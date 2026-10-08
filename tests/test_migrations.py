"""Offline migration regression tests; no GitHub Actions or ClaudeHub required."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def upgrade(path: Path):
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=PROJECT_ROOT, env=env, check=True, capture_output=True, text=True,
    )


def test_fresh_db_alembic_builds_memory_and_archive_tables(tmp_path):
    path = tmp_path / "fresh.db"
    upgrade(path)
    con = sqlite3.connect(path)
    tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"users", "personal_memories", "recipe_archive",
            "fermentation_batches", "alembic_version"}.issubset(tables)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0001_memory"
    con.close()


def test_old_fermentation_rows_survive_migration_and_upgrade_is_repeatable(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fermentation_batches (
            id INTEGER PRIMARY KEY, user_id BIGINT NOT NULL,
            category VARCHAR(20) NOT NULL, name VARCHAR(120) NOT NULL,
            protocol_source VARCHAR(240) NOT NULL DEFAULT '',
            finished BOOLEAN NOT NULL DEFAULT 0,
            started_at DATETIME NOT NULL
        );
        INSERT INTO fermentation_batches(id,user_id,category,name,protocol_source,finished,started_at)
        VALUES (1,501,'vegetables','Наша капуста','',0,'2026-10-08');
    """)
    conn.commit()
    conn.close()
    upgrade(path)
    upgrade(path)
    con = sqlite3.connect(path)
    row = con.execute(
        "SELECT name, protocol_id, protocol_revision FROM fermentation_batches WHERE id=1"
    ).fetchone()
    assert row == ("Наша капуста", "", "")
    assert con.execute("SELECT count(*) FROM recipe_archive").fetchone()[0] == 0
    con.close()
