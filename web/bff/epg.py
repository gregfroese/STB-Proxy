"""Extract now/next per ``epgId`` from STB-Proxy's XMLTV guide (spec 2.6 / ticket 06).

The guide is multi-MB; this is a single streaming pass that keeps at most one
*now* and one *next* programme per channel, skipping everything else.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

_TIME_RE = re.compile(r"^(\d{14})(?:\s+([+-]\d{4}))?$")


def parse_xmltv_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    match = _TIME_RE.match(raw.strip())
    if not match:
        return None
    base = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    if match.group(2):
        sign = 1 if match.group(2)[0] == "+" else -1
        hours = int(match.group(2)[1:3])
        minutes = int(match.group(2)[3:5])
        tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
    else:
        tz = timezone.utc
    return base.replace(tzinfo=tz)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(elem: ET.Element) -> str | None:
    text = (elem.text or "").strip()
    return text or None


def parse_now_next(xml_bytes: bytes, now: datetime) -> dict[str, dict]:
    """``{"<epgId>": {"now": Programme|None, "next": Programme|None}}``."""
    now_by: dict[str, tuple[datetime, dict]] = {}
    next_by: dict[str, tuple[datetime, dict]] = {}
    next_start: dict[str, datetime] = {}

    context = ET.iterparse(io.BytesIO(xml_bytes), events=("start", "end"))
    try:
        _, root = next(context)
    except StopIteration:
        return {}

    for event, elem in context:
        if event != "end":
            continue
        if _localname(elem.tag) != "programme":
            # Keep child elements (title/desc) intact until their programme is
            # processed; they are freed when the programme is cleared below.
            continue

        channel = elem.get("channel")
        start = parse_xmltv_time(elem.get("start"))
        stop = parse_xmltv_time(elem.get("stop"))

        if channel and start:
            is_now = start <= now and (stop is None or now < stop)
            is_next = start > now
            if is_now or is_next:
                title = None
                description = None
                for child in elem:
                    name = _localname(child.tag)
                    if name == "title" and title is None:
                        title = _text(child)
                    elif name == "desc" and description is None:
                        description = _text(child)
                if title:
                    programme = {
                        "title": title,
                        "start": start.isoformat(),
                        "stop": stop.isoformat() if stop else None,
                        "description": description,
                    }
                    if is_now:
                        existing = now_by.get(channel)
                        if existing is None or start > existing[0]:
                            now_by[channel] = (start, programme)
                    else:
                        existing_start = next_start.get(channel)
                        if existing_start is None or start < existing_start:
                            next_start[channel] = start
                            next_by[channel] = (start, programme)

        elem.clear()
        root.clear()

    channels = set(now_by) | set(next_by)
    return {
        channel: {
            "now": now_by.get(channel, (None, None))[1],
            "next": next_by.get(channel, (None, None))[1],
        }
        for channel in channels
    }
