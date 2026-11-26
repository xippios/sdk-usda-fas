"""The variables the package reads, for a host (conventions §7).

The one variable is the key of api.data.gov's gateway, which every source behind the gateway
reads (sdk-core ADR-0032). The code that reads it is the gateway's ``auth``, in ``data_gov.py``
with the name of the variable, so that the gateway's module stands alone; this file declares
the variable, and core's pytest plugin finds the package by this file and sets the placeholder
key in it offline (sdk-core ADR-0035).
"""

from xippios.core import EnvVar

from xippios.usda.fas.data_gov import API_KEY_ENV

ENV_VARS: tuple[EnvVar, ...] = (EnvVar(API_KEY_ENV, secret=True, required=True),)
"""The variables the package reads, for a host (conventions §7; sdk-core ADR-0026, amendment
2026-11-18, point c). An ``EnvVar`` names a variable and reads none; a variable the package
reads beside these joins the list."""

__all__ = [
    "API_KEY_ENV",
    "ENV_VARS",
]
