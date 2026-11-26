import ast
import subprocess
import sys
from functools import cache
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

import pytest

import xippios.usda.fas
from xippios.usda.fas import data_gov, no_data, portal

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
    # A source imports them in one line of its _client.py and its tasks.py,
    # ``from xippios.usda.fas import API_KEY_ENV, Gateway`` and ``NoDataForYear``.
    from xippios.usda.fas import API_KEY_ENV, REMAINING_HEADER, Gateway, NoDataForYear

    assert sorted(xippios.usda.fas.__all__) == [
        "API_KEY_ENV",
        "Gateway",
        "NoDataForYear",
        "REMAINING_HEADER",
        "__version__",
    ]
    assert API_KEY_ENV is data_gov.API_KEY_ENV
    assert REMAINING_HEADER is data_gov.REMAINING_HEADER
    assert Gateway is no_data.Gateway, "the gateway with FAS's answer for a year without data"
    assert issubclass(Gateway, data_gov.Gateway)
    assert NoDataForYear is no_data.NoDataForYear


def test_the_kit_s_names_are_its_module_s_alone() -> None:
    # A snapshot script imports them from xippios.usda.fas.portal, as it imports core's frame.
    assert portal.__all__ == ["Portal", "shell_text"]
    for name in (*portal.__all__, "_Part", "PORTAL_URL", "SHELL_NOTE", "MAX_SHELL_BYTES"):
        assert not hasattr(xippios.usda.fas, name), name


def test_the_package_s_root_loads_no_script_frame() -> None:
    # A source's runtime imports the root for its gateway; core's refresh frames are its
    # scripts' (sdk-core ADR-0062, decision 1), so the root imports nothing of them.
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, xippios.usda.fas; "
            "print(sorted(m for m in sys.modules if m.startswith('xippios.core.refresh')))",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert loaded.strip() == "[]"


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


def _imports(source: str) -> list[str]:
    """Each name or module that an import statement of ``source`` takes from core outside its
    public lists, ``<line>: <dotted>``.

    It reads the import statements alone, ``import xippios.core...`` and ``from xippios.core...
    import ...``. A private member read on an object of core, a chain of attributes and a
    dynamic import are not its matter.
    """
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
        pytest.param("from xippios.core import KeyAuth, QuotaPolicy\n", [], id="a public name"),
        pytest.param("from xippios.core.testing import CLOCK_SLACK\n", [], id="a public package's"),
        pytest.param("from xippios.core import client\n", [], id="a public package by name"),
        pytest.param("import xippios.core.client\n", [], id="import of a public package"),
        pytest.param(
            "from xippios.core.client import QuotaSnapshot\n",
            ["1: xippios.core.client.QuotaSnapshot"],
            id="a name outside a public package's list",
        ),
        pytest.param(
            "from xippios.core.client.quota import QuotaSnapshot\n",
            ["1: xippios.core.client.quota.QuotaSnapshot"],
            id="a name of a module below the lists",
        ),
        pytest.param(
            "from xippios.core.errors import AuthError\n",
            ["1: xippios.core.errors.AuthError"],
            id="a public name by a module below the lists",
        ),
        pytest.param(
            "import xippios.core.client.quota as q\n",
            ["1: xippios.core.client.quota"],
            id="a module below the lists by its alias",
        ),
        pytest.param(
            "import xippios.core._loop\n",
            ["1: xippios.core._loop"],
            id="a private module",
        ),
    ],
)
def test_an_import_outside_core_s_public_lists_is_found(source: str, found: list[str]) -> None:
    assert _imports(source) == found


def test_the_package_and_its_tests_import_core_by_its_public_lists_alone() -> None:
    """Every name that an import statement of the package or its tests takes from core stands in
    core's public lists, so the gateway imports no private name of core.

    It reads the import statements alone: a private member read on an object of core, the quota
    policy's say, is not its matter.
    """
    found = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")])
        if path != COLLECTS_THE_CHECK
        for line in _imports(path.read_text(encoding="utf-8"))
    ]
    assert found == []
    assert COLLECTS_THE_CHECK.read_text(encoding="utf-8") == (
        "from xippios.core.testing.built_answers import *  # noqa: F403\n"
    )
