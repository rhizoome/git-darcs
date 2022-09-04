git-darcs - Incremental import of git into darcs
================================================

[![Test](https://github.com/ganwell/git-darcs/actions/workflows/test.yml/badge.svg)](https://github.com/ganwell/git-darcs/actions/workflows/test.yml) [![CodeQL](https://github.com/ganwell/git-darcs/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/ganwell/git-darcs/actions/workflows/codeql-analysis.yml)

[git-darcs on pypi](https://pypi.org/project/git-darcs/)

See "Linearized history" for the big problem with this approach. The tool is
meant to temporarly bring in changes from upstream, so we can work/test against
these. So the broken history doesn't really matter to me, as long as the
resulting state is correct, which it is (I tested that a lot).

Just call `git-darcs update`, it will import the current git-commit into darcs.
If you get new commits eg. using `git pull`, you can call `git-darcs update` and
it will import each commit into darcs.

By default the first import is shallow, only importing the current git-commit.
If you want to import the whole history use `git-darcs update --no-shallow`,
since we **linearize** the history by checking out each commit this can take
very long.

On the first import you can also supply a custom base-commit `git-darcs update
--base fa2b982` ignoring history you are not interested in.

The options `base` and `shallow` are ignored after the first import.

Use a global `gitignore` to ignore `_darcs` in all your depositories.

With `git-darcs clone <source> <destination>` you can clone a darcs/git dual
repository locally. Both git and darcs will make sure no history-data is
duplicated on disk.

The tool is intentionally very minimal, it is for devs. They can read tracebacks
or change the code to fit better. To create git patches from my
working-repositories I use `darcs rebase suspend` and `git commit -a -v`.

But why
-------

I prefer to group changes by topic, so I am constantly amending patches. This is
very easy in darcs and more complicated in git. Yes, I know about `--fixup` and
`--autosquash` in git. Also I can find independent low-risk patches easily with
`darcs show dependencies`, so I can constantly make PRs. Making the final
_breaking_ change/PR much smaller. This is less tedious for the reviewers.

For darcs beginners
-------------------

* There is a great [video](https://hikari.acmelabs.space/videos/hikari-darcs.mp4) by
  [raichoo](https://hub.darcs.net/raichoo) the maintainer of
  [hikari](https://hikari.acmelabs.space/)
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
the changes are in upstream, I obliterate everything to the checkpoint (tag) I
started with and pull the patches (now via `git`) from `project-tracking`. Or I
remove `project` and clone it again from `project-tracking`.

Since I always make git-commits from the darcs-patches `git` will track `chmod`
and symbolic-links for me.

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
  --help  Sow this message and exit.

Commands:
  clone   Locally clone a tracking repository to get a working-repository.
  update  Incremental import o git into darcs.
```

```
$> git-darcs update --help
Usage: git-darcs update [OPTIONS]

  Incremental import of git into darcs.

  By default it imports a shallow copy (the current commit). Use `--no-
  shallow` to import the complete history.

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

  Locally clone a tracking repository to get a working-repository.

Options:
  -v, --verbose / -nv, --no-verbose
  --help                          Show this message and exit.
```

Linearized history
------------------

After some trials I deemed my secret sauce:

```bash
git rev-list
    --reverse
    --topo-order
    --ancestry-path
```

the least confusing traversal option. It will follow an ancestry-path in
topo-order. But with parallel history the result is bad.

This:

```bash
$> git log -p .
commit 6723b82b4328bced84f1f761095683918e193e8f (HEAD -> master)
Merge: 5700f36 dde8155

    Merge branch 'b'

commit dde8155c5cd69613dbfe4d3da3a8de0ffa543ddc (b)

    b

diff --git a/b b/b
new file mode 100644
index 0000000..e69de29

commit 5700f36c30a5c6e5f783c0a685c1f97e266c232c (a)

    a

diff --git a/a b/a
new file mode 100644
index 0000000..e69de29

commit c40c0c924849baa89a074789eac82eea87d934bc

    start

diff --git a/start b/start
new file mode 100644
index 0000000..e69de29
```

becomes this:

```
$> darcs log -v
patch 0014c8c6d7255819e5dc6645e73cbfee985ac493
  tagged git-checkpoint 2022-09-03T23:34:09.731312 dde8155c5cd69613dbfe4d3da3a8de0ffa543ddc
    depend 6fb75f20aba30c5cf943572c53290cc6446741e4
      * dde8155 b
    depend fda79254573d7f1b3a50ea0e4a057a3b210d3284
      * 5700f36 a
    depend 46ac34b0119697fdae7e32329554367c30627b10
      * c40c0c9 start

patch 6fb75f20aba30c5cf943572c53290cc6446741e4
  * dde8155 b
    rmfile ./a
    addfile ./b

patch fda79254573d7f1b3a50ea0e4a057a3b210d3284
  * 5700f36 a
    addfile ./a

patch 46ac34b0119697fdae7e32329554367c30627b10
  * c40c0c9 start
    addfile ./start
```

The alternative is writing clever code that follows the tree structure and at
each fork follow one branch until a merge, then suspend, follow the other
branch. I 100% certain this also means we have to deal with conflichts.
