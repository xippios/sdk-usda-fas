# xippios-usda-fas

Shared code of the USDA FAS sources, a package of the [xippios SDK family](https://github.com/xippios).

## Install

```bash
uv add xippios-usda-fas
```

## Workflows

`ci.yml` runs ruff, its format check, mypy, pytest and pre-commit on Python 3.12, 3.13 and
3.14, requires a changelog entry of every pull request but Dependabot's and refuses a
fixture file over 256 KiB that a pull request adds or changes. It runs on every pull request and,
called by `publish.yml`, once for a release, and its job `ci` is the check the
organization's ruleset requires. It is handed no secret, and no variable switches it off.

`publish.yml` is the release train (conventions §12): on a push to `main` whose
`pyproject.toml` names a version that has no tag yet and has its section in `CHANGELOG.md`,
it runs `ci.yml`, refuses a core pinned to git, tags the merge commit, builds the package
and, once a reviewer of the environment `pypi` approves the run, publishes it to PyPI by
trusted publishing. Every push to `main` and a dispatch start it, and a push that brings no
release ends quietly. It is handed no secret: the step that tells a release is handed the
job's token as `GH_TOKEN`, the tag goes with the job's token and PyPI trusts the workflow
itself. Its job `tag` holds the one checkout of the repository that keeps its credentials,
since it pushes the tag with the job's token; every other checkout sets
`persist-credentials: false` (conventions §13). No variable switches it off.

`conventions.yml` calls the organization's review of a pull request against the documents
listed under Documents below, the check `conventions / conventions`, when a pull request
opens, is pushed to, reopens or is edited, and on a push to `main` or a dispatch the review
of the range of commits, `range / range`. It hands the review the organization's
secret of the model's key, by name. A variable `WORKFLOW_CONVENTIONS` of `off`, the
repository's over the organization's, switches both off.

`adr-index.yml` calls the organization's check of the ADR index, `adr-index / adr-index`,
which runs `scripts/adr_index.py --check`, when a pull request opens, is pushed to or
reopens. It hands over nothing, and the called workflow reads its switch itself: a variable
`WORKFLOW_ADR_INDEX` of `off`, the repository's over the organization's, skips the check.

`siblings.yml` runs `.github/scripts/check-siblings.sh`, which installs the wheel beside
every sibling on PyPI under the same provider namespace that shares its core minor and
beside the source packages it depends on, and proves that the namespace levels stay portions
(sdk-core ADR-0006, sdk-core ADR-0021). It runs on every pull request and push to `main`, a
check the ruleset does not require, in a workflow of its own, since `ci.yml` is core's file,
which `publish.yml` calls for a release. It hands the script the job's read-only token as
`GITHUB_TOKEN`, for the listing of the organization's repositories, since GitHub limits the
calls of a runner without one. A variable `WORKFLOW_SIBLINGS` of `off`, the repository's
over the organization's, switches it off.

## Documents

- sdk-core: [docs/conventions.md](https://github.com/xippios/sdk-core/blob/main/docs/conventions.md) — the conventions every xippios source package follows: its layout, names, results, tests and releases.
- sdk-core: [docs/adr.md](https://github.com/xippios/sdk-core/blob/main/docs/adr.md) — the index of the family's architecture decisions, which the conventions cite.
- sdk-core: [docs/definition-of-done.md](https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md) — what a change satisfies before its pull request is opened.
- sdk-core: [docs/review-checklist.md](https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md) — what the review of a pull request checks, in order.
- sdk-usda-fas: [docs/adr.md](https://github.com/xippios/sdk-usda-fas/blob/main/docs/adr.md) — the index of this package's own decisions, generated from the records in `docs/adr/`.

## Licence

Apache-2.0. See [LICENSE](https://github.com/xippios/sdk-usda-fas/blob/main/LICENSE).
