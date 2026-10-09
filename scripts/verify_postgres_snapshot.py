"""Deployment-only PostgreSQL manifests. Never emit row contents or credentials."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path
import asyncpg
from sqlalchemy.engine import make_url

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), default=str).encode()).hexdigest()

def ident(name):
    return '"' + name.replace('"', '""') + '"'

async def manifest(conn):
    tables = {}
    names = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    for entry in names:
        name = entry["tablename"]
        rows = await conn.fetch(f"SELECT to_jsonb(t)::text AS row_text FROM public.{ident(name)} t ORDER BY row_text")
        cols = await conn.fetch("""SELECT column_name, data_type, udt_name, is_nullable, column_default,
                                  character_maximum_length FROM information_schema.columns
                                  WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position""", name)
        indexes = await conn.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=$1 ORDER BY indexname", name)
        constraints = await conn.fetch("""SELECT c.conname, pg_get_constraintdef(c.oid) AS definition
                                         FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
                                         JOIN pg_namespace n ON n.oid=t.relnamespace
                                         WHERE n.nspname='public' AND t.relname=$1 ORDER BY c.conname""", name)
        tables[name] = {"count": len(rows), "data_sha256": digest([r["row_text"] for r in rows]),
                        "schema_sha256": digest([[dict(c) for c in cols], [dict(i) for i in indexes],
                                                 [dict(c) for c in constraints]])}
    sequences = {}
    for row in await conn.fetch("SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"):
        name = row["sequencename"]
        value = await conn.fetchrow(f"SELECT last_value, is_called FROM public.{ident(name)}")
        sequences[name] = digest(dict(value))
    dish_rows = {}
    if "dish_process_cards" in tables:
        for row in await conn.fetch("""SELECT id, (to_jsonb(t)-'production_spec')::text AS row_text
                                       FROM public.dish_process_cards t ORDER BY id"""):
            dish_rows[row["id"]] = digest(row["row_text"])
    return {"tables": tables, "sequences": sequences, "dish_rows": dish_rows}

async def main():
    mode, file = sys.argv[1:3]
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("PostgreSQL required")
    if len(sys.argv) > 3:
        database = sys.argv[3]
        if not re.fullmatch(r"sushef(?:_[a-z0-9_]+)?", database):
            raise RuntimeError("Unexpected database")
        url = url.set(database=database)
    conn = await asyncpg.connect(url.set(drivername="postgresql").render_as_string(hide_password=False))
    try:
        actual = await manifest(conn)
        if mode == "snapshot":
            Path(file).write_text(json.dumps(actual, sort_keys=True), encoding="utf-8")
            print("SNAPSHOT_OK tables=" + str(len(actual["tables"])))
            return
        baseline = json.loads(Path(file).read_text(encoding="utf-8"))
        if mode == "restored":
            if baseline != actual:
                raise RuntimeError("Restored schema/data/sequence manifest differs")
            print("RESTORE_MATCH_OK schema+all_rows+sequences")
            return
        if mode != "migrated":
            raise RuntimeError("Unknown verification mode")
        for name, expected in baseline["tables"].items():
            if name not in {"alembic_version", "dish_process_cards"}:
                if actual["tables"].get(name) != expected:
                    raise RuntimeError("Existing table changed: " + name)
        for name, expected in baseline["sequences"].items():
            if actual["sequences"].get(name) != expected:
                raise RuntimeError("Existing sequence changed: " + name)
        for name, expected in baseline["dish_rows"].items():
            if actual["dish_rows"].get(name) != expected:
                raise RuntimeError("Existing dish card changed: " + name)
        revision = await conn.fetchval("SELECT version_num FROM alembic_version")
        if revision != "0005_prod_cards":
            raise RuntimeError("Unexpected Alembic revision")
        from sushef.dish_process_cards_v2 import V2_DISH_CARDS
        for card in V2_DISH_CARDS:
            exists = await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM dish_process_cards
                                           WHERE id=$1 AND production_spec IS NOT NULL)""", card["id"])
            if not exists:
                raise RuntimeError("Version 2 card absent: " + card["id"])
        print("MIGRATION_DATA_OK revision=0005_prod_cards; existing_rows_preserved; v2_cards=" + str(len(V2_DISH_CARDS)))
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
