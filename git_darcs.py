"""Incremental import of git into darcs."""

import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError
from subprocess import Popen as SPOpen
from subprocess import run as srun
from threading import Thread

import click
from tqdm import tqdm

_isatty = sys.stdout.isatty()
_verbose = False
_devnull = DEVNULL
_disable = None
_shutdown = False

_boring = """
# git
(^|/)\\.git($|/)
# darcs
(^|/)_darcs($|/)
"""


def handle_shutdown():
    """Wait for CTRL-D and set _shutdown, to flag a graceful shutdown request."""
    global _shutdown
    print("Use CTRL-D for a graceful shutdown.")
    sys.stdin.read()
    print("Shutting down, use CTRL-C if shutdown takes too long.")
    _shutdown = True


class Popen(SPOpen):
    """Inject default into Popen."""

    def __init__(self, *args, stdin=None, **kwargs):
        """Well, dear flake8 this is a __init__."""
        if not stdin:
            stdin = _devnull
        super().__init__(*args, stdin=stdin, **kwargs)


def run(*args, stdout=_devnull, stdin=None, **kwargs):
    """Inject defaults into run."""
    if not stdin:
        stdin = _devnull
    return srun(*args, stdout=stdout, stdin=stdin, **kwargs)


def wipe():
    """Completely clean the git-repo except `_darcs`."""
    run(
        ["git", "reset"],
        check=True,
    )
    run(
        ["git", "clean", "-xdf", "--exclude", "/_darcs"],
        check=True,
    )


def checkout(rev):
    """Checkout a git-commit."""
    run(
        ["git", "checkout", rev],
        check=True,
        stderr=_devnull,
    )


def revert():
    """Revert recorded changes in darcs."""
    run(["darcs", "revert", "--no-interactive"])


def optimize():
    """Optimize darcs-repo, this is a bit of a cargo-cult."""
    run(["darcs", "optimize", "clean"], check=True)
    run(["darcs", "optimize", "compress"], check=True)
    run(["darcs", "optimize", "pristine"], check=True)


def move(orig, new):
    """Move a file in the darcs-repo."""
    porig = Path(orig)
    if (porig.is_file() or porig.is_dir()) and not porig.is_symlink():
        dir = Path(new).parent
        dir.mkdir(parents=True, exist_ok=True)
        add(dir)
        run(
            ["darcs", "move", "--case-ok", "--reserved-ok", orig, new],
            check=True,
        )


def add(path):
    """Add a path to the darcs-repo."""
    try:
        run(
            ["darcs", "add", "--case-ok", "--reserved-ok", str(path)],
            stderr=PIPE,
            check=True,
        )
    except CalledProcessError as e:
        if "No files were added" not in e.stderr.decode("UTF-8"):
            raise


def tag(name):
    """Tag a state in the darcs-repo."""
    run(
        ["darcs", "tag", "--skip-long-comment", "--name", name],
        check=True,
        input=b"\n",
    )


def get_tags():
    """Get tags from darcs."""
    res = run(
        ["darcs", "show", "tags"],
        check=True,
        stdout=PIPE,
    )
    return res.stdout.decode("UTF-8").strip().splitlines()


def get_current_branch():
    """Get the current branch from git."""
    res = run(
        ["git", "branch", "--show-current"],
        stdout=PIPE,
        check=True,
    )
    branch = res.stdout.decode("UTF-8").strip()
    if _verbose:
        print(branch)
    return branch


def author(rev):
    """Get the author of a commit from git."""
    res = run(
        ["git", "log", "--pretty=format:'%cN <%cE>'", "--max-count=1", rev],
        stdout=PIPE,
        check=True,
    )
    msg = res.stdout.decode("UTF-8").strip()
    if _verbose:
        print(msg)
    return msg


def message(rev):
    """Get the short-message of a commit from git."""
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
    """Record all change onto the darcs-repo."""
    msg = message(rev)
    by = author(rev)
    if postfix:
        msg = f"{msg} {postfix}"
    try:
        res = run(
            [
                "darcs",
                "record",
                "--look-for-adds",
                "--no-interactive",
                "--ignore-times",
                "--author",
                by,
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
    """Get a linearized path from base to head from git."""
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
    """Get the root/base commit from git."""
    base = (
        run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            check=True,
            stdout=PIPE,
        )
        .stdout.strip()
        .decode("UTF-8")
        .splitlines()[-1]
    )
    if _verbose:
        print(base)
    return base


def get_head():
    """Get the current head from git."""
    res = run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        stdout=PIPE,
    )
    head = res.stdout.strip().decode("UTF-8")
    if _verbose:
        print(head)
    return head


