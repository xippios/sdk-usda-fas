# sdk-usda-fas — instructions for Claude Code

`xippios-usda-fas`: Shared code of the USDA FAS sources, a package of the xippios SDK family, built
on `xippios-core`. This file holds what an agent needs to work on the package: its layout,
its commands and what only it knows. The documents it follows, sdk-core's conventions among
them, are listed under [`## Documents` in the README](README.md#documents); read them
before you change a file. The rules that no change breaks stand in
`.claude/rules/never.md`, which Claude Code loads with this file.

## Layout

What this package adds to the family's tree, and its import path, stand in `docs/layout.md`,
imported here:

@docs/layout.md

## Commands

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 -I scripts/adr_index.py --check   # the index matches the records in docs/adr/
```

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15). The
update never overwrites a file this package fills, those that `_skip_if_exists` lists in
sdk-template's [`copier.yml`](https://github.com/xippios/sdk-template/blob/main/copier.yml),
and sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

The update writes every other file it renders again, since they are the template's,
`.claude/rules/never.md` among them. This package keeps no text of its own in them: its own
words go into a file it fills. `pyproject.toml` is one it fills, its manifest once rendered,
so no update changes its dependencies, its scripts or its bound of `xippios-core`, which an
adoption of a core minor raises there by hand.

## What only this package knows

<!-- What only this package knows: its modules' purpose, the packages that use it, sections of its own. Fill this section or delete it. -->
