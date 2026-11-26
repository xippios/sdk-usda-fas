- The api.data.gov gateway, `Gateway` with `API_KEY_ENV` and `REMAINING_HEADER`, which left
  `xippios-core` with its 0.5.0: the key in `DATA_GOV_API_KEY`, the gateway's documented
  answers as core's errors that name the request sent, and one quota policy per process for the
  key. A publisher's own answers come in through the gateway's `answers` hook.
  (sdk-core ADR-0065, https://github.com/xippios/sdk-core/issues/485)
