"""``_client.py``: the variables the package reads, which core's pytest plugin reads too.

The package holds a key's code and no ``tasks.py``, so core's plugin finds it by its
``_client.py`` and sets the placeholder key in each secret variable of ``ENV_VARS`` in every
test not marked ``live`` (sdk-core ADR-0035, https://github.com/xippios/sdk-core/issues/538).
"""

import os

from xippios.core import EnvVar

from xippios.usda.fas import _client, data_gov


def test_env_vars_name_the_gateway_s_key_and_nothing_else() -> None:
    assert (EnvVar("DATA_GOV_API_KEY", secret=True, required=True),) == _client.ENV_VARS
    assert _client.API_KEY_ENV is data_gov.API_KEY_ENV, "one name, the gateway's"


def _holds(name: str, placeholder: str) -> bool:
    """Whether the variable holds the placeholder; it never returns or shows the value."""
    return os.environ.get(name) == placeholder


def test_core_s_plugin_sets_the_placeholder_in_the_key_s_variable(
    placeholder_api_key: str,
) -> None:
    # The fixture is core's: it returns the placeholder that it sets in the variables it finds.
    assert _holds(_client.API_KEY_ENV, placeholder_api_key), "found by _client.ENV_VARS"
