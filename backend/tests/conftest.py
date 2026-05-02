"""Configuration pytest — active le mode asyncio pour tous les tests async."""
import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
