"""Offline migration regression tests; no GitHub Actions or ClaudeHub required."""
import json
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
            "fermentation_batches", "cuisine_recipes", "alembic_version"}.issubset(tables)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_cuisines"
    assert con.execute("SELECT COUNT(*) FROM cuisine_recipes").fetchone()[0] >= 23
    assert con.execute("SELECT kind FROM cuisine_recipes WHERE id='gazpacho'").fetchone()[0] == "quantified"
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


def test_timers_table_exists_after_upgrade_and_upgrade_is_idempotent(tmp_path):
    path = tmp_path / "timers.db"
    upgrade(path)
    upgrade(path)
    con = sqlite3.connect(path)
    columns = {row[1] for row in con.execute("PRAGMA table_info(cooking_timers)")}
    assert {"user_id", "chat_id", "recipe_title", "step_index",
            "label", "minutes", "due_at_ts", "status",
            "retry_at_ts", "lease_until_ts", "attempts"}.issubset(columns)
    con.execute(
        "INSERT INTO cooking_timers "
        "(user_id,chat_id,recipe_title,step_index,label,minutes,"
        "due_at_ts,status,lease_until_ts,retry_at_ts,attempts,created_at) "
        "VALUES (10,10,'Суп',1,'Перемешать',5,99999,'active',0,0,0,CURRENT_TIMESTAMP)"
    )
    con.commit()
    con.close()
    upgrade(path)
    con = sqlite3.connect(path)
    assert con.execute("SELECT count(*) FROM cooking_timers").fetchone()[0] == 1
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_cuisines"
    con.close()



def test_repeated_migration_keeps_edited_cuisine_entry_and_existing_users(tmp_path):
    path = tmp_path / "preserve.db"
    upgrade(path)
    con = sqlite3.connect(path)
    con.execute("UPDATE cuisine_recipes SET method=? WHERE id='gazpacho'",
                ("Редакторская правка",))
    con.execute("INSERT INTO users(id,mode,preferences,last_recipe,usage_day,usage_count) "
                "VALUES(31,'ask',?,NULL,'',0)", (json.dumps({"likes": "суп"}, ensure_ascii=False),))
    con.commit()
    con.close()
    upgrade(path)
    con = sqlite3.connect(path)
    assert con.execute("SELECT method FROM cuisine_recipes WHERE id='gazpacho'").fetchone()[0] == "Редакторская правка"
    assert con.execute("SELECT preferences FROM users WHERE id=31").fetchone()[0].find("суп") >= 0
    con.close()


def test_legacy_current_recipe_is_backfilled_without_erasing_original(tmp_path):
    path = tmp_path / "profile-legacy.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE users(
          id BIGINT PRIMARY KEY, mode VARCHAR(32) NOT NULL,
          preferences JSON NOT NULL, last_recipe JSON,
          usage_day VARCHAR(10) NOT NULL, usage_count INTEGER NOT NULL
        );
        INSERT INTO users(id,mode,preferences,last_recipe,usage_day,usage_count)
        VALUES(77, 'ask', '{}',
               '{"title":"Каша","ingredients":[],"steps":["Кипятить"]}',
               '', 0);
    """)
    con.commit()
    con.close()
    upgrade(path)
    con = sqlite3.connect(path)
    original = con.execute("SELECT last_recipe FROM users WHERE id=77").fetchone()[0]
    archived = con.execute(
        "SELECT recipe,origin FROM recipe_archive WHERE user_id=77"
    ).fetchone()
    assert json.loads(original)["title"] == "Каша"
    assert json.loads(archived[0]) == json.loads(original)
    assert archived[1] == "legacy_last"
    con.close()
