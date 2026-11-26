"""Public API: ``__version__`` and what the package exports.

Shared code of the USDA FAS sources. A source imports the gateway's names from here, in one line
of its ``_client.py``::

    from xippios.usda.fas import API_KEY_ENV, Gateway
"""

from xippios.usda.fas._version import __version__
from xippios.usda.fas.data_gov import API_KEY_ENV, REMAINING_HEADER, Gateway

__all__ = [
    "API_KEY_ENV",
    "REMAINING_HEADER",
    "Gateway",
    "__version__",
]
