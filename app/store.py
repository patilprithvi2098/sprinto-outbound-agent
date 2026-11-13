"""Where runs, records and the page cache live: JSON files under data/ locally, Neon Postgres on Vercel
(Vercel's disk is thrown away between requests). One small interface for both."""
import json
import os
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
# kind -> file layout under data/ (kept from the earlier phases, so old runs still show)
_LAYOUT = {"run": "runs/{key}/run.json", "record": "runs/{key}.json", "cache": "cache/{key}.json"}


class FileStore:
    def __init__(self, root=DATA):
        self.root = Path(root)

    def _path(self, kind, key):
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError("bad key")
        return self.root / _LAYOUT[kind].format(key=key)

    def get(self, kind, key):
        p = self._path(kind, key)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, kind, key, value):
        p = self._path(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)  # contact names and emails: owner only
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, indent=2))
        tmp.replace(p)  # readers never see a half-written file

    def run_ids(self):
        runs = self.root / "runs"
        return sorted(p.name for p in runs.glob("*") if (p / "run.json").exists()) if runs.exists() else []

    def records(self):
        runs = self.root / "runs"
        return [json.loads(p.read_text()) for p in runs.glob("*/*.json") if p.name != "run.json"] if runs.exists() else []

    def claim(self, name, ttl=None):
        """True for exactly one caller until released (or until `ttl` seconds pass, for work that may have died)."""
        p = self.root / "claims" / name.replace("/", "_")
        p.parent.mkdir(parents=True, exist_ok=True)
        if ttl and p.exists() and time.time() - p.stat().st_mtime > ttl:
            p.unlink(missing_ok=True)
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            return False

    def release(self, name):
        (self.root / "claims" / name.replace("/", "_")).unlink(missing_ok=True)


def _obj(value):
    return json.loads(value) if isinstance(value, str) else value  # pg8000 may already decode jsonb


class PgStore:
    """Tables `kv` and `claims` (db/schema.sql). One short connection per call: serverless functions do not keep state."""

    def _run(self, sql, args=(), fetch=False):
        import feedback  # same DATABASE_URL connection code as the feedback loop
        conn = feedback._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            rows = cur.fetchall() if fetch else None
            conn.commit()
            return rows
        finally:
            conn.close()

    def get(self, kind, key):
        rows = self._run("SELECT value FROM kv WHERE kind = %s AND key = %s", (kind, key), fetch=True)
        return _obj(rows[0][0]) if rows else None

    def put(self, kind, key, value):
        self._run("INSERT INTO kv (kind, key, value) VALUES (%s, %s, %s::jsonb) ON CONFLICT (kind, key) "
                  "DO UPDATE SET value = EXCLUDED.value, updated_at = now()", (kind, key, json.dumps(value)))

    def run_ids(self):
        return [r[0] for r in self._run("SELECT key FROM kv WHERE kind = 'run' ORDER BY key", fetch=True)]

    def records(self):
        return [_obj(r[0]) for r in self._run("SELECT value FROM kv WHERE kind = 'record'", fetch=True)]

    def claim(self, name, ttl=None):
        rows = self._run(
            "INSERT INTO claims (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET created_at = now() "
            "WHERE %s::int IS NOT NULL AND claims.created_at < now() - make_interval(secs => %s::int) RETURNING name",
            (name, ttl, ttl or 0), fetch=True)
        return bool(rows)

    def release(self, name):
        self._run("DELETE FROM claims WHERE name = %s", (name,))


def _choose():
    return PgStore() if os.environ.get("VERCEL") or os.environ.get("STORE") == "neon" else FileStore()


STORE = _choose()
