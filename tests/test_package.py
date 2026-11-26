from importlib.metadata import version

import xippios.usda.fas


def test_the_package_imports_with_its_distributions_version() -> None:
    assert xippios.usda.fas.__version__ == version("xippios-usda-fas")
