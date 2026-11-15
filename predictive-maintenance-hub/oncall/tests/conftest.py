import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "tests"))

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from oncall_helpers import ADMIN_TOKEN, LiveHub  # noqa: E402


@pytest.fixture()
def hub_app(tmp_path):
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'oncall.db'}"
    app = create_app(Config(env="test", database_url=url, admin_token=ADMIN_TOKEN, enable_fault_injection=True,
                            frontend_dir=os.path.join(HERE, "..", "..", "frontend")))
    yield app
    app.extensions["pdm_db"].reset()


@pytest.fixture()
def live_hub(hub_app):
    with LiveHub(hub_app) as hub:
        yield hub
