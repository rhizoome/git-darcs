from datetime import datetime
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError, Popen, run

import click
from tqdm import tqdm

_verbose = False
_devnull = DEVNULL
if _verbose:
    _devnull = None


def wipe():
    run(["git", "reset"], check=True, stdout=_devnull)
    run(["git", "clean", "-xdf", "--exclude", "/_darcs"], check=True, stdout=_devnull)


def checkout(rev):
    run(["git", "checkout", rev], check=True, stdout=_devnull, stderr=_devnull)


def move(rename):
    orig, new = rename
    dir = Path(new).parent
    dir.mkdir(parents=True, exist_ok=True)
    add(dir)
    run(["darcs", "move", "--case-ok", orig, new], check=True, stdout=_devnull)


def add(path):
    try:
        run(["darcs", "add", str(path)], stderr=PIPE, check=True, stdout=_devnull)
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
    try:
        res = Popen(
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
        )
        while line := res.stdout.readline():
            yield line.decode("UTF-8").strip()
    finally:
        res.wait()


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
    try:
        res = Popen(
            ["git", "show", "--diff-filter=R", rev],
            stdout=PIPE,
        )
        while line := res.stdout.readline():
            yield line.decode("UTF-8").strip()
    finally:
        res.wait()


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
        with tqdm(desc="moves", total=renames, leave=False) as pbar:
            for rename in get_renames(rev):
                move(rename)
                iters += 1
                if iters % 20 == 0:
                    record_all(rev, f"move({count:04d})")
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


@click.command()
def main():
    """Incremental import of git into darcs."""
    branch = get_current_branch()
    try:
        base = get_lastest_rev()
        head = get_head()
        if base == head:
            return
        if base is None:
            base = get_base()
        count = 0
        for rev in get_rev_list(get_head(), base):
            count += 1
        gen = get_rev_list(get_head(), base)
        wipe()
        checkout(base)
        record_all(base)
        last = None
        try:
            with tqdm(desc="commits", total=count) as pbar:
                for rev in gen:
                    record_revision(rev)
                    pbar.update()
                    last = rev
        finally:
            date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            tag(f"git-checkpoint {date} {last}")
    finally:
        if branch:
            # checkout(branch)
            pass
