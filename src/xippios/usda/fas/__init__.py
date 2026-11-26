"""Public API: ``__version__`` and what the package exports.

Shared code of the USDA FAS sources. A source imports the gateway's names from here, in one line
of its ``_client.py``, and ``NoDataForYear`` in its tasks::

    from xippios.usda.fas import API_KEY_ENV, Gateway

``Gateway`` is api.data.gov's gateway with FAS's answer for a year without data (``no_data``);
the gateway alone, which holds nothing of FAS, is ``data_gov.Gateway``. The kit of the FAS
portal is the snapshot scripts', imported from ``xippios.usda.fas.portal`` as core's frame is
from ``xippios.core.refresh``: the root imports neither, so a source's runtime loads no script
frame.
"""

from xippios.usda.fas._version import __version__
from xippios.usda.fas.data_gov import API_KEY_ENV, REMAINING_HEADER
from xippios.usda.fas.no_data import Gateway, NoDataForYear

__all__ = [
    "API_KEY_ENV",
    "REMAINING_HEADER",
    "Gateway",
    "NoDataForYear",
    "__version__",
]
