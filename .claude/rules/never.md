# Never

What no change of `xippios-usda-fas` does, whoever makes it. The template writes this
file again at every update, so a rule of the package's own goes into `CLAUDE.md`.

- Never read or print `.envrc`, `.env`, the credential variable of this package,
  `DATA_GOV_API_KEY`, or any variable ending in `_API_KEY`, `_TOKEN` or
  `_SECRET`.
- Never write a key, a token or another credential into a file or a commit.
- Never add `src/xippios/__init__.py`, nor an `__init__.py` at a level between it and the
  package (sdk-core ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone (conventions §12).
