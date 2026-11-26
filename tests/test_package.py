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


CORE = "xippios.core"
DYNAMIC = ("import_module", "__import__")
"""The functions that import a module by its dotted name, ``importlib``'s and the builtin."""


def _in_core(dotted: str) -> bool:
    return dotted == CORE or dotted.startswith(f"{CORE}.")


def _dotted(node: ast.expr) -> str | None:
    """``a.b.c`` for an attribute chain on a name, else ``None``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def _bound(tree: ast.Module) -> dict[str, str]:
    """Each name that an import of ``tree`` binds to a path of core, by that path.

    ``import xippios.core.client as c`` binds ``c``, ``from xippios.core import client``
    binds ``client`` and ``from xippios import core`` binds ``core``; ``import xippios.core``
    binds ``xippios``, which a chain then spells whole.
    """
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname and _in_core(alias.name):
                    bound[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}"
                if _in_core(dotted):
                    bound[alias.asname or alias.name] = dotted
    return bound


def _chain(dotted: str) -> str:
    """The part of a chain into core that its public lists judge.

    The longest public package that the chain begins with and the one name after it, or the
    chain itself where it names no more than core.
    """
    parts = dotted.split(".")
    depth = max(n for n in range(2, len(parts) + 1) if ".".join(parts[:n]) in _pinned())
    return ".".join(parts[: depth + 1])


def _found(tree: ast.Module) -> list[tuple[int, str]]:
    """Each read of core in ``tree``, its line and its dotted path or private member."""
    bound = _bound(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _in_core(node.module):
            found += [(node.lineno, f"{node.module}.{alias.name}") for alias in node.names]
        elif isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names if _in_core(alias.name)]
        elif isinstance(node, ast.Call):
            name = _dotted(node.func) or ""
            first = node.args[0] if node.args else None
            if (
                name.rpartition(".")[2] in DYNAMIC
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and _in_core(first.value)
            ):
                found.append((node.lineno, first.value))
        elif isinstance(node, ast.Attribute):
            private = node.attr.startswith("_") and not node.attr.startswith("__")
            own = isinstance(node.value, ast.Name) and node.value.id in ("self", "cls")
            chain = _dotted(node)
            if chain is not None:
                head, _, rest = chain.partition(".")
                dotted = f"{bound[head]}.{rest}" if head in bound else chain
                if dotted.startswith(f"{CORE}."):
                    found.append((node.lineno, _chain(dotted)))
                    continue
            if private and not own:
                found.append((node.lineno, f".{node.attr}"))
    return found


def _violations(source: str) -> list[str]:
    """Each read of core in ``source`` outside its public lists, ``<line>: <dotted>``.

    An import of a module or a name, a chain of attributes on a name that an import of core
    bound, and a dynamic import of a core module by its dotted name are judged by core's
    public lists. A member that starts with one underscore, read on anything but ``self`` or
    ``cls``, is found as such, ``.<name>``, since it reaches past an object's public names,
    the quota policy's ``_wait_left`` say. A chain is found once, though each of its inner
    attributes names it again.
    """
    lines = (
        f"{line}: {dotted}"
        for line, dotted in _found(ast.parse(source))
        if dotted.startswith(".") or _outside(dotted)
    )
    return list(dict.fromkeys(lines))


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
