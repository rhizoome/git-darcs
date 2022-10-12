"""Incremental import of git into darcs."""


import os
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from shutil import copy, rmtree
from subprocess import DEVNULL, PIPE, CalledProcessError
from subprocess import Popen as SPOpen
from subprocess import run as srun
from threading import Thread

import click
from click import ClickException
from colorama import Fore, Style, init
from readchar import readkey
from tqdm import tqdm

_uuid = "_b531990e-3187-4b52-be1f-6e4d4d1e40c9"
_darcs_comment = Path("_darcs", _uuid)
_env_comment = {"EDITOR": f"mv {_darcs_comment}", "VISUAL": f"mv {_darcs_comment}"}
_isatty = sys.stdout.isatty()
_verbose = False
_devnull = DEVNULL
_disable = None
_shutdown = False
_darcs_date = "%Y%m%d%H%M%S"
_pull_question = "Shall I pull this patch"
_pull_help = """
y: pull this patch
n: don't pull it
w: decide later

a: pull all remaining patches
i: don't pull remaining patches

l: show full log message
f: show full patch

?: help
h: help

c: cancel without pulling
q: cancel without pulling
"""

_boring = """
# git
(^|/)\\.git($|/)
# darcs
(^|/)_darcs($|/)
"""

_gitignore = "/_darcs"


def handle_shutdown():
    """Wait for CTRL-D and set _shutdown, to flag a graceful shutdown request."""
    global _shutdown
    print("Use CTRL-D for a graceful shutdown.")
    sys.stdin.read()
    print("Shutting down, use CTRL-C if shutdown takes too long.")
    print("If you use CTRL-C changes might be recorded twice.")
    _shutdown = True


def args_print(args):
    """Print args of executed command."""
    if _verbose:
        args = [str(x) for x in args]
        args = " ".join(args)
        print(f"\n$ {args}")


class Popen(SPOpen):
    """Inject defaults into Popen."""

    def __init__(self, *args, stderr=None, stdin=None, **kwargs):
        """Inject default into Popen."""
        args_print(args[0])
        if not stderr:
            stderr = _devnull
        if not stdin and "input" not in kwargs:
            stdin = _devnull
        super().__init__(*args, stderr=stderr, stdin=stdin, **kwargs)


def run(*args, stdout=None, stderr=None, stdin=None, **kwargs):
    """Inject defaults into run."""
    args_print(args[0])
    if not stdout:
        stdout = _devnull
    if not stderr:
        stderr = _devnull
    if not stdin and "input" not in kwargs:
        stdin = _devnull
    return srun(*args, stdout=stdout, stderr=stderr, stdin=stdin, **kwargs)


def hasnew():
    """Revert recorded changes in darcs."""
    try:
        run(["darcs", "whatsnew"], check=True)
    except CalledProcessError:
        return False
    return True


def revert():
    """Revert recorded changes in darcs."""
    run(["darcs", "revert", "--no-interactive"])


def initialize():
    """Initialize darcs."""
    run(["darcs", "initialize"], check=True)


def relink():
    """Relink darcs-repo, this is a bit of cargo-cult."""
    run(["darcs", "optimize", "relink"], check=True)


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
        darcs_add(dir)
        run(
            ["darcs", "move", "--case-ok", "--reserved-ok", orig, new],
            check=True,
        )


def darcs_add(path):
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


def darcs_clone(source, destination):
    """Clone darcs-repo."""
    run(
        ["darcs", "clone", source, destination],
        check=True,
    )


def get_patches(source, args):
    """Get patches from darcs."""
    res = run(
        ["darcs", "pull", "--dry-run", "--xml-output"] + args + [source],
        stdout=PIPE,
        check=True,
    )
    res = res.stdout.decode("UTF-8").strip()
    if res.startswith("No remote patches to pull in!"):
        return ET.fromstring("<root></root>")
    else:
        return ET.fromstring(res)


