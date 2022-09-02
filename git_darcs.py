import sys
from datetime import datetime
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError, Popen, run

import click
from tqdm import tqdm

_verbose = False
_devnull = DEVNULL
_disable = None


def wipe():
    run(["git", "reset"], check=True, stdout=_devnull)
    run(["git", "clean", "-xdf", "--exclude", "/_darcs"], check=True, stdout=_devnull)


def checkout(rev):
    run(["git", "checkout", rev], check=True, stdout=_devnull, stderr=_devnull)


def optimize():
    run(["darcs", "optimize", "clean"], check=True, stdout=_devnull)
    run(["darcs", "optimize", "compress"], check=True, stdout=_devnull)
    run(["darcs", "optimize", "pristine"], check=True, stdout=_devnull)


def move(rename):
    orig, new = rename
    dir = Path(new).parent
    dir.mkdir(parents=True, exist_ok=True)
    add(dir)
    run(["darcs", "move", "--case-ok", orig, new], check=True, stdout=_devnull)


def add(path):
    try:
        run(
            ["darcs", "add", "--case-ok", str(path)],
            stderr=PIPE,
            check=True,
            stdout=_devnull,
        )
    except CalledProcessError as e:
        if "No files were added" not in e.stderr.decode("UTF-8"):
            raise


def tag(name):
    run(["darcs", "tag", "--name", name], check=True, stdout=_devnull)


def get_tags():
    res = run(
        ["darcs", "show", "tags"],
        check=True,
        stdout=PIPE,
    )
    return res.stdout.decode("UTF-8").strip().splitlines()


def get_current_branch():
    res = run(
        ["git", "branch", "--show-current"],
        stdout=PIPE,
        check=True,
    )
    branch = res.stdout.decode("UTF-8").strip()
    if _verbose:
        print(branch)
    return branch


def message(rev):
    res = run(
        ["git", "log", "--oneline", "--no-decorate", "--max-count=1", rev],
        stdout=PIPE,
        check=True,
    )
    msg = res.stdout.decode("UTF-8").strip()
    if _verbose:
        print(msg)
    return msg


def record_all(rev, postfix=""):
    msg = message(rev)
    if postfix:
        msg = f"{rev} {postfix}"
    try:
        res = run(
            [
                "darcs",
                "record",
                "--look-for-adds",
                "--no-interactive",
                "--name",
                msg,
            ],
            check=True,
            stdout=PIPE,
            stderr=_devnull,
        )
        if _verbose:
            print(res.stdout.decode("UTF-8").strip())
    except CalledProcessError as e:
        if "No changes!" not in e.stdout.decode("UTF-8"):
            raise


def get_rev_list(head, base):
    with Popen(
        [
            "git",
            "rev-list",
            "--reverse",
            "--topo-order",
            "--ancestry-path",
            "--no-merges",
            f"{base}..{head}",
        ],
        stdout=PIPE,
    ) as res:
        while line := res.stdout.readline():
            yield line.decode("UTF-8").strip()


def get_base():
    base = (
        run(
            [
                "git",
                "rev-list",
                "--all",
                "--max-parents=0",
            ],
            check=True,
            stdout=PIPE,
        )
        .stdout.strip()
        .decode("UTF-8")
    )
    if _verbose:
        print(base)
    return base


def get_head():
    res = run(["git", "rev-parse", "HEAD"], check=True, stdout=PIPE)
    head = res.stdout.strip().decode("UTF-8")
    if _verbose:
        print(head)
    return head


def get_rename_diff(rev):
    with Popen(
        ["git", "show", "--diff-filter=R", rev],
        stdout=PIPE,
    ) as res:
        while line := res.stdout.readline():
            yield line.decode("UTF-8").strip()


class RenameDiffState:
    INIT = 1
    IN_DIFF = 2
    ORIG_FOUND = 3


def get_renames(rev):
    s = RenameDiffState
    state = s.INIT
    orig = ""
    new = ""
    for line in get_rename_diff(rev):
        if state == s.INIT:
            if line.startswith("diff --git"):
                state = s.IN_DIFF
        elif state == s.IN_DIFF:
            start = "rename from "
            if line.startswith(start):
                _, _, orig = line.partition(start)
                orig = orig.strip()
                state = s.ORIG_FOUND
        elif state == s.ORIG_FOUND:
            start = "rename to "
            if line.startswith(start):
                _, _, new = line.partition(start)
                yield (orig, new)
                state = s.IN_DIFF


def record_revision(rev):
    iters = 0
    count = 0
    renames = 0
    for rename in get_renames(rev):
        renames += 1

    if renames:
        with tqdm(desc="moves", total=renames, leave=False, disable=_disable) as pbar:
            for rename in get_renames(rev):
                move(rename)
                iters += 1
                if iters % 50 == 0:
                    record_all(rev, f"move({count:03d})")
                    count += 1
                pbar.update()
    wipe()
    checkout(rev)
    record_all(rev)


def get_lastest_rev():
    res = []
    start = "git-checkpoint "
    for tag in get_tags():
        if tag.startswith(start):
            res.append(tag)
    if len(res) > 0:
        _, _, hash = sorted(res)[-1].partition(start)
        return hash.split(" ")[1]
    return None


def checkpoint(rev):
    date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    tag(f"git-checkpoint {date} {rev}")
    optimize()


def warning():
    print("Use git-darcs on an extra tracking repository.")
    print("git-darcs WILL CLEAR ALL YOUR WORK! Use -nw to skip this warning.\n")
    print("press enter to continue")
    sys.stdin.readline()


@click.command()
@click.option("-v/-nv", "--verbose/--no-verbose", default=False)
@click.option(
    "-w/-nw",
    "--warn/--no-warn",
    default=True,
    help="Warn that repository will be cleaned",
)
@click.option(
    "--base",
    "-b",
    default=None,
    help="First import from (commit-ish)",
)
def main(verbose, base, warn):
    """Incremental import of git into darcs.

    By default it imports from the first commit or the last checkpoint."""
    global _verbose
    global _devnull
    global _disable
    if warn:
        warning()
    _verbose = verbose
    if verbose:
        _devnull = None
        _disable = True
    branch = get_current_branch()
    try:
        rbase = get_lastest_rev()
        if rbase is None:
            if base:
                rbase = base
            else:
                rbase = get_base()
        else:
            if base:
                print("Found checkpoint base-option is ignored")
        rhead = get_head()
        if rbase == rhead:
            return
        count = 0
        for rev in get_rev_list(rhead, rbase):
            count += 1
        gen = get_rev_list(rhead, rbase)
        wipe()
        checkout(rbase)
        record_all(rbase)
        last = None
        try:
            with tqdm(desc="commits", total=count, disable=_disable) as pbar:
                iters = 0
                for rev in gen:
                    record_revision(rev)
                    pbar.update()
                    last = rev
                    iters += 1
                    if iters % 200 == 0:
                        checkpoint(last)
        finally:
            checkpoint(last)
    finally:
        if branch:
            wipe()
            checkout(branch)
