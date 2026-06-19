"""Alembic baseline must upgrade to head and downgrade to base cleanly."""

import os
import tempfile

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ALEMBIC_INI = os.path.join(REPO_ROOT, "backend", "alembic.ini")

EXPECTED_TABLES = {
    "workspaces", "users", "memberships", "sessions", "api_keys",
    "contacts", "contact_lists", "list_memberships", "segments", "suppressions",
    "sending_domains", "templates", "saved_blocks", "campaigns", "campaign_variants", "messages", "events",
    "automations", "automation_steps", "automation_runs",
    "jobs", "audit_logs", "ai_usage",
}


def _config(db_url: str) -> Config:
    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("script_location", os.path.join(REPO_ROOT, "backend", "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    os.environ["DATABASE_URL"] = db_url  # env.py reads settings.database_url
    return cfg


def test_migration_upgrade_then_downgrade():
    tmpdir = tempfile.mkdtemp(prefix="ice-mig-")
    db_path = os.path.join(tmpdir, "m.db")
    db_url = f"sqlite:///{db_path}"
    cfg = _config(db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables), f"missing: {EXPECTED_TABLES - tables}"
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(db_url)
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert remaining == set(), f"tables left after downgrade: {remaining}"
    engine.dispose()