def show_full_patch(source, patch):
    """Show full patch with darcs."""
    run(
        ["darcs", "log", "-i", "--repodir", source, "-h", patch],
        stdout=sys.stdout,
        stderr=sys.stderr,
        input=b"y",
        check=True,
    )


def pull_patch(source, hash):
    """Pull a darcs-patch."""
    run(
        [
            "darcs",
            "pull",
            "--no-interactive",
            "--no-set-default",
            source,
            "-h",
            hash,
        ],
        check=True,
    )


def git_add(args=None):
    """Add changes to git."""
    if args is None:
        run(["git", "add", "."], check=True)
    else:
        run(["git", "add"] + args, check=True)


def git_commit(message):
    """Git commit."""
    run(["git", "commit", "--allow-empty", "-m", message], check=True)


def git_clone(source, destination):
    """Clone git-repo."""
    run(["git", "clone", source, destination], check=True)


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
    )


def is_ancestor(rev, last):
    """Check if revisiion can fast-forward."""
    try:
        run(["git", "merge-base", "--is-ancestor", last, rev], check=True)
        return True
    except CalledProcessError:
        return False


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
        ["git", "log", "--pretty=format:%cN <%cE>", "--max-count=1", rev],
        stdout=PIPE,
        check=True,
    )
    msg = res.stdout.decode("UTF-8").strip()
    if _verbose:
        print(msg)
    return msg


def onelines(rev, *, last=None):
    """Get the short-message of a commit from git."""
    if last:
        res = run(
            [
                "git",
                "log",
                "--oneline",
                "--no-decorate",
                "--date-order",
                "--no-merges",
                f"{last}..{rev}",
            ],
            stdout=PIPE,
            check=True,
        )
    else:
        res = run(
            ["git", "log", "--oneline", "--no-decorate", "--max-count=1", rev],
            stdout=PIPE,
            check=True,
        )
    msg = res.stdout.decode("UTF-8").strip()
    if _verbose:
        print(msg)
    return msg.splitlines()


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


