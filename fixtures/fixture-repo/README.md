# Fixture repository

A deliberately tiny package with one planted bug: `add` subtracts.

The whole-loop test copies this tree, commits it, and lets the supervisor fix the bug with a
recorded harness trace. `test_add` fails on the base commit, which is what reproduction requires.
