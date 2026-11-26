# ADR-0001: What the package holds, and the api.data.gov gateway that left xippios-core

Status: Accepted · Date: 2026-11-26 · Decided by https://github.com/xippios/sdk-core/issues/485

## Context

Three sources of the xippios SDK family wrap APIs of USDA's Foreign Agricultural Service (FAS)
behind the api.data.gov gateway: `xippios-usda-psd`, `xippios-usda-esr` and `xippios-usda-gats`.
Until its 0.5.0 `xippios-core` held the gateway as `xippios.core.data_gov`, and each source's
snapshot script carried its own copy of the code that reads FAS's documentation portal.

sdk-core's ADR-0065 moved the gateway here
(https://github.com/xippios/sdk-core/blob/v0.5.0/docs/adr/0065-core-names-no-publisher.md). Its
decision 1 has this package's first record hold the gateway's own decisions, decision 5 of
sdk-core's ADR-0032 as it stands, while ADR-0032's other decisions, one key variable for each
issuer among them, stay core's. Its decision 3 says what a publisher's shared package is, how a
source depends on one, and which sections of sdk-core's conventions bind it. The maintainer
decided the package's scope and the gateway's leaving on 2026-11-24.

## Decision

1. **What the package holds.** The facts of one publisher that two or more of its sources share
   and that cannot be written without the publisher's name, and the code that reads them: the
   api.data.gov gateway (`data_gov`), FAS's answer for a year without data (`no_data`) and the
   kit of the FAS Open Data Services portal (`portal`). It holds no task, no model of an
   answer, no list and no server, and nothing that joins or aligns the three services: their
   lists, their models and their checks of a code stay in their sources. It depends on
   `xippios-core` alone (sdk-core ADR-0065, decision 3).
2. **The gateway's decisions**, decision 5 of sdk-core's ADR-0032 as it stands at v0.5.0
   (https://github.com/xippios/sdk-core/blob/v0.5.0/docs/adr/0032-one-key-per-issuer-for-shared-gateways.md),
   moved here by sdk-core's ADR-0065, decision 1:
   - The key comes from `DATA_GOV_API_KEY` and goes out in the `X-Api-Key` header, sent by
     core's one key class with the slug of the source that builds the gateway. The variable is
     the issuer's by sdk-core's ADR-0032, decision 1, which stays core's.
   - `classify` maps the gateway's documented answers to core's errors in the source's name: a
     401 or 403 with an `API_KEY_*` code to `AuthError`, a 429 to `RateLimitError` and the
     gateway's `NOT_FOUND` to `NotFoundError`. It reads the gateway's own answers alone and
     returns `None` for the answer to a request that the client marked as sent to another
     origin than its base URL's (sdk-core ADR-0037, decision 4).
   - `Gateway.policy` is one quota policy per process for the key in `DATA_GOV_API_KEY`, which
     every source in that process shares: a quota one of them spends, the next request of
     another waits out or is refused without being sent (sdk-core ADR-0033, decision 4). It
     reads `x-ratelimit-limit` and `x-ratelimit-remaining`, counts a rolling hour, and keeps
     the wait of a 429 from its `Retry-After`, else one hour (sdk-core ADR-0033, decision 3).
     Separate processes keep a snapshot each.
   - `Gateway` takes no key of its own: a key passed to a source's client still draws on
     `Gateway.policy`'s snapshot, and a caller with a key of its own, a separate quota, builds
     its own core key class and `QuotaPolicy`.
   - FAS's answer for a market year that a data path holds no data for, HTTP 404 with an empty
     `text/plain` body, is `NoDataForYear`, a `NotFoundError` with the request's path, given by
     the `Gateway` that the package exports to a source that names its data paths,
     `Gateway(source, data_path=...)`. Any other empty 404 and the gateway's `NOT_FOUND` are
     left to the source and to core.
3. **Where the package differs from ADR-0032's decision 5.** The gateway's module holds nothing
   of FAS: FAS's rule stands beside it in `no_data`, as the publisher's answers that the
   gateway's `answers` hook takes, so the gateway could serve another agency's source. The
   refusal of a 429 reads the quota policy's public names alone, `snapshot()`, `window`, the
   clock that the module hands the policy and `parse_retry_after` (sdk-core ADR-0065,
   decision 2). Each of the gateway's messages names the request it answers by core's
   `request_description` (conventions §5), and a code that the gateway sends without a message
   is quoted alone (https://github.com/xippios/sdk-usda-fas/issues/7).
4. **The kit of the portal.** `xippios.usda.fas.portal` gives a source's snapshot script
   `Portal(prefix)`, the portal's pages, the hooks of core's snapshot frame and the paragraphs
   of the capture for one of its three services, and `shell_text` for a source's own shell
   page. Scripts import it from its module, and the package's root imports none of core's
   script frames. Its wording of a capture
   (https://github.com/xippios/sdk-usda-fas/issues/8), the absent definition its cut names
   (https://github.com/xippios/sdk-usda-fas/issues/9) and its refusal of a document without an
   `info` object (https://github.com/xippios/sdk-usda-fas/issues/10) stand as those rows
   record them.
5. **What does not enter in 0.1.0.** `naive_time` stays sdk-usda-esr's: it has one consumer,
   and part 4 of the answer on https://github.com/xippios/sdk-core/issues/473 returned it to that
   source. By decision 1 of this record, a fact of the publisher enters the package once two of
   its sources share it.
6. **How a source depends on it.** By `xippios-usda-fas~=0.1.0`, one minor, as sdk-core's
   ADR-0021, decision 1, bounds a dependency, with the package's public names in the place of
   a task layer (sdk-core ADR-0065, decision 3). The package and its sources share one core
   minor, and the package releases on it first. The three sources adopt a breaking minor of
   the package together, since the host installs them with `>=` lower bounds (sdk-core
   ADR-0021, amendment 2026-10-29, point 4), so that the latest of the three install beside one
   minor of it.

## Consequences

- A source imports `API_KEY_ENV` and `Gateway` from `xippios.usda.fas` in its `_client.py`,
  `NoDataForYear` in its tasks and `REMAINING_HEADER` in its reference script, and its snapshot
  script imports the kit from `xippios.usda.fas.portal`.
- A change of a public name is a breaking minor of the package, which the three sources adopt
  together.
- Conventions §1, §5, §6, §7, §10, §11, §12, §13 and §15 bind the package where it holds what
  their rules name, without `docs/upstream/`, and no other section does (sdk-core ADR-0065,
  decision 3).
- A later decision that changes one of decision 2's facts amends this record.
