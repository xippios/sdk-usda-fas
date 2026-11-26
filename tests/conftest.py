# Core's plugin keeps the default run offline (sdk-core ADR-0035) and runs anyio tests on
# asyncio.
pytest_plugins = ["xippios.core.testing.plugin"]
