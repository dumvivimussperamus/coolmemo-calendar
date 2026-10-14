import base64
import ctypes
import json
import os
import sqlite3
from ctypes import wintypes

from .config import CLIENT_SECRET_FILE, STATE_DB, TOKEN_FILE, ensure_directories


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_bytes(data):
    if os.name != "nt":
        return base64.b64encode(data)
    in_blob, in_buffer = _blob(data)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), "CoolMemo Calendar", None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(protected)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def unprotect_bytes(data):
    raw = base64.b64decode(data)
    if os.name != "nt":
        return raw
    in_blob, in_buffer = _blob(raw)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def save_secure_json(path, value):
    ensure_directories()
    path.write_bytes(protect_bytes(json.dumps(value, ensure_ascii=False).encode("utf-8")))


def load_secure_json(path):
    if not path.exists():
        return None
    return json.loads(unprotect_bytes(path.read_bytes()).decode("utf-8"))


def save_client_config(value):
    save_secure_json(CLIENT_SECRET_FILE, value)


def load_client_config():
    return load_secure_json(CLIENT_SECRET_FILE)


def save_token(value):
    save_secure_json(TOKEN_FILE, value)


def load_token():
    return load_secure_json(TOKEN_FILE)


def remove_google_connection():
    for path in (CLIENT_SECRET_FILE, TOKEN_FILE):
        if path.exists():
            path.unlink()


def connect():
    ensure_directories()
    con = sqlite3.connect(STATE_DB)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS event_links (
            source_table TEXT NOT NULL,
            source_key INTEGER NOT NULL,
            occurrence_key TEXT NOT NULL,
            google_event_id TEXT NOT NULL,
            payload_hash TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_table, source_key, occurrence_key)
        )
        """
    )
    columns = {row[1] for row in con.execute("PRAGMA table_info(event_links)")}
    if "calendar_id" not in columns:
        con.execute("ALTER TABLE event_links ADD COLUMN calendar_id TEXT DEFAULT 'primary'")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dismissed (
            candidate_id TEXT PRIMARY KEY,
            dismissed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.commit()
    return con


def linked_event(source_table, source_key, occurrence_key):
    con = connect()
    row = con.execute(
        "SELECT google_event_id, payload_hash, calendar_id FROM event_links WHERE source_table=? AND source_key=? AND occurrence_key=?",
        (source_table, source_key, occurrence_key),
    ).fetchone()
    con.close()
    return {"event_id": row[0], "payload_hash": row[1], "calendar_id": row[2] or "primary"} if row else None


def save_link(source_table, source_key, occurrence_key, event_id, payload_hash, calendar_id="primary"):
    con = connect()
    con.execute(
        """
        INSERT INTO event_links(source_table, source_key, occurrence_key, google_event_id, payload_hash, calendar_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_table, source_key, occurrence_key) DO UPDATE SET
          google_event_id=excluded.google_event_id,
          payload_hash=excluded.payload_hash,
          calendar_id=excluded.calendar_id,
          updated_at=CURRENT_TIMESTAMP
        """,
        (source_table, source_key, occurrence_key, event_id, payload_hash, calendar_id),
    )
    con.commit()
    con.close()


def dismiss(candidate_ids):
    con = connect()
    con.executemany("INSERT OR IGNORE INTO dismissed(candidate_id) VALUES (?)", [(value,) for value in candidate_ids])
    con.commit()
    con.close()


def dismissed_ids():
    con = connect()
    values = {row[0] for row in con.execute("SELECT candidate_id FROM dismissed")}
    con.close()
    return values
