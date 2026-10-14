import html
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


KEYWORDS = (
    "까지", "마감", "제출", "신청", "회신", "보고", "회의", "협의회", "연수",
    "행사", "설명회", "평가", "출장", "수업", "위원회", "점검", "교육", "공람",
)

FULL_DATE_RE = re.compile(
    r"(?P<year>20\d{2})\s*[./년-]\s*(?P<month>1[0-2]|0?\d)\s*[./월-]\s*"
    r"(?P<day>3[01]|[12]\d|0?\d)\s*(?:일)?"
)
SHORT_DATE_RE = re.compile(
    r"(?<![\d./-])(?P<month>1[0-2]|0?[1-9])\s*(?:[./]|월\s*)\s*"
    r"(?P<day>3[01]|[12]\d|0?[1-9])\s*(?:일)?(?![\d./-])"
)
TIME_RE = re.compile(
    r"(?:(?P<ampm>오전|오후)\s*)?(?P<hour>[01]?\d|2[0-3])\s*"
    r"(?:(?::|시\s*)(?P<minute>[0-5]\d)?)\s*(?:분)?"
)
PLACE_RE = re.compile(r"(?:장소|회의실|교육장)\s*[:：]?\s*([^\n,;]{2,60})")
ASSIGNEE_RE = re.compile(r"(?:담당자?|담당)\s*[:：]?\s*([^\n,;]{2,30})")
QUOTE_RE = re.compile(
    r"\n.*?(?:님이 보낸글|님의 보낸 메시지 전달)\s*>>\s*20\d{2}[/-]\d{2}[/-]\d{2}",
    re.DOTALL,
)


@dataclass(frozen=True)
class Message:
    source_table: str
    source_key: int
    direction: str
    message_date: str
    title: str
    person: str
    body: str


def compact(value):
    value = html.unescape(str(value or "")).replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    return value.strip()


def strip_quoted_history(value):
    text = compact(value)
    match = QUOTE_RE.search("\n" + text)
    return text[: max(0, match.start() - 1)].strip() if match else text


def parse_message_date(value):
    match = re.match(r"(20\d{2})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})", value or "")
    if not match:
        return datetime.now()
    return datetime(*map(int, match.groups()))


def _safe_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_short_date(month, day, reference):
    candidates = []
    for year in (reference.year - 1, reference.year, reference.year + 1):
        parsed = _safe_date(year, month, day)
        if parsed:
            distance = abs((parsed - reference.date()).days)
            future_penalty = 0 if parsed >= reference.date() else 30
            candidates.append((distance + future_penalty, parsed))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _parse_time(fragment):
    match = TIME_RE.search(fragment)
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = match.group("ampm")
    if ampm == "오후" and hour < 12:
        hour += 12
    if ampm == "오전" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _context(text, start, end, radius=90):
    return text[max(0, start - radius): min(len(text), end + radius)]


def _mask_list_prefixes(text):
    return re.sub(r"(?m)^\s*\d{1,2}\.\s+", lambda match: " " * len(match.group(0)), text)


def _event_title(message, context):
    title = compact(message.title)
    if title and not title.startswith(("감사", "넵", "네", "확인")):
        return title[:100]
    lines = [compact(line) for line in context.splitlines() if compact(line)]
    useful = [line for line in lines if not FULL_DATE_RE.fullmatch(line) and not SHORT_DATE_RE.fullmatch(line)]
    return (useful[0] if useful else "쿨메신저 일정")[:100]


def _find_value(regex, context):
    match = regex.search(context)
    return compact(match.group(1)) if match else ""


