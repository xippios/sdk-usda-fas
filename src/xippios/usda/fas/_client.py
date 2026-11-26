"""The variables the package reads, for a host (conventions §7).

The package keeps here, beside their declaration, the code that reads them, such as the auth
of a client that it shares.
"""

from xippios.core import EnvVar

API_KEY_ENV = "DATA_GOV_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
ENV_VARS: tuple[EnvVar, ...] = (EnvVar(API_KEY_ENV, secret=True, required=True),)
"""The variables the package reads, for a host (conventions §7; sdk-core ADR-0026, amendment
2026-11-18, point c). An ``EnvVar`` names a variable and reads none; a variable the package
reads beside these joins the list."""

__all__ = [
    "API_KEY_ENV",
    "ENV_VARS",
]
