git-darcs
=========

Just call `git-darcs`, git-darcs will import the history from the first commit.
It will remember (checkpoint) the last imported commit. If you call `git-darcs`
again it will import from the last checkpoint.

It will import a linearized version if the history, some patches might differ
from the original git-commit.

The tool intentionally very minimal, it is for devs how can read tracebacks or
change the code to fit better.