def extract_candidates(message):
    reference = parse_message_date(message.message_date)
    full_text = compact("\n".join(part for part in (message.title, message.body) if part))[:30000]
    body = strip_quoted_history(message.body)
    text = compact("\n".join(part for part in (message.title, body) if part))
    if not any(keyword in text for keyword in KEYWORDS):
        return []

    scan_text = _mask_list_prefixes(text)
    found = []
    occupied = []
    for match in FULL_DATE_RE.finditer(scan_text):
        parsed = _safe_date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
        if parsed:
            found.append((match.start(), match.end(), parsed))
            occupied.append((match.start(), match.end()))
    for match in SHORT_DATE_RE.finditer(scan_text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        parsed = _resolve_short_date(int(match.group("month")), int(match.group("day")), reference)
        if parsed:
            found.append((match.start(), match.end(), parsed))

    candidates = []
    seen = set()
    for sequence, (start, end, event_date) in enumerate(sorted(found), start=1):
        context = _context(text, start, end)
        if not any(keyword in context for keyword in KEYWORDS):
            continue
        after_date = text[end: min(len(text), end + 45)]
        event_time = _parse_time(after_date)
        all_day = event_time is None
        occurrence_key = f"{event_date.isoformat()}-{event_time or 'all-day'}"
        if occurrence_key in seen:
            continue
        seen.add(occurrence_key)
        candidates.append(
            {
                "id": f"{message.source_table}:{message.source_key}:{sequence}",
                "source_table": message.source_table,
                "source_key": message.source_key,
                "occurrence_key": occurrence_key,
                "message_date": message.message_date,
                "direction": message.direction,
                "person": message.person,
                "title": _event_title(message, context),
                "date": event_date.isoformat(),
                "time": event_time or "",
                "end_time": "",
                "all_day": all_day,
                "location": _find_value(PLACE_RE, context),
                "assignee": _find_value(ASSIGNEE_RE, context) or compact(message.person),
                "context": compact(context)[:500],
                "full_text": full_text,
            }
        )
    return candidates


def read_messages(source_db: Path, days=90):
    cutoff = (datetime.now() - timedelta(days=max(1, min(days, 365)))).strftime("%Y/%m/%d")
    uri = f"file:{source_db.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    specs = (
        ("tbl_recv", "받은 메모", "ReceiveDate", "Sender"),
        ("tbl_send", "보낸 메모", "SendDate", "Receiver"),
    )
    messages = []
    for table, direction, date_col, person_col in specs:
        sql = f"""
            SELECT MessageKey, Title, {person_col} AS Person, {date_col} AS MessageDate,
                   MessageText, MessageBody
            FROM {table}
            WHERE {date_col} >= ? AND (DeletedDate IS NULL OR DeletedDate = '')
            ORDER BY {date_col} DESC, MessageKey DESC
        """
        for row in con.execute(sql, (cutoff,)):
            messages.append(
                Message(
                    source_table=table,
                    source_key=int(row["MessageKey"]),
                    direction=direction,
                    message_date=compact(row["MessageDate"]),
                    title=compact(row["Title"]),
                    person=compact(row["Person"]),
                    body=compact(row["MessageText"]) or compact(row["MessageBody"]),
                )
            )
    con.close()
    return messages


def extract_from_database(source_db: Path, days=90):
    candidates = []
    for message in read_messages(source_db, days=days):
        candidates.extend(extract_candidates(message))
    candidates.sort(key=lambda item: (item["date"], item["time"], item["source_key"]))
    return candidates


def default_end_time(start_time):
    if not start_time:
        return ""
    hour, minute = map(int, start_time.split(":"))
    total = hour * 60 + minute + 60
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def next_date(value):
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return (parsed + timedelta(days=1)).isoformat()


def escape_ics(value):
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def build_ics(events):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CoolMemo Calendar//KO", "CALSCALE:GREGORIAN"]
    for event in events:
        lines.extend(["BEGIN:VEVENT", f"UID:{escape_ics(event['uid'])}", f"DTSTAMP:{now}"])
        if event.get("all_day"):
            lines.append(f"DTSTART;VALUE=DATE:{event['date'].replace('-', '')}")
            lines.append(f"DTEND;VALUE=DATE:{next_date(event['date']).replace('-', '')}")
        else:
            start = f"{event['date'].replace('-', '')}T{event['time'].replace(':', '')}00"
            end_time = event.get("end_time") or default_end_time(event["time"])
            end_date = event["date"]
            if end_time <= event["time"]:
                end_date = next_date(event["date"])
            end = f"{end_date.replace('-', '')}T{end_time.replace(':', '')}00"
            lines.append(f"DTSTART;TZID=Asia/Seoul:{start}")
            lines.append(f"DTEND;TZID=Asia/Seoul:{end}")
        lines.append(f"SUMMARY:{escape_ics(event.get('title'))}")
        if event.get("location"):
            lines.append(f"LOCATION:{escape_ics(event['location'])}")
        if event.get("description"):
            lines.append(f"DESCRIPTION:{escape_ics(event['description'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
