"""Shared fixtures.

By default tests run against a temporary SQLite file. Set ``TEST_DATABASE_URL`` (for example
``postgresql://pdm:pdm@localhost:5432/pdm_test``) to run the same suite against PostgreSQL;
CI does this in a dedicated job.
"""
from __future__ import annotations

import os

import pytest

from app import create_app
from app.config import Config

ADMIN = {"Authorization": "Bearer test-admin-token"}


def _test_config(tmp_path, **overrides) -> Config:
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    base = dict(
        env="test",
        database_url=url,
        admin_token="test-admin-token",
        frontend_dir=str(os.path.join(os.path.dirname(__file__), "..", "..", "frontend")),
        enable_fault_injection=True,
    )
    base.update(overrides)
    return Config(**base)


@pytest.fixture()
def app(tmp_path):
    application = create_app(_test_config(tmp_path))
    yield application
    application.extensions["pdm_db"].reset()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin():
    return dict(ADMIN)


@pytest.fixture()
def make_app(tmp_path):
    """Factory for apps with custom config (e.g. fault injection disabled)."""
    created = []

    def _make(**overrides):
        application = create_app(_test_config(tmp_path, **overrides))
        created.append(application)
        return application

    yield _make
    for application in created:
        application.extensions["pdm_db"].reset()


@pytest.fixture()
def machine(client):
    resp = client.post("/api/machines", json={"code": "PUMP-001", "name": "Cooling pump", "machine_type": "pump", "location": "Plant A"})
    assert resp.status_code == 201
    return resp.get_json()
