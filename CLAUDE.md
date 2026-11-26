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

- The three FAS sources depend on it, `xippios-usda-psd`, `xippios-usda-esr` and
  `xippios-usda-gats`, each by one minor, and adopt a breaking minor of it together. A public
  name of the package needs two consumers among them. Its root exports the gateway's names
  alone, `API_KEY_ENV`, `Gateway`, `NoDataForYear` and `REMAINING_HEADER`, and the kit's names,
  `Portal` and `shell_text`, stay in `xippios.usda.fas.portal`, which a snapshot script imports,
  so a source's runtime loads no script frame.
- `data_gov.py` holds nothing of FAS and imports nothing of the package; FAS's own answer
  stands in `no_data.py`. ADR-0001 holds the gateway's decisions that left xippios-core.
- The gateway words its refusal of a 429 from the quota policy's public names alone and holds
  its wait to the one the policy sets, and its messages name the request by core's
  `request_description`. The test of core's public lists reads the import statements alone.
- The kit's hooks read a document that they write with core's `read_json`, and one that they
  only note with `parse_json`; its capture states its own check of a shell.
