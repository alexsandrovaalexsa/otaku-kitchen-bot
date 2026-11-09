"""Durable recipe catalog for Render + Neon PostgreSQL.

When DATABASE_URL is set, recipe changes are committed to Neon before being
published to the in-process cache. Local Windows use (without DATABASE_URL)
continues to work from recipes.json. No DB credentials are ever logged.
"""
import json
import os
import time
from pathlib import Path

DB_URL = os.environ.get('DATABASE_URL', '').strip()
RECIPES_PATH = Path(__file__).with_name('recipes.json')


def database_enabled():
    return bool(DB_URL)


def _connection():
    # Import lazily: local Windows use remains dependency-free.
    import psycopg
    # Neon can supply a pooled PgBouncer connection. Disabling psycopg's
    # automatic prepared statements keeps the pooled connection compatible.
    return psycopg.connect(DB_URL, connect_timeout=15, prepare_threshold=None)


def _load_from_db(seed):
    from psycopg.types.json import Jsonb
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS otaku_recipes (
                    message_id BIGINT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS otaku_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            cur.execute("SELECT value FROM otaku_settings WHERE key = 'seed_complete'")
            if cur.fetchone() is None:
                # Never replace newer recipes that arrived before seeding.
                cur.executemany('''
                    INSERT INTO otaku_recipes (message_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (message_id) DO NOTHING
                ''', [(int(r['id']), Jsonb(r)) for r in seed])
                cur.execute('''
                    INSERT INTO otaku_settings (key, value)
                    VALUES ('seed_complete', '1')
                    ON CONFLICT (key) DO NOTHING
                ''')
            cur.execute('SELECT data FROM otaku_recipes ORDER BY message_id')
            return [row[0] for row in cur.fetchall()]


def load_recipes():
    """Read the persistent catalog, seeding the original export only once."""
    seed = json.loads(RECIPES_PATH.read_text(encoding='utf-8'))
    if not DB_URL:
        return seed
    # Free Neon may need a few seconds to wake after inactivity.
    for attempt in range(4):
        try:
            return _load_from_db(seed)
        except Exception as ex:
            if attempt == 3:
                raise
            print(f'Database startup retry {attempt+1}/4 ({type(ex).__name__})', flush=True)
            time.sleep(2 ** attempt)


def upsert_recipe(recipe):
    """Insert/update one channel recipe. Retried Telegram deliveries are safe."""
    if not DB_URL:
        raise RuntimeError('PostgreSQL DATABASE_URL is required for durable updates')
    from psycopg.types.json import Jsonb
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO otaku_recipes (message_id, data, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (message_id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
            ''', (int(recipe['id']), Jsonb(recipe)))


def delete_recipe(message_id):
    """Remove a former recipe if its edited text no longer has recipe tags."""
    if not DB_URL:
        raise RuntimeError('PostgreSQL DATABASE_URL is required for durable updates')
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM otaku_recipes WHERE message_id = %s', (int(message_id),))


def save_local_recipes(data):
    """Only for optional local Windows mode, not for Render."""
    temp = RECIPES_PATH.with_suffix('.json.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(RECIPES_PATH)
