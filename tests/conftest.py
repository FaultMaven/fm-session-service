"""Pytest configuration and fixtures for fm-session-service tests.

Provides shared fixtures for unit and integration tests.
"""

import asyncio
from typing import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
