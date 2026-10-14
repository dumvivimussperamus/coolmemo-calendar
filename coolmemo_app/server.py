import hashlib
import json
import logging
import mimetypes
import secrets
import sys
import threading
import time
import urllib.request
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, updater
from .config import (
    BASE_PORT,
    CLIENT_SECRET_FILE,
    discover_source_dbs,
    get_source_db,
    get_calendar_id,
    get_theme,
    set_calendar_id,
    HOST,
    LOG_FILE,
    PORT_TRIES,
    set_source_db,
    set_theme,
    STATIC_DIR,
    TOKEN_FILE,
    ensure_directories,
)
from .extractor import build_ics, extract_from_database
from .google_calendar import (
    auth_url,
    create_event,
    exchange_code,
    has_list_scope,
    list_calendars,
    move_event,
    update_event,
)
from .storage import (
    dismiss,
    dismissed_ids,
    linked_event,
    remove_google_connection,
    save_client_config,
    save_link,
)


APP_ID = "coolmemo-calendar"
APP_TOKEN = secrets.token_urlsafe(32)
OAUTH_STATES = {}
EXTRACT_CACHE = {"path": "", "mtime": 0, "days": 0, "items": [], "updated": 0}


def setup_logging():
    ensure_directories()
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def candidate_items(days, force=False):
    source_db = get_source_db()
    source_path = str(source_db) if source_db else ""
    mtime = source_db.stat().st_mtime if source_db else 0
    if force or source_path != EXTRACT_CACHE["path"] or mtime != EXTRACT_CACHE["mtime"] or days != EXTRACT_CACHE["days"]:
        items = extract_from_database(source_db, days=days) if source_db else []
        ignored = dismissed_ids()
        for item in items:
            link = linked_event(item["source_table"], item["source_key"], item["occurrence_key"])
            item["synced"] = bool(link)
            item["google_event_id"] = link["event_id"] if link else ""
            item["dismissed"] = item["id"] in ignored
        EXTRACT_CACHE.update({"path": source_path, "mtime": mtime, "days": days, "items": items, "updated": time.time()})
    return EXTRACT_CACHE["items"]


def choose_source_db():
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            parent=root,
            title="쿨메신저 UDB 파일 선택",
            filetypes=[("쿨메신저 데이터베이스", "*.udb"), ("모든 파일", "*.*")],
        )
    finally:
        root.destroy()
    return set_source_db(selected) if selected else None