def record_all(rev, *, last=None, postfix=None, comments=None):
    """Record all change onto the darcs-repo."""
    msgs = onelines(rev, last=last)
    msg = msgs[0]
    comments = "\n".join(msgs[1:])
    by = author(rev)
    if postfix:
        msg = f"{msg} {postfix}"
    elif comments:
        msg = f"{msg}\n\n{comments}"
    with _darcs_comment.open("w", encoding="UTF-8") as f:
        f.write(msg)
    try:
        env = dict(os.environ)
        env.update(_env_comment)
        res = run(
            [
                "darcs",
                "record",
                "--look-for-adds",
                "--no-interactive",
                "--ignore-times",
                "--edit-long-comment",
                "--author",
                by,
                "--name",
                "",
            ],
            check=True,
            stdout=PIPE,
            env=env,
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


class RenameDiffState:
    """State-machine for the rename parser."""

    INIT = 1
    IN_DIFF = 2
    ORIG_FOUND = 3


def get_rename_diff(rev, *, last=None):
    """Request the renames of a commit from git."""
    assert last != rev
    if last is None:
        action = "show"
        range = rev
    else:
        action = "diff"
        range = f"{last}..{rev}"
    with Popen(
        ["git", action, "--diff-filter=R", range],
        stdout=PIPE,
    ) as res:
        while line := res.stdout.readline():
            yield line.decode("UTF-8").strip()


def get_renames(rev, *, last=None):
    """Parse the renames from a git-rename-diff."""
    s = RenameDiffState
    state = s.INIT
    orig = ""
    new = ""
    for line in get_rename_diff(rev, last=last):
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


def record_revision(rev, *, last=None):
    """Record a revision, pre-record moves if there are any."""
    iters = 0
    count = 0
    renames = 0
    for _ in get_renames(rev, last=last):
        renames += 1

    if renames:
        with tqdm(desc="moves", total=renames, leave=False, disable=_disable) as pbar:
            for orig, new in get_renames(rev, last=last):
                move(orig, new)
                iters += 1
                if iters % 50 == 0:
                    record_all(rev, postfix=f"move({count:03d})")
                    count += 1
                pbar.update()
        wipe()
    checkout(rev)
    record_all(rev, last=last)


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
    print("Use git-darcs on an extra tracking-repository.")
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


@contextmanager
def ignore_darcs():
    """Replace .gitignore with one that ignores `_darcs`."""
    bfile = Path(".gitignore")
    old = None
    if bfile.exists():
        with bfile.open("rb") as f:
            old = f.read()
        bfile.unlink()

    with bfile.open("w", encoding="UTF-8") as f:
        f.write(_gitignore)
    yield
    bfile.unlink()
    if old:
        with bfile.open("wb") as f:
            f.write(old)
        git_add([".gitignore"])


def transfer(gen, count, *, last=None):
    """Transfer the git-commits to darcs."""
    try:
        with tqdm(desc="commits", total=count, disable=_disable) as pbar:
            records = 0
            for rev in gen:
                # Check if fast-forward is possible
                if is_ancestor(rev, last):
                    record_revision(rev, last=last)
                    last = rev
                    records += 1
                    if records % 100 == 0:
                        checkpoint(last)
                pbar.update()
                if _shutdown:
                    sys.exit(0)
    except Exception:
        print(f"Failed on revision {last}")
        raise
    return last


def import_range(rbase, *, from_checkpoint=False):
    """Run the transfer to darcs."""
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
        try:
            last = rbase
            if not from_checkpoint:
                record_all(rbase)
            last = transfer(gen, count, last=last)
            if last != rhead:
                checkout(rhead)
                record_all(rhead)
        finally:
            checkpoint(rhead)


def import_one():
    """Import current revisiion."""
    head = get_head()
    wipe()
    checkout(head)
    record_all(head)
    checkpoint(head)


def fix_pwd():
    """Fix pwd if GIT_DARCS_PWD is given."""
    pwd = os.environ.get("GIT_DARCS_PWD")
    if pwd:
        os.chdir(pwd)


def setup(warn, verbose):
    """Set verbose and warn up."""
    global _verbose
    global _devnull
    global _disable
    if warn:
        warning()
    _verbose = verbose
    if verbose:
        _devnull = None
        _disable = True


def prepare_update(base, shallow):
    """Check repo, arguments, find base and setup shutdown."""
    if not Path(".git").exists():
        raise ClickException("Please run git-darcs in the root of your git-repo.")
    if not Path("_darcs").exists():
        initialize()
    rbase = get_lastest_rev()
    from_checkpoint = False
    if rbase:
        from_checkpoint = True
        do_one = False
        if base:
            print("Found git-checkpoint, ignoring base-option")
        if shallow is True:
            print("Found git-checkpoint, ignoring shallow-option")
    else:
        do_one = True
        if base:
            do_one = False
            rbase = base
            if shallow is True:
                print("Found base-option, ignoring shallow-option")
        if shallow is False:
            do_one = False
            rbase = get_base()
    if _isatty:
        _thread = Thread(target=handle_shutdown, daemon=True)
        _thread.start()
    return rbase, from_checkpoint, do_one


def run_update(rbase, from_checkpoint, do_one):
    """Run conversion loop."""
    branch = get_current_branch()
    failed = True
    try:
        try:
            checkout(".")
        except CalledProcessError:
            pass
        if do_one:
            import_one()
        else:
            import_range(rbase, from_checkpoint=from_checkpoint)
        failed = False
    finally:
        if branch:
            if failed and _verbose:
                print(f"Not restoring to `{branch}` in verbose-mode failure.")
            else:
                wipe()
                checkout(branch)


def ask(question, choice, *, text="", state="", help=""):
    """Ask a question on the terminal."""
    key = "?"
    if text:
        print(text)
    while key in ("h", "?"):
        sys.stdout.write(f"{question}? {state}  [{choice}], or ? for more options: ")
        sys.stdout.flush()
        key = readkey()
        print(key)
        if key in ("h", "?"):
            print(help)
    return key


class Patch:
    """Represents a darcs-patch."""

    def __init__(self, source, patch):
        """Dear flake8 this is a init function."""
        self.source = source
        self.patch = patch
        fields = patch.attrib
        self.author = fields["author"]
        self.hash = fields["hash"]
        self.chash = Fore.CYAN + f"patch {self.hash}" + Style.RESET_ALL
        self.date = datetime.strptime(fields["date"], _darcs_date)
        self.subject = patch.find("name").text
        comment = patch.find("comment").text
        if comment.startswith("Ignore-this: "):
            comment = os.linesep.join(comment.splitlines()[1:])
        self.comment = comment.strip()
        self.pull = None

    def short(self):
        """Get a short description of the patch."""
        return f"""
{self.chash}
Author: {self.author}
Date: {self.date}
Subject: {self.subject}
        """.strip()

    def long(self):
        """Get a longer description of the patch."""
        if self.comment:
            return f"{self.short()}\n\n{self.comment}"
        else:
            return self.short()

    def full(self):
        """Show the full patch."""
        show_full_patch(self.source, self.hash)

    def message(self):
        """Format patch message for git."""
        return f"{self.subject}\n\n{self.comment}".strip()

    def ask(self, index, of):
        """Ask if I should pull this patch."""
        key = "l"
        text = self.short()
        while key in ("l", "f"):
            key = ask(
                _pull_question,
                "ynwasc",
                text=text,
                state=f"{index + 1}/{of}",
                help=_pull_help,
            )
            text = ""
            if key == "l":
                print(self.long())
            elif key == "f":
                self.full()
            elif key == "y":
                self.pull = True
            elif key == "n":
                self.pull = False
            elif key == "a":
                self.pull = True
            elif key == "i":
                self.pull = False
        return key


class Pull:
    """Contains state for the pull-questions."""

    def __init__(self, source, args, *, ignore_temp=True):
        """Dear flake8 this is a init function."""
        self.source = source
        self.args = args
        self.ignore_temp = ignore_temp
        self.patches_xml = get_patches(source, args)
        self.patches = OrderedDict()  # Legacy support
        for patch in self.patches_xml:
            obj = Patch(source, patch)
            if self.ignore_temp:
                if not obj.subject.startswith("temp: "):
                    self.patches[obj.hash] = obj
            else:
                self.patches[obj.hash] = obj

    def pull(self, all=False):
        """Pull patches."""
        if not self.patches:
            print("No remote patches to pull in!")
            return
        if all:
            for patch in self.patches.values():
                patch.pull = True
        else:
            self.decide()
        pull = [x for x in self.patches.values() if x.pull]
        count = len(pull)
        if not all:
            key = ask(f"Shall I pull {count} patches", "yn")
            if key in ("n", "q", "c"):
                print("Cancel pull")
                sys.exit(1)
        with tqdm(desc="pull", total=count, disable=_disable) as pbar:
            for patch in pull:
                pull_patch(self.source, patch.hash)
                with ignore_darcs():
                    git_add()
                git_commit(patch.message())
                pbar.update()

    def pull_depends(self, hash):
        """Find dependent patches an set pull to True for these, too."""
        xml = get_patches(self.source, ["-h", hash])
        count = 0
        for patch in xml:
            hash = patch.attrib["hash"]
            patch = self.patches[hash]
            if not patch.pull:
                count += 1
                patch.pull = True
        if count:
            print(Fore.RED + f"Select {count} dependent patches" + Style.RESET_ALL)

    def decide(self):
        """Decide patches to pull."""
        decide = OrderedDict(self.patches)
        while decide:
            key = None
            of = len(decide)
            for index, (hash, patch) in enumerate(OrderedDict(decide).items()):
                key = patch.ask(index, of)
                if patch.pull is not None:
                    if patch.pull:
                        self.pull_depends(hash)
                    decide.pop(hash)
                if key == "a":
                    break
                elif key == "i":
                    break
                elif key in ("c", "q"):
                    print("Cancel pull")
                    sys.exit(1)

            of = len(decide)
            with tqdm(desc="resolve", total=of, disable=_disable) as pbar:
                for hash, patch in OrderedDict(decide).items():
                    if key == "a":
                        patch.pull = True
                        self.pull_depends(hash)
                    elif key == "i":
                        patch.pull = False
                    decide.pop(hash)
                    pbar.update()


@click.group()
def main():
    """Click entrypoint."""
    fix_pwd()


@main.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=True, file_okay=False))
@click.argument("destination", type=click.Path(exists=False))
@click.option("-v/-nv", "--verbose/--no-verbose", default=False)
def clone(source, destination, verbose):
    """Locally clone a tracking-repository to get a working-repository."""
    setup(False, verbose=verbose)
    with tqdm(desc="clone", total=5, disable=_disable) as pbar:
        destination = Path(destination)
        if destination.exists():
            raise ClickException(f"Destination `{destination}` may not exist")
        git_clone(source, destination)
        pbar.update()
        dest = Path(destination, ".git", "config")
        dest.unlink()
        copy(Path(source, ".git", "config"), dest)
        pbar.update()
        darcs_dest = Path(destination, _uuid)
        repo_source = Path(darcs_dest, "_darcs")
        darcs_clone(source, darcs_dest)
        pbar.update()
        repo_source = Path(darcs_dest, "_darcs")
        repo_dest = Path(destination, "_darcs")
        repo_source.rename(repo_dest)
        rmtree(darcs_dest, ignore_errors=True)
        pbar.update()
        os.chdir(destination)
        relink()
        pbar.update()


