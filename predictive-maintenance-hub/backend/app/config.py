"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEV_ADMIN_TOKEN = "dev-admin-token"


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    env: str = "development"
    database_url: str = "sqlite:///data/pdm.db"
    admin_token: str = DEV_ADMIN_TOKEN
    service_name: str = "pdm-hub"
    telemetry_retention_hours: int = 24
    frontend_dir: str = ""
    enable_fault_injection: bool = True
    seed_demo_data: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        env = os.getenv("APP_ENV", "development")
        default_frontend = str(Path(__file__).resolve().parents[2] / "frontend")
        cfg = cls(
            env=env,
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            admin_token=os.getenv("ADMIN_TOKEN", DEV_ADMIN_TOKEN),
            service_name=os.getenv("SERVICE_NAME", "pdm-hub"),
            telemetry_retention_hours=int(os.getenv("TELEMETRY_RETENTION_HOURS", "24")),
            frontend_dir=os.getenv("FRONTEND_DIR", default_frontend),
            # Fault injection lets operators push an unvalidated config for incident
            # drills. It defaults to ON outside production and OFF in production.
            enable_fault_injection=_bool(
                os.getenv("ENABLE_FAULT_INJECTION"), env != "production"
            ),
            seed_demo_data=_bool(os.getenv("SEED_DEMO_DATA"), False),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.env == "production" and self.admin_token in {"", DEV_ADMIN_TOKEN}:
            raise RuntimeError(
                "ADMIN_TOKEN must be set to a non-default value when APP_ENV=production"
            )