def event_hash(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


class Handler(BaseHTTPRequestHandler):
    server_version = "CoolMemoCalendar/1.0"

    def log_message(self, fmt, *args):
        logging.info("%s - %s", self.address_string(), fmt % args)

    def _send(self, status, body=b"", content_type="text/plain; charset=utf-8", extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self'; script-src 'self'")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, value):
        self._send(status, json_bytes(value), "application/json; charset=utf-8")

    def _read_json(self, max_bytes=2_000_000):
        length = int(self.headers.get("Content-Length", "0"))
        if length > max_bytes:
            raise ValueError("요청 데이터가 너무 큽니다.")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _require_token(self):
        if self.headers.get("X-App-Token") != APP_TOKEN:
            self._json(HTTPStatus.FORBIDDEN, {"error": "요청 확인 토큰이 올바르지 않습니다."})
            return False
        return True

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/ping":
            self._json(HTTPStatus.OK, {"app": APP_ID})
            return
        if parsed.path == "/api/bootstrap":
            source_db = get_source_db()
            latest = source_db.stat().st_mtime if source_db else 0
            self._json(
                HTTPStatus.OK,
                {
                    "token": APP_TOKEN,
                    "sourceExists": bool(source_db),
                    "sourcePath": str(source_db) if source_db else "",
                    "sourceCandidates": [str(path) for path in discover_source_dbs()[:10]],
                    "theme": get_theme(),
                    "version": updater.current_version(),
                    "sourceUpdated": latest,
                    "googleConfigured": CLIENT_SECRET_FILE.exists(),
                    "googleConnected": TOKEN_FILE.exists(),
                    "googleCanListCalendars": TOKEN_FILE.exists() and has_list_scope(),
                    "calendarId": get_calendar_id(),
                },
            )
            return
        if parsed.path == "/api/candidates":
            query = urllib.parse.parse_qs(parsed.query)
            days = int(query.get("days", ["90"])[0])
            force = query.get("force", ["0"])[0] == "1"
            try:
                items = candidate_items(days, force=force)
                self._json(HTTPStatus.OK, {"items": items, "updated": EXTRACT_CACHE["updated"]})
            except Exception as error:
                logging.exception("candidate extraction failed")
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
            return
        if parsed.path == "/api/update":
            query = urllib.parse.parse_qs(parsed.query)
            self._json(HTTPStatus.OK, updater.check(force=query.get("force", ["0"])[0] == "1"))
            return
        if parsed.path == "/api/google/calendars":
            if not self._require_token():
                return
            try:
                self._json(HTTPStatus.OK, {"calendars": list_calendars(), "selected": get_calendar_id()})
            except PermissionError as error:
                self._json(HTTPStatus.OK, {"calendars": [], "selected": get_calendar_id(), "needsReconnect": True, "error": str(error)})
            except Exception as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if parsed.path == "/api/google/auth-url":
            if not self._require_token():
                return
            try:
                self._json(HTTPStatus.OK, {"url": auth_url(OAUTH_STATES)})
            except Exception as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if parsed.path == "/oauth/callback":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                if query.get("error"):
                    raise ValueError(query["error"][0])
                exchange_code(query.get("code", [""])[0], query.get("state", [""])[0], OAUTH_STATES)
                body = """<!doctype html><html lang='ko'><meta charset='utf-8'><meta http-equiv='refresh' content='2;url=/'><title>연결 완료</title><body style='font-family:sans-serif;padding:40px;background:#fff6ef;color:#367060'><h1>Google Calendar 연결 완료</h1><p>잠시 후 메모 일정함으로 돌아갑니다.</p></body></html>""".encode("utf-8")
                self._send(HTTPStatus.OK, body, "text/html; charset=utf-8")
            except Exception as error:
                self._send(HTTPStatus.BAD_REQUEST, f"연결 실패: {error}".encode("utf-8"))
            return
        self._serve_static(parsed.path)

    def _serve_static(self, request_path):
        relative = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
        target = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
            self._send(HTTPStatus.FORBIDDEN, b"Forbidden")
            return
        if not target.exists() or not target.is_file():
            self._send(HTTPStatus.NOT_FOUND, b"Not found")
            return
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.name == "index.html":
            page = target.read_text(encoding="utf-8").replace('data-theme="coral"', f'data-theme="{get_theme()}"', 1)
            self._send(HTTPStatus.OK, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._send(HTTPStatus.OK, target.read_bytes(), f"{mime}; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else mime)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if not self._require_token():
            return
        try:
            data = self._read_json()
            if parsed.path == "/api/source/pick":
                selected = choose_source_db()
                if selected:
                    EXTRACT_CACHE["path"] = ""
                self._json(HTTPStatus.OK, {"path": str(selected) if selected else ""})
                return
            if parsed.path == "/api/source/set":
                selected = set_source_db(data.get("path", ""))
                EXTRACT_CACHE["path"] = ""
                self._json(HTTPStatus.OK, {"path": str(selected)})
                return
            if parsed.path == "/api/theme":
                self._json(HTTPStatus.OK, {"theme": set_theme(data.get("theme", ""))})
                return
            if parsed.path == "/api/google/calendar":
                self._json(HTTPStatus.OK, {"calendarId": set_calendar_id(data.get("calendar_id"))})
                return
            if parsed.path == "/api/update/install":
                result = updater.install()
                self._json(HTTPStatus.OK, result)
                threading.Timer(1.0, self.server.shutdown).start()
                return
            if parsed.path == "/api/quit":
                self._json(HTTPStatus.OK, {"ok": True})
                threading.Timer(0.3, self.server.shutdown).start()
                return
            if parsed.path == "/api/source/auto":
                candidates = discover_source_dbs(refresh=True)
                if not candidates:
                    raise ValueError("자동으로 찾은 UDB 파일이 없습니다.")
                selected = set_source_db(candidates[0])
                EXTRACT_CACHE["path"] = ""
                self._json(HTTPStatus.OK, {"path": str(selected)})
                return
            if parsed.path == "/api/google/credentials":
                value = data.get("credentials")
                if not isinstance(value, dict) or not (value.get("installed") or value.get("web") or value.get("client_id")):
                    raise ValueError("Google OAuth 클라이언트 JSON 파일을 선택해 주세요.")
                save_client_config(value)
                self._json(HTTPStatus.OK, {"ok": True})
                return
            if parsed.path == "/api/google/disconnect":
                remove_google_connection()
                self._json(HTTPStatus.OK, {"ok": True})
                return
            if parsed.path == "/api/dismiss":
                dismiss(data.get("ids", []))
                EXTRACT_CACHE["mtime"] = 0
                self._json(HTTPStatus.OK, {"ok": True})
                return
            if parsed.path == "/api/export-ics":
                events = data.get("events", [])
                body = build_ics(events).encode("utf-8")
                self._send(
                    HTTPStatus.OK,
                    body,
                    "text/calendar; charset=utf-8",
                    {"Content-Disposition": 'attachment; filename="coolmemo-calendar.ics"'},
                )
                return
            if parsed.path == "/api/calendar/events":
                results = []
                calendar_id = data.get("calendar_id") or get_calendar_id()
                for event in data.get("events", []):
                    link = linked_event(event["source_table"], event["source_key"], event["occurrence_key"])
                    payload_hash = event_hash(event)
                    if link:
                        if link["calendar_id"] != calendar_id:
                            move_event(link["event_id"], link["calendar_id"], calendar_id)
                        result = update_event(link["event_id"], event, calendar_id)
                    else:
                        result = create_event(event, calendar_id)
                    save_link(
                        event["source_table"], event["source_key"], event["occurrence_key"], result["id"], payload_hash,
                        calendar_id,
                    )
                    results.append({"id": result["id"], "htmlLink": result.get("htmlLink", ""), "updated": bool(link)})
                EXTRACT_CACHE["mtime"] = 0
                self._json(HTTPStatus.OK, {"results": results})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "지원하지 않는 요청입니다."})
        except Exception as error:
            logging.exception("POST %s failed", parsed.path)
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


class AppServer(ThreadingHTTPServer):
    # Windows에서는 SO_REUSEADDR가 같은 포트 중복 바인딩을 허용하므로 끈다.
    allow_reuse_address = False
    daemon_threads = True


def open_browser(url=None):
    webbrowser.open(url or config.BASE_URL)


def _is_our_instance(port):
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/ping", timeout=1.5) as response:
            return json.loads(response.read().decode()).get("app") == APP_ID
    except Exception:
        return False


def _bind_server():
    """(server, existing_url) 중 하나를 반환한다. 이미 실행 중이면 그 주소를 돌려준다."""
    for port in range(BASE_PORT, BASE_PORT + PORT_TRIES):
        try:
            server = AppServer((HOST, port), Handler)
        except OSError:
            if _is_our_instance(port):
                return None, f"http://{HOST}:{port}"
            continue
        config.set_port(port)
        return server, None
    raise RuntimeError("사용 가능한 로컬 포트를 찾지 못했습니다.")


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    background = "--background" in argv
    setup_logging()
    ensure_directories()
    server, existing = _bind_server()
    if existing:
        if not background:
            open_browser(existing)
        return
    threading.Thread(target=discover_source_dbs, daemon=True).start()
    threading.Thread(target=updater.check, daemon=True).start()
    if not background:
        threading.Timer(0.7, open_browser).start()
    logging.info("CoolMemo Calendar started at %s", config.BASE_URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
