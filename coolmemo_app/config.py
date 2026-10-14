import json
import os
import sqlite3
import string
import sys
import threading
from pathlib import Path


APP_NAME = "메모 일정함"
APP_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home()))
DATA_DIR = Path(os.environ.get("COOLMEMO_DATA_DIR") or LOCAL_APP_DATA / "CoolMemoCalendar")
STATIC_DIR = RESOURCE_ROOT / "static"
STATE_DB = DATA_DIR / "calendar_app.sqlite"
CLIENT_SECRET_FILE = DATA_DIR / "google_client.bin"
TOKEN_FILE = DATA_DIR / "google_token.bin"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "app.log"

HOST = "127.0.0.1"
BASE_PORT = int(os.environ.get("COOLMEMO_PORT", "8766"))
PORT_TRIES = 10
PORT = BASE_PORT
BASE_URL = f"http://{HOST}:{PORT}"
TIME_ZONE = "Asia/Seoul"

THEMES = ("coral", "forest", "sky", "dark")
DEFAULT_THEME = "coral"
LEGACY_THEMES = {"warm": "coral"}


def set_port(port):
    global PORT, BASE_URL
    PORT = port
    BASE_URL = f"http://{HOST}:{PORT}"


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    try:
        value = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(value):
    ensure_directories()
    SETTINGS_FILE.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def get_theme():
    theme = load_settings().get("theme", DEFAULT_THEME)
    theme = LEGACY_THEMES.get(theme, theme)
    return theme if theme in THEMES else DEFAULT_THEME


def set_theme(theme):
    if theme not in THEMES:
        raise ValueError("지원하지 않는 색상 테마입니다.")
    settings = load_settings()
    settings["theme"] = theme
    save_settings(settings)
    return theme


def get_calendar_id():
    return load_settings().get("calendar_id") or "primary"


def set_calendar_id(calendar_id):
    settings = load_settings()
    settings["calendar_id"] = str(calendar_id or "primary")
    save_settings(settings)
    return settings["calendar_id"]


def _search_roots():
    """쿨메신저 UDB가 있을 만한 위치와 탐색 깊이."""
    home = Path.home()
    roots = [
        (LOCAL_APP_DATA / "CoolMessenger", 3),
        (Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "CoolMessenger", 3),
        (home / "Documents" / "CoolMessenger", 3),
        (home / "Documents", 1),
        (home / "Desktop", 1),
        (home / "Downloads", 1),
        (Path(sys.executable).resolve().parent, 1),
    ]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        base = os.environ.get(env)
        if base:
            roots.append((Path(base) / "CoolMessenger", 3))
    if os.name == "nt":
        import ctypes

        for letter in string.ascii_uppercase:
            drive = f"{letter}:/"
            # 고정 디스크(3)만 검사해서 끊어진 네트워크 드라이브로 멈추지 않게 한다.
            if ctypes.windll.kernel32.GetDriveTypeW(drive) == 3:
                roots.append((Path(drive) / "CoolMessenger", 3))
    if not getattr(sys, "frozen", False):
        roots.extend(((APP_ROOT.parent, 1), (Path.cwd(), 1)))
    return roots


def _walk_udb(root, depth):
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file() and entry.name.lower().endswith(".udb"):
                yield Path(entry.path)
            elif depth > 0 and entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                yield from _walk_udb(entry.path, depth - 1)
        except OSError:
            continue


def is_coolmessenger_db(path):
    """쿨메신저 메시지 테이블이 들어 있는 DB인지 읽기 전용으로 확인한다."""
    try:
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
    except sqlite3.Error:
        return False
    return "tbl_recv" in names or "tbl_send" in names


_DISCOVERY = {"done": False, "items": []}
_DISCOVERY_LOCK = threading.Lock()


def discover_source_dbs(refresh=False):
    """자동 탐색: 수정 시각이 가장 최근인 쿨메신저 UDB 순으로 반환한다."""
    with _DISCOVERY_LOCK:
        if refresh or not _DISCOVERY["done"]:
            _DISCOVERY["items"] = _scan_source_dbs()
            _DISCOVERY["done"] = True
        return [path for path in _DISCOVERY["items"] if path.exists()]


def _scan_source_dbs():
    found = {}
    for root, depth in _search_roots():
        if not root.exists() or not root.is_dir():
            continue
        for path in _walk_udb(root, depth):
            try:
                found[str(path.resolve()).lower()] = path.resolve()
            except OSError:
                continue
    ordered = sorted(found.values(), key=lambda path: path.stat().st_mtime, reverse=True)
    return [path for path in ordered if is_coolmessenger_db(path)]


def get_source_db():
    configured = load_settings().get("source_db", "")
    if configured:
        path = Path(configured).expanduser()
        if path.exists() and path.is_file():
            return path.resolve()
    discovered = discover_source_dbs()
    return discovered[0] if discovered else None


def set_source_db(path_value):
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".udb":
        raise ValueError("사용할 수 있는 쿨메신저 UDB 파일을 선택해 주세요.")
    if not is_coolmessenger_db(path):
        raise ValueError("쿨메신저 메시지 데이터가 들어 있는 UDB 파일이 아닙니다.")
    settings = load_settings()
    settings["source_db"] = str(path)
    save_settings(settings)
    return path
