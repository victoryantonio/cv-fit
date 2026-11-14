"""The migration is the schema. If it drifts from the models, this fails."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db import Base

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_TABLES = {
    "alembic_version",
    "analysis",
    "analysis_task",
    "app_setting",
    "cv",
    "cv_version",
    "jd_extraction",
    "jd_requirement",
    "jd_snapshot",
    "job_posting",
    "job_sync_state",
    "llm_call",
    "requirement_match",
    "suggestion",
}


def _config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'migrations.db'}"


def test_upgrade_head_creates_every_table(db_url: str) -> None:
    command.upgrade(_config(db_url), "head")

    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables == EXPECTED_TABLES


def test_upgrade_matches_the_models(db_url: str) -> None:
    command.upgrade(_config(db_url), "head")

    engine = create_engine(db_url)
    try:
        migrated = set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()
    assert migrated == set(Base.metadata.tables)


def test_downgrade_removes_every_table(db_url: str) -> None:
    config = _config(db_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()
    assert tables == set()


def test_upgrade_after_downgrade_works(db_url: str) -> None:
    config = _config(db_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables == EXPECTED_TABLES


def test_foreign_keys_are_declared(db_url: str) -> None:
    command.upgrade(_config(db_url), "head")

    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        match_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("requirement_match")}
        task_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("analysis_task")}
    finally:
        engine.dispose()
    assert match_fks == {"analysis", "jd_requirement"}
    assert task_fks == {"analysis"}
