Incremental import of git into darcs and back again
====================================================

[![Test](https://github.com/ganwell/git-darcs/actions/workflows/test.yml/badge.svg)](https://github.com/ganwell/git-darcs/actions/workflows/test.yml) [![CodeQL](https://github.com/ganwell/git-darcs/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/ganwell/git-darcs/actions/workflows/codeql-analysis.yml)

[git-darcs on pypi](https://pypi.org/project/git-darcs/)

- [Warning](#-warning)
- [Tutorial](#Tutorial)
- [But why?](#but-why)
- [For darcs beginners](#for-darcs-beginners)
- [Caveats](#caveats)
  * [Performance](#performance)
  * [chmod and symbolic-links](#chmod-and-symbolic-links)
  * [Linearized History](#linearized-history)
- [Usage](#usage)

⚠ Warning
=========

git-darcs needs a repository only for tracking. Don't use your working
git-repository. git-darcs will clear all your work that is not commited. It also
needs to temporarily change `.gitignore` and `_darcs/pref/boring`. By default it
will warn about this. You can add `-nw` to avoid the warning. The tutorial never
contains a `-nw`, so people don't copy-paste from the tutorial and lose their
work.

The tool is made for developers, while error-handling is okayish, there is
almost no error-reporting, you'll have to read the traceback.

![demo](https://github.com/ganwell/git-darcs/blob/main/demo.gif?raw=true)

Tutorial
========

Clone your tracking-repository.

```bash
$> git clone https://github.com/adfinis-sygroup/document-merge-service.git dms-track
Cloning into 'document-merge-service'...

.....

Resolving deltas: 100% (1267/1267), done.
```

Lazily import the git-repository to darcs.

```bash
$> git darcs update
Use CTRL-D for a graceful shutdown.
```

git-darcs will import the latest commit and tag it, so it can update from there,
when you pull commits from upstream.

```bash
$> (cd dms-track; darcs log)
patch 7997a3365da1022db4b669ea63a37dc3f370a225
Author: Jean-Louis Fuchs <email>
Date:   Fri Oct  7 17:40:10 CEST 2022
  tagged git-checkpoint 2022-10-07T17:40:10.963827
d3ce714f2d77897e773e89ee3344602fceb1b625

patch 4e917fcc769b7a69858e0b11e7ee5aaffc76fbda
Author: Jean-Louis Fuchs <email>
Date:   Fri Oct  7 17:40:10 CEST 2022
  * d3ce714 chore(release): v5.0.0
```

Create the work-repository. Note that git and darcs make sure that no historical
data is duplicated on disk (using hardlinks).

```bash
$> git darcs clone dms-track/ dms-work
clone: 100%|████████████████████████████████████████████████| 5/5 [00:00<00:00, 37.75it/s]
```

Now you can implement a new feature.

```bash
$> cd dms-work
$> touch document_merge_service/feature.py
$> darcs add document_merge_service/feature.py
Adding './document_merge_service/feature.py'
Finished adding:
./document_merge_service/feature.py

$> darcs record -m "a new feature"
addfile ./document_merge_service/feature.py
Shall I record this change? (1/1)  [ynW...], or ? for more options: y
Do you want to Record these changes? [Yglqk...], or ? for more options: y
Finished recording patch 'a new feature'
```

```bash
darcs show dependencies | dot -Tpdf -Grankdir=TB -o $ftmp
```

![first record](https://github.com/ganwell/git-darcs/blob/main/_static/first.png?raw=true)

There are new changes on upstream, let's pull them in.

```bash
$> cd ../dms-track/
$> git pull
Updating d3ce714..a6a8e35
Fast-forward
 .github/workflows/tests.yml                         |  6 ++++-
 
.....
 
 18 files changed, 262 insertions(+), 67 deletions(-)
```

From now on git-darcs will import every commit, but with a linearized
history. That means the history might look different than in git, but no change will be
forgotten. (See [Linearized History](#linearized-history))

```bash
$> git darcs update
Use CTRL-D for a graceful shutdown.
commits:
100%|███████████████████████████████████████████████████████| 18/18 [00:00<00:00, 19.14it/s]
```

We pull the new patches into `dms-work`.

```bash
$> cd ../dms-track/
$> darcs pull ../dms-track/
Pulling from "/home/jeanlf/Temp/dms-track"...
patch 309682700e7142e37945c45cc3375674012e8050
Author: GitHub <noreply@github.com>
Date:   Fri Oct  7 18:07:08 CEST 2022
  * 85892f6 fix(docker): fix docker uwsgi command
Shall I pull this patch? (1/19)  [ynW...], or ? for more options: a
Finished pulling.
```

The 18 patches we pulled are now in `dms-work` along with a new snapshot-tag.

```bash
$> darcs log --from-tag=.
patch 430136524b02be562fdf0f0459594ffa981d386b
Author: Jean-Louis Fuchs <email>
Date:   Fri Oct  7 18:07:09 CEST 2022
  tagged git-checkpoint 2022-10-07T18:07:09.041126 a6a8e35ae3c3b42b04837a75ff59aa092130f326

patch ef1f2894abd21d0deef19090d4b873bf62af890a
Author: Jean-Louis Fuchs <email>
Date:   Fri Oct  7 17:55:22 CEST 2022
  * a new feature
```

We can now either pull the `a new feature`-patch into `dms-track` or we can
create a temporary `dms-stage` so it is easier to clean up after the
merge-request has been accepted. Note `git-darcs clone` will copy git-remotes
from the source, so you can push into your fork if it is set up.

If you pull into `dms-track` instead, you have to remove patches or commits on
both darcs and git, keeping darcs and git manually in sync.


```bash
$> cd ..
$> git darcs clone dms-track/ dms-stage
clone: 100%|████████████████████████████████████████████████| 5/5 [00:00<00:00, 48.32it/s]
$> cd dms-stage
```

`git-darcs pull` tries to emulate `darcs pull`.

```bash
$> git darcs pull ../dms-work/
patch ef1f2894abd21d0deef19090d4b873bf62af890a
Author: Jean-Louis Fuchs <email>
Date: 2022-10-07 15:55:22
Subject: a new feature
Shall I pull this patch? 1/1  [ynwasc], or ? for more options: ?

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

Shall I pull this patch? 1/1  [ynwasc], or ? for more options: y
resolve: 0it [00:00, ?it/s]
Shall I pull 1 patches?   [yn], or ? for more options: y
pull: 100%|█████████████████████████████████████████████████| 1/1 [00:00<00:00,  2.58it/s]
```

The patch `a new feature` is now a git-commit.

```bash
$> git show
commit c2541c6c3527d99a7fe69dc43b5863992d919a45 (HEAD -> main)
Author: Jean-Louis Fuchs <email>
Date:   Fri Oct 7 20:01:22 2022 +0200

    a new feature

diff --git a/document_merge_service/feature.py b/document_merge_service/feature.py
new file mode 100644
index 0000000..e69de29
```

```bash
$> cd ..
$> rm -r dms-stage
```

But why?
========

I prefer to group changes by topic, so I am constantly amending commits/patches.
This is very easy in darcs and more complicated in git. Yes, I know about
`--fixup` and `--autosquash` in git. Also I can find independent low-risk
patches easily with `darcs show dependencies`, so I can constantly make MRs.
Making the final _breaking_ change/MR much smaller. This is less tedious for the
reviewers.

For darcs beginners
===================

* There is a great [video](https://hikari.acmelabs.space/videos/hikari-darcs.mp4) by
  [raichoo](https://hub.darcs.net/raichoo) the maintainer of
  [hikari](https://hikari.acmelabs.space/)
* You have to read the [darcs book](https://darcsbook.acmelabs.space/), you just
  have to
* `_darcs/pref/boring` is the equivalent of `.gitignore`, but has quite a wide
  definition of boring by default

Caveats
=======

Performance
-----------

git-darcs will playback the history of the git-repository. Every commit that is
recorded will first be checked out in git and then recorded in darcs. For that reason
git-darcs lazily imports the latest commit by default. This is how it is meant
to be used: Using darcs to complement git. You can use it to convert
repositories, if you like the way non-linear history is handled, it will be
sloooow. See also `darcs convert import`.

chmod and symbolic links
------------------------

Darcs does not handle `chmod` or symbolic links. The easiest way to work around
this is by  letting `git` do the work. Since I always make git-commits from the
darcs-patches `git` will track `chmod` and symbolic links for me.

Linearized History
------------------

git-darcs will traverse the git-history in topological order. For every commit
it encounters, it will test if the previous commit was an ancestor, if not it
will ignore that commit for now. That way git-darcs can only "enter" one branch
of parallel history. Once it reaches a commit that is an ancestor it will import
that commit and log the complete history between it and the last successful
commit. So git-darcs creates patches that combine the complete history of a
parallel branch.

This git-log

```
$> git log --oneline --graph
* eef24d8 (HEAD -> master) end > end0
* 841c900 end
*   969ad57 Merge branch 'b'
|\
| * 76ca538 (b) bb2 > bb3
| * 0040cee bb1 > bb2
* | 663168a antiforward > antiforward0
* |   0d94733 Merge branch 'a'
|\ \
| * | d26d325 (a) aa2 > aa3
| * | 8090696 aa1 > aa2
| |/
* / fa7accb antiforward
|/
* 7bc2b76 aa0 > aa1, bb0 > bb1
* 665937d aa > aa0, bb bb0
* 1fd0236 aa, bb
```

becomes this darcs-log

```
* eef24d8 end > end0
    move ./end ./end0
* 841c900 end
    addfile ./end
* 969ad57 Merge branch 'b'
  76ca538 bb2 > bb3
  0040cee bb1 > bb2
    move ./bb1 ./bb3
* 663168a antiforward > antiforward0
    move ./antiforward ./antiforward0
* 0d94733 Merge branch 'a'
  d26d325 aa2 > aa3
  8090696 aa1 > aa2
    move ./aa1 ./aa3
* fa7accb antiforward
    addfile ./antiforward
* 7bc2b76 aa0 > aa1, bb0 > bb1
    move ./aa0 ./aa1
    move ./bb0 ./bb1
* 665937d aa > aa0, bb bb0
    move ./aa ./aa0
    move ./bb ./bb0
* 1fd0236 aa, bb
    addfile ./aa
```

See how `0d94733 Merge branch 'a'` also contains `d26d325` and `0d94733`.

Usage
=====

```
$> git-darcs --help
Usage: git-darcs [OPTIONS] COMMAND [ARGS]...

  Click entrypoint.

Options:
  --help  Sow this message and exit.

Commands:
  clone   Locally clone a tracking-repository to get a working-repository.
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
  -w, --warn / -nw, --no-warn     Warn that repository will be cleared
  -b, --base TEXT                 On first update import from (commit-ish)
  -s, --shallow / -ns, --no-shallow
                                  On first update only import current commit
  --help                          Show this message and exit.
```

```
$> git-darcs clone --help
Usage: git-darcs clone [OPTIONS] SOURCE DESTINATION

  Locally clone a tracking-repository to get a working-repository.

Options:
  -v, --verbose / -nv, --no-verbose
  --help                          Show this message and exit.
```

```
$> git-darcs pull --help
Usage: git-darcs pull [OPTIONS] SOURCE [DARCS]...

  Pull from source darcs-repository into a tracking-repository.

  A tracking-repository is created by `git darcs update` and contains a git-
  and a darcs-repository. Arguments after `--` are passed to `darcs pull`.

Options:
  -v, --verbose / -nv, --no-verbose
  -w, --warn / -nw, --no-warn     Warn that repository will be cleared
  -a, --all / -na, --no-all       Pull all patches
  -i, --ignore-temp / -ni, --no-ignore-temp
                                  Ignore temporary patches (with 'temp: ')
  --help                          Show this message and exit.
```
