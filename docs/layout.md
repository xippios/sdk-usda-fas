# Layout

The files that every repository of the template's general shape holds are laid out once, in
sdk-template's README,
[The general part of a repository](https://github.com/xippios/sdk-template/blob/main/README.md#the-general-part-of-a-repository).
This file holds what `xippios-usda-fas` adds to them, a module, a script or a test of
its own, each with what it holds, and the change that adds one updates it.

The import path is `xippios.usda.fas` (sdk-core ADR-0006); `src/xippios/` is a
namespace package, and so is `src/xippios/usda/`, the provider level.

```
src/xippios/usda/fas/
  __init__.py        the gateway's public names, API_KEY_ENV, Gateway, NoDataForYear and
                     REMAINING_HEADER, and __version__
  _client.py         ENV_VARS: the gateway's key, which core's pytest plugin reads for its
                     placeholder
  data_gov.py        the api.data.gov gateway: its key, its documented answers as core's
                     errors and one quota policy per process for the key
  no_data.py         FAS's answer for a year without data, NoDataForYear, and the Gateway
                     that the package exports, the gateway with that answer
  portal.py          the kit of the FAS portal for the sources' snapshot scripts: Portal and
                     shell_text, imported from this module by scripts alone
tests/
  test_data_gov.py   the gateway's key, answers, quota and messages, offline
  test_no_data.py    FAS's empty 404 on a data path, through the exported Gateway
  test_portal.py     the kit's hooks, and core's frame run offline on a snapshot of the kit
  test_one_quota.py  two clients on the gateway in one process hold one quota policy
  test_client.py     ENV_VARS, and core's placeholder in the key's variable
  test_package.py    the version, the exports, the kit's names, and core imported by its public
                     lists alone
```
