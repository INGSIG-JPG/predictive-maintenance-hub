import pytest

from app.config import Config
from app.db import Conn, Database

pytestmark = pytest.mark.unit


def test_placeholder_translation_only_for_postgres():
    assert Conn(None, "postgres")._sql("SELECT * FROM t WHERE a = ? AND b = ?") == "SELECT * FROM t WHERE a = %s AND b = %s"
    assert Conn(None, "sqlite")._sql("SELECT ?") == "SELECT ?"


def test_unsupported_scheme_is_rejected():
    with pytest.raises(ValueError):
        Database("mysql://localhost/db")


def test_dialect_detection():
    assert Database("sqlite:///x.db").dialect == "sqlite"
    assert Database("postgresql://u:p@h/db").dialect == "postgres"
    assert Database("postgres://u:p@h/db").dialect == "postgres"


def test_insert_returns_new_id_and_query_returns_dicts(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'a.db'}")
    db.init_schema()
    with db.session() as conn:
        first = conn.insert("INSERT INTO machines (code, name, machine_type, location, created_at) VALUES (?,?,?,?,?)", ("AAA-1", "n", "pump", "", "t"))
        second = conn.insert("INSERT INTO machines (code, name, machine_type, location, created_at) VALUES (?,?,?,?,?)", ("AAA-2", "n", "pump", "", "t"))
        conn.commit()
        assert second == first + 1
        row = conn.query_one("SELECT code FROM machines WHERE id = ?", (first,))
        assert row == {"code": "AAA-1"}
        assert conn.query_one("SELECT code FROM machines WHERE id = ?", (999,)) is None


def test_init_schema_is_idempotent(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'b.db'}")
    db.init_schema()
    db.init_schema()


def test_production_requires_non_default_admin_token():
    with pytest.raises(RuntimeError):
        Config(env="production").validate()
    Config(env="production", admin_token="a-long-random-value").validate()
