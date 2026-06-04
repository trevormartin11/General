"""Small time / formatting helpers shared across modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import markdown as _markdown

from .config import CONFIG


def tz() -> ZoneInfo:
    return ZoneInfo(CONFIG.timezone)


def now_local() -> datetime:
    return datetime.now(tz())


def to_local(dt: datetime) -> datetime:
    """Convert any aware datetime to the configured local timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz())


def parse_utc(iso: str) -> datetime:
    """Parse an ISO timestamp stored in the DB back into an aware datetime."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def week_window(reference: datetime | None = None) -> tuple[datetime, datetime]:
    """Return (start, end) for the current week in local time.

    The week starts Monday at 00:00 local; the window ends at `reference`
    (defaults to now). A Friday report therefore covers Mon -> Fri.
    """
    end = reference or now_local()
    end = to_local(end)
    midnight = end.replace(hour=0, minute=0, second=0, microsecond=0)
    start = midnight - timedelta(days=end.weekday())  # weekday(): Mon=0
    return start, end


def _d(dt: datetime) -> int:
    """Day of month without a leading zero (portable across platforms)."""
    return dt.day


def week_label(start: datetime, end: datetime) -> str:
    """Human label for the report subject, e.g. 'Jun 2–6, 2025'."""
    if start.year != end.year:
        return f"{start:%b} {_d(start)}, {start.year} – {end:%b} {_d(end)}, {end.year}"
    if start.month != end.month:
        return f"{start:%b} {_d(start)} – {end:%b} {_d(end)}, {end.year}"
    return f"{start:%b} {_d(start)}–{_d(end)}, {end.year}"


def fmt_local(dt: datetime) -> str:
    """Friendly local timestamp for listings, e.g. 'Mon Jun 2, 3:45 PM'."""
    local = to_local(dt)
    hour12 = local.strftime("%I").lstrip("0") or "12"
    return f"{local:%a %b} {_d(local)}, {hour12}:{local:%M %p}"


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#f5f5f4;">
    <div style="max-width:640px;margin:0 auto;padding:24px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2937;line-height:1.55;font-size:15px;">
{body}
    </div>
  </body>
</html>
"""


def md_to_html(md_text: str) -> str:
    """Render the Markdown report into a simple, email-friendly HTML document."""
    inner = _markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "nl2br"],
    )
    return _HTML_TEMPLATE.format(body=inner)
