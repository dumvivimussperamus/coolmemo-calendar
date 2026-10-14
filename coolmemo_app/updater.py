"""GitHub Releases 기반 업데이트 확인과 설치.

보안 원칙
- 확인과 다운로드는 이 저장소(REPO)의 HTTPS 주소만 사용한다.
- 설치파일은 GitHub이 제공하는 SHA-256 digest와 일치할 때만 실행한다.
- 설치는 사용자가 버튼을 누른 경우에만 시작한다.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import config
from .version import INSTALLER_ASSET, REPO, __version__

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
CACHE_SECONDS = 6 * 3600

_lock = threading.Lock()
_cache = {"at": 0.0, "value": None}


def current_version():
    return os.environ.get("COOLMEMO_VERSION_OVERRIDE") or __version__


def parse_version(value):
    numbers = re.findall(r"\d+", str(value).split("-")[0])
    return tuple(int(part) for part in numbers[:4]) or (0,)


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def is_installed_build():
    """설치파일로 설치된 EXE인지(자동 설치 가능 여부)."""
    if not getattr(sys, "frozen", False):
        return False
    return (Path(sys.executable).resolve().parent / "unins000.exe").exists()


def _http_json(url):
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"CoolMemoCalendar/{current_version()}"}
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _summarize(release):
    tag = release.get("tag_name", "")
    asset = next((a for a in release.get("assets", []) if a.get("name") == INSTALLER_ASSET), None)
    digest = (asset or {}).get("digest", "")
    url = (asset or {}).get("browser_download_url", "")
    safe = bool(
        asset and url.startswith(DOWNLOAD_PREFIX) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest or "")
    )
    return {
        "current": current_version(),
        "latest": tag.lstrip("vV"),
        "available": is_newer(tag, current_version()),
        "canAutoInstall": safe and is_installed_build(),
        "assetUrl": url if safe else "",
        "sha256": digest.split(":", 1)[1] if safe else "",
        "notes": (release.get("body") or "")[:600],
        "pageUrl": RELEASES_PAGE,
    }


def check(force=False):
    """최신 릴리스 정보. 네트워크 오류 시 available=False 로 조용히 돌려준다."""
    with _lock:
        if not force and _cache["value"] and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
        try:
            value = _summarize(_http_json(API_URL))
        except Exception as error:  # 오프라인, 요청 제한 등: 업무에 영향 없도록 무시
            logging.info("update check failed: %s", error)
            value = {
                "current": current_version(), "latest": "", "available": False, "canAutoInstall": False,
                "assetUrl": "", "sha256": "", "notes": "", "pageUrl": RELEASES_PAGE, "error": "확인하지 못했습니다.",
            }
        _cache.update({"at": time.time(), "value": value})
        return value


def download_installer(info):
    update_dir = config.DATA_DIR / "update"
    update_dir.mkdir(parents=True, exist_ok=True)
    target = update_dir / f"MemoCalendar-Setup-{info['latest']}.exe"
    request = urllib.request.Request(info["assetUrl"], headers={"User-Agent": f"CoolMemoCalendar/{current_version()}"})
    sha = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=60) as response, open(target, "wb") as out:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            sha.update(chunk)
            out.write(chunk)
    if sha.hexdigest() != info["sha256"]:
        target.unlink(missing_ok=True)
        raise RuntimeError("내려받은 파일이 올바르지 않아 설치를 중단했습니다. (해시 불일치)")
    return target


def install(info=None):
    """검증된 설치파일을 내려받아 조용히 설치하고, 끝나면 앱을 다시 연다."""
    info = info or check(force=True)
    if not info["available"]:
        raise ValueError("이미 최신 버전입니다.")
    if not info["canAutoInstall"]:
        raise ValueError("이 실행 방식에서는 자동 설치를 지원하지 않습니다. 릴리스 페이지에서 직접 받아 주세요.")
    setup = download_installer(info)
    app_exe = Path(sys.executable).resolve()
    script = setup.with_suffix(".cmd")
    script.write_text(
        "@echo off\r\n"
        f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS\r\n'
        f'start "" "{app_exe}"\r\n'
        f'del "{setup}" >nul 2>&1\r\n',
        encoding="mbcs",
    )
    if os.environ.get("COOLMEMO_UPDATE_DRY_RUN") == "1":
        return {"dryRun": True, "script": str(script)}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd.exe", "/c", str(script)], creationflags=flags, close_fds=True)
    return {"started": True}
