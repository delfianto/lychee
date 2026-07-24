"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client() -> TestClient:
    """A FastAPI TestClient bound to the app."""
    return TestClient(app)
