# Repo Notes for Claude

This repository is the PRISM specification: the modality schemas, the term registry
and the specification pages. PRISM Studio and the `prism-validator` carry a
hash-locked copy of a tagged release; change things here, tag a release, never edit
the copy there.

## Mandatory skills for every chat in this repo

At the start of every conversation in this repository, invoke both of the
following skills before doing any other work:

- `ponytail` (ponytail:ponytail) — lazy-senior-dev mode: prefer the
  minimal, boring solution (YAGNI, reuse existing code, stdlib/native
  features before new dependencies) for any coding task.
- `superpowers` (superpowers:using-superpowers) — establishes which other
  superpowers skills (brainstorming, systematic-debugging,
  test-driven-development, etc.) apply to the task at hand, and requires
  invoking them before responding.

Use ponytail and the superpowers skills whenever they apply, regardless of how
trivial the request looks.

## Always use TDD

For every feature or bug fix, invoke `superpowers:test-driven-development`
and follow it: first the test, then the code. Write a failing test that
reproduces the problem, watch it fail, then write the fix. For bugs, also invoke
`superpowers:systematic-debugging` before proposing a fix. Don't write the
test after the fix; a test that never failed proves nothing.

## One implementation: every command is a CLI command, a GUI only triggers it

Every feature (the checks, the generator, anything a user can do with this
specification) is a command: its logic is implemented once, under `scripts/`, and
runs from the command line. A GUI (for example a future schema-annotation tool) is a
thin adapter that runs that same command or function; it must never carry its own copy
of the logic. A feature is not done until it works from the command line with the
same options the GUI offers.