def get_rename_diff(rev):
    """Request the renames of a commit from git."""
    with Popen(
        ["git", "show", "--diff-filter=R", rev],
        stdout=PIPE,
    ) as res:
        while line := res.stdout.readline():
            yield line.decode("UTF-8").strip()


class RenameDiffState:
    """State-machine for the rename parser."""

    INIT = 1
    IN_DIFF = 2
    ORIG_FOUND = 3


def get_renames(rev):
    """Parse the renames from a git-rename-diff."""
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
    """Record a revision, pre-record moves if there are any."""
    iters = 0
    count = 0
    renames = 0
    for _ in get_renames(rev):
        renames += 1

    if renames:
        with tqdm(desc="moves", total=renames, leave=False, disable=_disable) as pbar:
            for orig, new in get_renames(rev):
                move(orig, new)
                iters += 1
                if iters % 50 == 0:
                    record_all(rev, f"move({count:03d})")
                    count += 1
                pbar.update()
                if _shutdown:
                    revert()
                    sys.exit(0)
    wipe()
    checkout(rev)
    record_all(rev)


def get_lastest_rev():
    """Get the latest git-commit recorded in darcs."""
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
    """Tag/checkpoint the current git-commit."""
    date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    tag(f"git-checkpoint {date} {rev}")
    optimize()


def warning():
    """Print a warning that git-darcs is going to wipe uncommitted change."""
    print("Use git-darcs on an extra tracking repository.")
    print("git-darcs WILL CLEAR ALL YOUR WORK THAT IS NOT COMMITED!")
    print("Use -nw to skip this warning.\n")
    print("Press enter to continue")
    sys.stdin.readline()


@contextmanager
def less_boring():
    """Replace boring with one that only ignores `.git` and `_darcs`."""
    bfile = Path("_darcs/prefs/boring")
    disable = Path(bfile.parent, "not_boring")
    bfile.rename(disable)
    with bfile.open("w", encoding="UTF-8") as f:
        f.write(_boring)
    yield
    bfile.unlink()
    disable.rename(bfile)


def transfer(gen, count):
    """Transfer the git-commits to darcs."""
    try:
        last = None
        with tqdm(desc="commits", total=count, disable=_disable) as pbar:
            iters = 0
            for rev in gen:
                record_revision(rev)
                pbar.update()
                last = rev
                iters += 1
                if iters % 100 == 0:
                    checkpoint(last)
                if _shutdown:
                    sys.exit(0)
    except Exception:
        print(f"Failed on revision {last}")
        raise
    finally:
        checkpoint(last)


def runner(base):
    """Run the transfer to darcs."""
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
    for _ in get_rev_list(rhead, rbase):
        count += 1
    if count == 0:
        return
    gen = get_rev_list(rhead, rbase)
    wipe()
    checkout(rbase)
    with less_boring():
        record_all(rbase)
        transfer(gen, count)

def checks():
    bailout = False
    if not Path("_darcs"):
        bailout = True
        print("darcs repository not initialized.")
    if not Path("_darcs"):
        bailout = True
        print("Please run git-darcs in the root of your git-repo.")
    if bailout:
        sys.exit(1)


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

    By default it imports from the first commit or the last checkpoint.
    """
    global _verbose
    global _devnull
    global _disable
    pwd = os.environ.get("GIT_DARCS_PWD")
    if pwd:
        os.chdir(pwd)
    checks()
    if warn:
        warning()
    if _isatty:
        _thread = Thread(target=handle_shutdown, daemon=True)
        _thread.start()
    _verbose = verbose
    if verbose:
        _devnull = None
        _disable = True
    branch = get_current_branch()
    failed = True
    try:
        runner(base)
        failed = False
    finally:
        if branch:
            if failed and verbose:
                print(f"Not restoring to `{branch}` in verbose-mode failure.")
            else:
                wipe()
                checkout(branch)
