import ast
from functools import cache
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

import pytest

import xippios.usda.fas
from xippios.usda.fas import data_gov

ROOT = Path(__file__).resolve().parents[1]
CORE_PUBLIC = (
    "xippios.core",
    "xippios.core.client",
    "xippios.core.http",
    "xippios.core.mcp",
    "xippios.core.refresh",
    "xippios.core.testing",
)
"""Core's packages whose ``__all__`` its tests pin as what consumers import (sdk-core
``tests/test_public_surface.py``)."""
COLLECTS_THE_CHECK = ROOT / "tests" / "test_built_answers.py"
"""The one file that imports below them: it collects core's built-answer check with the
template's one line, ``from xippios.core.testing.built_answers import *``."""


def test_the_package_imports_with_its_distributions_version() -> None:
    assert xippios.usda.fas.__version__ == version("xippios-usda-fas")


def test_the_package_exports_the_gateway_s_names_from_itself() -> None:
    # A source imports them in one line of its _client.py,
    # ``from xippios.usda.fas import API_KEY_ENV, Gateway``.
    from xippios.usda.fas import API_KEY_ENV, REMAINING_HEADER, Gateway

    assert sorted(xippios.usda.fas.__all__) == [
        "API_KEY_ENV",
        "Gateway",
        "REMAINING_HEADER",
        "__version__",
    ]
    assert API_KEY_ENV is data_gov.API_KEY_ENV
    assert REMAINING_HEADER is data_gov.REMAINING_HEADER
    assert Gateway is data_gov.Gateway


@cache
def _pinned() -> dict[str, frozenset[str]]:
    """The ``__all__`` of each of core's public packages, read by ``ast``, never imported.

    ``xippios.core.mcp`` and ``xippios.core.http`` need extras that the package does not
    install, so no list is imported.
    """
    spec = find_spec("xippios.core")
    assert spec is not None
    assert spec.origin is not None
    root = Path(spec.origin).parent
    pinned: dict[str, frozenset[str]] = {}
    for package in CORE_PUBLIC:
        init = root.joinpath(*package.split(".")[2:], "__init__.py")
        [names] = [
            ast.literal_eval(node.value)
            for node in ast.parse(init.read_text(encoding="utf-8")).body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
        ]
        pinned[package] = frozenset(names)
    return pinned


def _outside(dotted: str) -> bool:
    """Whether a dotted path of core leaves its public lists.

    Within them: a public package, or a name of a public package's ``__all__``.
    """
    pinned = _pinned()
    if dotted in pinned:
        return False
    module, _, name = dotted.rpartition(".")
    return module not in pinned or name not in pinned[module]


def _violations(source: str) -> list[str]:
    """Each read of core in ``source`` outside its public lists, ``<line>: <dotted>``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("xippios.core"):
            found += [f"{node.lineno}: {node.module}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Import):
            found += [
                f"{node.lineno}: {alias.name}"
                for alias in node.names
                if alias.name.startswith("xippios.core")
            ]
    return [line for line in found if _outside(line.split(": ", 1)[1])]


@pytest.mark.parametrize(
    ("source", "found"),
    [
        pytest.param("from xippios.core import KeyAuth, QuotaPolicy\n", [], id="the root"),
        pytest.param("from xippios.core.testing import CLOCK_SLACK\n", [], id="a public package"),
        pytest.param("from xippios.core import client\n", [], id="a public package by name"),
        pytest.param("import xippios.core.client\n", [], id="import of a public package"),
        pytest.param(
            "import xippios.core.client\nxippios.core.client.QuotaPolicy\n",
            [],
            id="a public name by its chain",
        ),
        pytest.param(
            "from xippios.core import QuotaPolicy\nQuotaPolicy.snapshot\n",
            [],
            id="a public method of a public name",
        ),
        pytest.param(
            "class G:\n    def f(self):\n        return self._spent_for()\n",
            [],
            id="a private name of the class's own on self",
        ),
        pytest.param(
            "from xippios.core.client.quota import QuotaSnapshot\n",
            ["1: xippios.core.client.quota.QuotaSnapshot"],
            id="a name of a module below the lists",
        ),
        pytest.param(
            "from xippios.core.errors import AuthError\n",
            ["1: xippios.core.errors.AuthError"],
            id="a public name by its module",
        ),
        pytest.param(
            "import xippios.core.client.quota as q\n",
            ["1: xippios.core.client.quota"],
            id="a module below the lists by its alias",
        ),
        pytest.param(
            "from xippios import core\ncore.client.quota._TEN_YEARS\n",
            ["2: xippios.core.client.quota"],
            id="a chain on core imported from the namespace",
        ),
        pytest.param(
            "import xippios.core\nxippios.core.client.quota._PAUSE_CAP\n",
            ["2: xippios.core.client.quota"],
            id="a chain on core imported whole",
        ),
        pytest.param(
            "import importlib\nimportlib.import_module('xippios.core.client.quota')\n",
            ["2: xippios.core.client.quota"],
            id="a dynamic import of a module below the lists",
        ),
        pytest.param(
            "from importlib import import_module\nimport_module('xippios.core.client.quota')\n",
            ["2: xippios.core.client.quota"],
            id="a dynamic import by the bare function",
        ),
        pytest.param(
            "def f(policy, now):\n    return policy._wait_left(policy.snapshot(), now)\n",
            ["2: ._wait_left"],
            id="a private member of another object",
        ),
        pytest.param(
            "class G:\n    def f(self):\n        return self.policy._clock()\n",
            ["3: ._clock"],
            id="a private member of an attribute of self",
        ),
    ],
)
def test_a_read_of_core_outside_its_public_lists_is_found(source: str, found: list[str]) -> None:
    assert _violations(source) == found


def test_the_package_and_its_tests_import_core_by_its_public_lists_alone() -> None:
    found = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")])
        if path != COLLECTS_THE_CHECK
        for line in _violations(path.read_text(encoding="utf-8"))
    ]
    assert found == []
    assert COLLECTS_THE_CHECK.read_text(encoding="utf-8") == (
        "from xippios.core.testing.built_answers import *  # noqa: F403\n"
    )
