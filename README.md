git-darcs - Incremental import of git into darcs
================================================

[![Test](https://github.com/ganwell/git-darcs/actions/workflows/test.yml/badge.svg)](https://github.com/ganwell/git-darcs/actions/workflows/test.yml) [![CodeQL](https://github.com/ganwell/git-darcs/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/ganwell/git-darcs/actions/workflows/codeql-analysis.yml)

[git-darcs on pypi](https://pypi.org/project/git-darcs/)

Just call `git-darcs update`, it will import current git-commit into darcs. If
you get new commits eg. using `git pull`, you can call `git-darcs update` and it
will import each commit into darcs.

By default the first import is shallow, only importing the current git-commit.
If you want to import the whole history use `git-darcs update --no-shallow`,
since we **linearize** history be checking out each commit this can take very
long.

On the first import you can also supply a custom base-commit `git-darcs update
--base fa2b982` ignoring history you are not interested in.

The options `base` and `shallow` are ignored after the first import.

Use a global `gitignore` to ignore `_darcs` in all your depositories.

With `git-darcs clone <source> <destination>` you can clone a darcs/git dual
repository locally. Both git and darcs will make sure no history-data is
duplicated.

The tool intentionally very minimal, it is for devs. They can read tracebacks or
change the code to fit better.

For darcs beginners
-------------------

* You have to read the [darcs book](https://darcsbook.acmelabs.space/), you just
  have to
* `_darcs/pref/boring` is the equivalent of `.gitignore`, but has quite a wide
  definition of boring by default

Darcs does not handle `chmod` or symbolic-links. The easiest way to workaround
this, is letting `git` do the work. I have two git/darcs repositories for each
project.

* `project` (the repository I work in) containing a `.git` and a `_darcs`
* `project-tracking` (the repository that tracks changes from upstrream,
   also containing a `.git` and a `_darcs`

I then pull new darcs-patches from `project-tracking` into `project`. Once my
the changes are in upstream, I obliterate everything to the checkpoint I started
with and pull the patches (now via `git`) from `project-tracking`. Or I remove
`project` and clone it again from `project-tracking`.

Since I always make git-commits from the darcs-patches `git` will track `chmod`
and symbolic-links for me.

Install
-------

If your system python isn't 3.10 or newer use:

`poetry env use $HOME/.pyenv/versions/3.10.5/bin/python3.10`

to set a version installed by pyenv. You can probably set a lower version in
`pyproject.toml`. 3.10 is just the one I am using and I know works.

Usage
-----

<a href="https://asciinema.org/a/518694" target="_blank"><img
src="https://asciinema.org/a/518694.svg" /></a>

Note: this asciinema was made before `shallow` was default.

```
$> git-darcs --help
Usage: git-darcs [OPTIONS] COMMAND [ARGS]...

  Click entrypoint.

Options:
  --help  Show this message and exit.

Commands:
  clone   Locally clone a tracking repository to get a working repository.
  update  Incremental import of git into darcs.
```

```
$> git-darcs update --help
Usage: git-darcs update [OPTIONS]

  Incremental import of git into darcs.

  By default it imports from the first commit or the last checkpoint.

Options:
  -v, --verbose / -nv, --no-verbose
  -w, --warn / -nw, --no-warn     Warn that repository will be cleaned
  -b, --base TEXT                 On first update import from (commit-ish)
  -s, --shallow / -ns, --no-shallow
                                  On first update only import current commit
  --help                          Show this message and exit.
```

```
$> git-darcs clone --help
Usage: git-darcs clone [OPTIONS] SOURCE DESTINATION

  Locally clone a tracking repository to get a working repository.

Options:
  -v, --verbose / -nv, --no-verbose
  --help                          Show this message and exit.
```
