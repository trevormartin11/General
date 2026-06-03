"""Smart compile: turn a week of raw notes into a polished report with Claude.

One `messages` call per report. The static instructions + property list live
in a cached `system` block (stable prefix); the week's notes are the volatile
user turn. See the Anthropic prompt-caching guidance: keep stable content first.
"""

from __future__ import annotations

from dataclasses import dataclass

from anthropic import AsyncAnthropic

from .config import CONFIG
from .db import Entry
from .util import fmt_local, md_to_html, parse_utc, week_label, week_window

# ---------------------------------------------------------------------------
# Static system instructions (the cached prefix). {placeholders} are filled
# from config — they change rarely, so the cache prefix stays stable week to
# week. The week's actual notes never appear here; they go in the user turn.
# ---------------------------------------------------------------------------
SYSTEM_TEMPLATE = """\
You are the reporting assistant for a family-office property manager. Each week \
the manager logs short, free-text notes from their phone while working across \
the family's properties. Your job is to turn those raw notes into a single \
polished, owner-facing "Weekly Property Update" that the owners read by email.

WHO IT'S FOR
- The audience is the property owners ({owners}). Write to them directly in a \
warm but professional, concise tone — the voice of a trusted manager. No \
jargon, no filler, no emojis.

THE PROPERTIES
{properties_block}
Map each note to one of these properties, matching loosely (e.g. "the lake \
place" -> "Lakehouse"). If a note clearly isn't about a specific property, or \
you genuinely can't tell, group it under "General / Across Properties". Never \
invent a property that isn't referenced.

WHAT TO PRODUCE (Markdown only)
Open with one or two sentences summarizing the week. Then one section per \
property that had activity, using "## <Property>" headings. Within each property:
- **Work completed** — a short bullet list of what was done, in plain past tense.
- **Expenses** — one bullet per spend as "Vendor — short description — $amount", \
then "**Subtotal: $X**". Omit this block entirely if the property had no costs.
- **Open follow-ups** — bullets for anything pending, scheduled, awaiting a \
quote, or needing an owner decision. Omit if there are none.
Finish with a "## Summary" section containing "**Total expenses this week: \
$X**" (the sum of all explicitly stated amounts) and, if useful, one line \
naming the most important open items. Close with a sign-off from {manager}.

RULES
- Use only what is in the notes. Do not invent work, vendors, amounts, or dates.
- Only sum dollar figures that are explicitly stated. If an amount is vague \
("a few hundred"), list it but flag it as a follow-up to confirm and leave it \
out of the total.
- When something is ambiguous, surface it as a follow-up rather than guessing.
- Format money as $1,250 (commas, no cents unless cents were given).
- Keep it skimmable: short bullets, no walls of text.
- Output ONLY the report body in Markdown. Do not add an email subject line, a \
"To:" line, or any commentary about how you produced it.
"""


@dataclass
class Report:
    subject: str
    markdown: str
    html: str
    week_label: str
    num_entries: int


def _properties_block() -> str:
    if CONFIG.properties:
        listed = "\n".join(f"- {name}" for name in CONFIG.properties)
        return "The family's properties (with the nicknames the manager uses):\n" + listed
    return (
        "No fixed property list was configured — infer the property names "
        "directly from the notes."
    )


def _build_system() -> list[dict]:
    text = SYSTEM_TEMPLATE.format(
        owners=CONFIG.owners_label,
        properties_block=_properties_block(),
        manager=CONFIG.manager_name,
    )
    # cache_control marks this stable prefix as cacheable. (For the weekly
    # cadence the 5-minute cache rarely lives long enough to hit, but it costs
    # nothing and helps if /report is run a few times back-to-back.)
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _build_user(entries: list[Entry], label: str) -> str:
    lines = [
        f"Here are the notes I logged for {label}. "
        "Please compile the Weekly Property Update.",
        "",
    ]
    for e in entries:
        lines.append(f"- [{fmt_local(parse_utc(e.ts_utc))}] {e.raw_text}")
    return "\n".join(lines)


async def compile_report(entries: list[Entry], reference=None) -> Report:
    """Call Claude once and return the finished report (Markdown + HTML)."""
    start, end = week_window(reference)
    label = week_label(start, end)

    client = AsyncAnthropic(api_key=CONFIG.anthropic_api_key)

    kwargs = dict(
        model=CONFIG.anthropic_model,
        max_tokens=CONFIG.max_tokens,
        system=_build_system(),
        messages=[{"role": "user", "content": _build_user(entries, label)}],
    )
    if CONFIG.thinking == "adaptive":
        kwargs["thinking"] = {"type": "adaptive"}

    # Stream and collect the final message — robust against HTTP timeouts at
    # higher max_tokens and when adaptive thinking is on.
    async with client.messages.stream(**kwargs) as stream:
        message = await stream.get_final_message()

    markdown = "".join(b.text for b in message.content if b.type == "text").strip()

    return Report(
        subject=f"Property Update — Week of {label}",
        markdown=markdown,
        html=md_to_html(markdown),
        week_label=label,
        num_entries=len(entries),
    )
