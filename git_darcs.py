from subprocess import PIPE, CalledProcessError, Popen, run

import click


def wipe():
    run(["git", "reset"], check=True)
    run(["git", "clean", "-xdf", "--exclude", "/_darcs"], check=True)


def checkout(rev):
    run(["git", "checkout", "-q", rev], check=True)


def move(rename):
    orig, new = rename
    run(["darcs", "move", orig, new], check=True)


def tag(name):
    run(["darcs", "tag", "--name", name], check=True)


def message(rev):
    res = run(
        ["git", "log", "--oneline", "--no-decorate", "--max-count=1", rev],
        stdout=PIPE,
        check=True,
    )
    return res.stdout.decode("UTF-8").strip()


def record_all(rev):
    msg = message(rev)
    try:
        run(
            ["darcs", "record", "--look-for-adds", "--no-interactive", "--name", msg],
            check=True,
            stdout=PIPE,
        )
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
    return (
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


def get_head():
    res = run(["git", "rev-parse", "HEAD"], check=True, stdout=PIPE)
    return res.stdout.strip().decode("UTF-8")


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
    for rename in get_renames(rev):
        move(rename)
    wipe()
    checkout(rev)
    record_all(rev)


@click.command()
def main():
    """Incremental import of git into darcs."""
    base = get_base()
    gen = get_rev_list(get_head(), get_base())
    checkout(base)
    wipe()
    record_all(base)
    for rev in gen:
        record_revision(rev)
    tag(f"git-checkpoint {rev}")
