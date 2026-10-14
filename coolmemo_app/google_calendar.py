import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config as app_config
from .config import TIME_ZONE
from .extractor import default_end_time, next_date
from .storage import load_client_config, load_token, save_token


LIST_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
SCOPES = "https://www.googleapis.com/auth/calendar.events " + LIST_SCOPE
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL = "https://www.googleapis.com/calendar/v3"


def _desktop_config(value):
    if not isinstance(value, dict):
        raise ValueError("Google OAuth JSON 형식이 올바르지 않습니다.")
    config = value.get("installed") or value.get("web") or value
    if not config.get("client_id"):
        raise ValueError("OAuth 클라이언트 ID가 없습니다.")
    return config


def auth_url(state_store):
    config = _desktop_config(load_client_config())
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    state_store[state] = {"verifier": verifier, "created": time.time()}
    params = {
        "client_id": config["client_id"],
        "redirect_uri": f"{app_config.BASE_URL}/oauth/callback",
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def _post_form(url, values):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"Google 인증 요청 실패: {detail}") from error


def exchange_code(code, state, state_store):
    saved = state_store.pop(state, None)
    if not saved or time.time() - saved["created"] > 600:
        raise ValueError("인증 요청이 만료되었거나 올바르지 않습니다.")
    config = _desktop_config(load_client_config())
    payload = {
        "code": code,
        "client_id": config["client_id"],
        "redirect_uri": f"{app_config.BASE_URL}/oauth/callback",
        "grant_type": "authorization_code",
        "code_verifier": saved["verifier"],
    }
    if config.get("client_secret"):
        payload["client_secret"] = config["client_secret"]
    token = _post_form(TOKEN_URL, payload)
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600)) - 60
    save_token(token)
    return token


def access_token():
    token = load_token()
    if not token:
        raise ValueError("Google Calendar 연결이 필요합니다.")
    if token.get("access_token") and token.get("expires_at", 0) > time.time():
        return token["access_token"]
    if not token.get("refresh_token"):
        raise ValueError("Google Calendar를 다시 연결해 주세요.")
    config = _desktop_config(load_client_config())
    payload = {
        "client_id": config["client_id"],
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    }
    if config.get("client_secret"):
        payload["client_secret"] = config["client_secret"]
    refreshed = _post_form(TOKEN_URL, payload)
    token.update(refreshed)
    token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600)) - 60
    save_token(token)
    return token["access_token"]


def _request(method, path, payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        API_URL + path,
        data=body,
        headers={"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json; charset=utf-8"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"Google Calendar 요청 실패: {detail}") from error


def event_payload(event):
    payload = {
        "summary": event["title"],
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "extendedProperties": {
            "private": {
                "coolmemoSource": f"{event['source_table']}:{event['source_key']}:{event['occurrence_key']}"
            }
        },
    }
    if event.get("all_day"):
        payload["start"] = {"date": event["date"]}
        payload["end"] = {"date": next_date(event["date"])}
    else:
        end_time = event.get("end_time") or default_end_time(event["time"])
        end_date = event["date"] if end_time > event["time"] else next_date(event["date"])
        payload["start"] = {"dateTime": f"{event['date']}T{event['time']}:00+09:00", "timeZone": TIME_ZONE}
        payload["end"] = {"dateTime": f"{end_date}T{end_time}:00+09:00", "timeZone": TIME_ZONE}
    reminder = int(event.get("reminder_minutes", -2))
    if reminder == -1:
        payload["reminders"] = {"useDefault": True}
    elif reminder < 0:
        payload["reminders"] = {"useDefault": False, "overrides": []}
    else:
        payload["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": reminder}],
        }
    return payload


def _cal(calendar_id):
    return urllib.parse.quote(calendar_id or "primary", safe="")


def has_list_scope():
    token = load_token() or {}
    return LIST_SCOPE in str(token.get("scope", "")).split()


def list_calendars():
    """일정을 쓸 수 있는 캘린더 목록(기본 캘린더가 맨 앞)."""
    if not has_list_scope():
        raise PermissionError("캘린더 목록을 보려면 Google 연결을 다시 승인해 주세요.")
    data = _request("GET", "/users/me/calendarList?minAccessRole=writer&maxResults=250")
    items = [
        {
            "id": entry["id"],
            "name": entry.get("summaryOverride") or entry.get("summary", entry["id"]),
            "primary": bool(entry.get("primary")),
            "color": entry.get("backgroundColor", ""),
        }
        for entry in data.get("items", [])
    ]
    return sorted(items, key=lambda entry: not entry["primary"])


def create_event(event, calendar_id="primary"):
    return _request("POST", f"/calendars/{_cal(calendar_id)}/events", event_payload(event))


def update_event(event_id, event, calendar_id="primary"):
    quoted = urllib.parse.quote(event_id, safe="")
    return _request("PATCH", f"/calendars/{_cal(calendar_id)}/events/{quoted}", event_payload(event))


def move_event(event_id, source_calendar, destination_calendar):
    quoted = urllib.parse.quote(event_id, safe="")
    destination = urllib.parse.quote(destination_calendar, safe="")
    return _request(
        "POST", f"/calendars/{_cal(source_calendar)}/events/{quoted}/move?destination={destination}"
    )
