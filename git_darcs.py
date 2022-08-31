from datetime import datetime
from subprocess import PIPE, CalledProcessError, Popen, run

import click
from tqdm import tqdm


def wipe():
    run(["git", "reset", "-q"], check=True)
    run(["git", "clean", "-q", "-xdf", "--exclude", "/_darcs"], check=True)


def checkout(rev):
    run(["git", "checkout", "-q", rev], check=True)


def move(rename):
    orig, new = rename
    run(["darcs", "move", "-q", orig, new], check=True)


def tag(name):
    run(["darcs", "tag", "-q", "--name", name], check=True)


def get_tags():
    res = run(
        ["darcs", "show", "tags"],
        check=True,
        stdout=PIPE,
    )
    return res.stdout.decode("UTF-8").strip().splitlines()


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
            [
                "darcs",
                "record",
                "-q",
                "--look-for-adds",
                "--no-interactive",
                "--name",
                msg,
            ],
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
    checkout(base)
    wipe()
    record_all(base)
    with tqdm(total=count) as pbar:
        for rev in gen:
            record_revision(rev)
            pbar.update()
    date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    tag(f"git-checkpoint {date} {rev}")
