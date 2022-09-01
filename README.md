git-darcs
=========

Just call `git-darcs`, git-darcs will import the history from the first commit.
It will remember (checkpoint) the last imported commit. If you call `git-darcs`
again it will import from the last checkpoint.

It will import a linearized version if the history, some patches might differ
from the original git-commit.

The tool intentionally very minimal, it is for devs. They can read tracebacks or
change the code to fit better.

install
-------

If your system python isn't 3.10 use:

`poetry env use $HOME/.pyenv/versions/3.10.5/bin/python3.10`

to set a version installed by pyenv.

usage
-----

```
Usage: git-darcs [OPTIONS]

  Incremental import of git into darcs.

  By default it imports from the first commit or the last checkpoint.

Options:
  -v, --verbose / -nv, --no-verbose
  -w, --warn / -nw, --no-warn
  -b, --base TEXT                 First import from (commit-ish)
  --help                          Show this message and exit.
```
