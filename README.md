git-darcs
=========

Just call `git-darcs`, it will import the history from the first commit.
It will remember (checkpoint) the last imported commit. If you call `git-darcs`
again it will import from the last checkpoint.

It will import a linearized version if the history, some patches might differ
from the original git-commit.

The tool intentionally very minimal, it is for devs. They can read tracebacks or
change the code to fit better.

for darcs beginners
-------------------

You have to read the [darcs book](https://darcsbook.acmelabs.space/), you just
have to.

Darcs does not handle `chmod` or symbolic-links. The easiest way to workaround
this, is letting `git` do the work. I have two git/darcs repositories for each
project.

* `project` (the repository I work in) containing a `.git` and a `_darcs`
* `project-tracking` (the repository that tracks changes from upstrream
   also containing a `.git` and a `_darcs`

I then pull new darcs-patches from `project-tracking` into `project`. Once
the changes are in upstream, I obliterate everything to the last checkpoint and
pull the patches (now via git) from `project-tracking`.

Since I always make git-commits from the darcs-patches git will track `chmod`
and symbolic-links for me.

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
  -w, --warn / -nw, --no-warn     Warn that repository will be cleaned
  -b, --base TEXT                 First import from (commit-ish)
  --help                          Show this message and exit.
```