@main.command()
@click.option("-v/-nv", "--verbose/--no-verbose", default=False)
@click.option(
    "-w/-nw",
    "--warn/--no-warn",
    default=True,
    help="Warn that repository will be cleared",
)
@click.option(
    "--base",
    "-b",
    default=None,
    help="On first update import from (commit-ish)",
)
@click.option(
    "-s/-ns",
    "--shallow/--no-shallow",
    default=None,
    help="On first update only import current commit",
)
def update(verbose, warn, base, shallow):
    """Incremental import of git into darcs.

    By default it imports a shallow copy (the current commit). Use `--no-shallow`
    to import the complete history.
    """
    setup(warn, verbose=verbose)
    run_update(*prepare_update(base, shallow))


@main.command()
@click.option("-v/-nv", "--verbose/--no-verbose", default=False)
@click.option(
    "-w/-nw",
    "--warn/--no-warn",
    default=True,
    help="Warn that repository will be cleared",
)
@click.option(
    "-a/-na",
    "--all/--no-all",
    default=False,
    help="Pull all patches",
)
@click.option(
    "-i/-ni",
    "--ignore-temp/--no-ignore-temp",
    default=True,
    help="Ignore temporary patches (with 'temp: ')",
)
@click.argument("source", type=click.Path(exists=True, dir_okay=True, file_okay=False))
@click.argument("darcs", nargs=-1)
def pull(verbose, all, warn, source, darcs, ignore_temp):
    """Pull from source darcs-repository into a tracking-repository.

    A tracking-repository is created by `git darcs update` and contains a git- and a
    darcs-repository. Arguments after `--` are passed to `darcs pull`.
    """
    setup(warn, verbose=verbose)
    if not Path("_darcs").exists():
        raise ClickException("Please run git-darcs in the root of your darcs-repo.")
    if not Path(".git").exists():
        raise ClickException("Please run git-darcs in the root of your git-repo.")
    wipe()
    if hasnew():
        raise ClickException(
            "The git and the darcs repo in your tracking-repo are not in sync."
        )

    init()
    Pull(source, list(darcs), ignore_temp=ignore_temp).pull(all)
