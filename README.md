# xippios-usda-fas

Shared code of the USDA FAS sources, a package of the [xippios SDK family](https://github.com/xippios):
the code that the family's sources of USDA's Foreign Agricultural Service share,
`xippios-usda-psd`, `xippios-usda-esr` and `xippios-usda-gats`, which reach FAS's APIs through
the api.data.gov gateway. It registers no task, runs no server, wraps no API of its own and keeps
no upstream snapshot or fixture, and it depends on `xippios-core` alone. Its first record,
[ADR-0001](https://github.com/xippios/sdk-usda-fas/blob/main/docs/adr/0001-what-the-package-holds-and-the-api-data-gov-gateway.md),
says what it holds and never holds.

## What it holds

- **The api.data.gov gateway**, `xippios.usda.fas.data_gov`: the key in `DATA_GOV_API_KEY`,
  sent in the `X-Api-Key` header, the gateway's documented answers as `xippios-core` errors that
  name the request sent, and one quota policy per process for the key, so that every source on
  the key spends one quota. The module holds nothing of FAS: a publisher's own answers come in
  through its `answers` hook.
- **FAS's answer for a year without data**, `xippios.usda.fas.no_data`: `NoDataForYear`, for
  FAS's empty `text/plain` 404 on a source's data path, and the `Gateway` that the package
  exports, the gateway with that answer.
- **The kit of the FAS Open Data Services portal**, `xippios.usda.fas.portal`, with which each
  source's `scripts/refresh_upstream.py` declares its documentation snapshot on core's frame:
  `Portal(prefix)` for the source's service and `shell_text` for a shell page of its own.

A source imports the gateway's names from the package and the kit from its module:

```python
from xippios.usda.fas import API_KEY_ENV, Gateway, NoDataForYear, REMAINING_HEADER

gateway = Gateway(SOURCE, data_path=DATA_PATH)  # in _client.py, the source's own data paths

from xippios.usda.fas.portal import Portal  # in scripts/refresh_upstream.py alone

PORTAL = Portal("/api/esr/")
```

Importing the package loads none of core's script frames. A source depends on it by
`xippios-usda-fas~=0.1.0`, one minor.

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
- sdk-core: [docs/adr/0065-core-names-no-publisher.md](https://github.com/xippios/sdk-core/blob/main/docs/adr/0065-core-names-no-publisher.md) — the gateway's leaving of xippios-core, and the sections of the conventions that bind a publisher's shared package.
- sdk-usda-fas: [docs/adr.md](https://github.com/xippios/sdk-usda-fas/blob/main/docs/adr.md) — the index of this package's own decisions, generated from the records in `docs/adr/`.

## Licence

Apache-2.0. See [LICENSE](https://github.com/xippios/sdk-usda-fas/blob/main/LICENSE).
