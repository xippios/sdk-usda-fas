import ast
import importlib
from importlib.metadata import version
from pathlib import Path

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


def test_the_package_and_its_tests_import_core_by_its_public_lists_alone() -> None:
    found = []
    for path in sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]):
        if path == COLLECTS_THE_CHECK:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("xippios.core"):
                module = node.module or ""
                public = module in CORE_PUBLIC and importlib.import_module(module).__all__
                found += [
                    f"{path.relative_to(ROOT)}:{node.lineno} {module}.{alias.name}"
                    for alias in node.names
                    if not public or alias.name not in public
                ]
            elif isinstance(node, ast.Import):
                found += [
                    f"{path.relative_to(ROOT)}:{node.lineno} {alias.name}"
                    for alias in node.names
                    if alias.name.startswith("xippios.core") and alias.name not in CORE_PUBLIC
                ]
    assert found == []
    assert COLLECTS_THE_CHECK.read_text(encoding="utf-8") == (
        "from xippios.core.testing.built_answers import *  # noqa: F403\n"
    )
