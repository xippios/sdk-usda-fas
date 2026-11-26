# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [0.1.0] - 2026-11-26

### Added

- ADR-0001 records what the package holds and never holds, the api.data.gov gateway's
  decisions that left xippios-core with it, and how a source depends on the package. The
  README says what the package holds and gives a source's imports in its 30-second example.
  (sdk-core ADR-0065, https://github.com/xippios/sdk-core/issues/485)
- `NoDataForYear`, FAS's answer for a year that a data path holds no data for, which the
  exported `Gateway(source, data_path=...)` gives for FAS's empty `text/plain` 404 there,
  its text naming the request as the gateway's other messages do.
  (sdk-core ADR-0065, https://github.com/xippios/sdk-core/issues/106)
- `xippios.usda.fas.portal`, the kit of the FAS Open Data Services portal for the sources'
  snapshot scripts. `Portal(prefix)` gives the portal's pages, the hooks of core's snapshot
  frame and the capture's paragraphs for one service, and `shell_text` checks a shell page.
  (https://github.com/xippios/sdk-core/issues/485)
- The api.data.gov gateway, `Gateway` with `API_KEY_ENV` and `REMAINING_HEADER`, which left
  `xippios-core` with its 0.5.0: the key in `DATA_GOV_API_KEY`, the gateway's documented
  answers as core's errors that name the request sent, and one quota policy per process for the
  key. A publisher's own answers come in through the gateway's `answers` hook.
  (sdk-core ADR-0032, sdk-core ADR-0065, https://github.com/xippios/sdk-core/issues/485)
- Scaffold from [sdk-template](https://github.com/xippios/sdk-template), its general part
  of a repository: the package with its version, CI, the organization's checks, the
  decision records and the release train, in which a release PR's merge tags and
  publishes.
