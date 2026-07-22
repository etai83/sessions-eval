"""Session Review static HTML generator (Antigravity Conversations + Session Logs).

Owns scan, cross-link matching, soft size caps, and offline HTML under
``sessions/`` + ``session-logs/``. Not part of ``DashboardGenerator.generate``.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from bench_suite.config import resolve_session_review_caps
from bench_suite.session_caps import (
    format_truncation_banner_html,
    load_transcript_lines,
    select_transcript_head,
    sidecar_truncation_note,
    trail_end_sentinel,
    truncate_sidecar,
    truncated_badge_html,
)

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
# Accept both `**Conversation ID**: uuid` and `**Conversation ID:** uuid`.
CONVERSATION_ID_RE = re.compile(
    r"\*\*Conversation ID:\*\*\s*`?(?P<id>" + UUID_RE.pattern + r")`?"
    r"|\*\*Conversation ID\*\*\s*:\s*`?(?P<id2>" + UUID_RE.pattern + r")`?",
    re.IGNORECASE,
)
# Metadata-style Session ID only (own line; not inline domain prose).
SESSION_ID_META_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:"
    r"\*\*Session ID:\*\*\s*`?(?P<id>" + UUID_RE.pattern + r")`?"
    r"|\*\*Session ID\*\*\s*:\s*`?(?P<id2>" + UUID_RE.pattern + r")`?"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)
BRAIN_PATH_RE = re.compile(
    r"(?:file://)?[^\s\)\"']*?/\.gemini/antigravity(?:-ide)?/brain/"
    r"(?P<id>" + UUID_RE.pattern + r")",
    re.IGNORECASE,
)

OUTCOME_HEADINGS = (
    "Results / Outcomes",
    "Results Observed",
    "Outcomes",
    "Results",
    "Result",
)

SYSTEM_NOISE_TYPES = frozenset(
    {
        "CONVERSATION_HISTORY",
        "CHECKPOINT",
        "EPHEMERAL",
    }
)
USER_STEP_TYPES = frozenset({"USER_INPUT", "USER_EXPLICIT"})
SIDECAR_NAMES = ("walkthrough.md", "task.md", "implementation_plan.md")

PREVIEW_CHARS = 120
OUTCOME_SNIPPET_CHARS = 100
PLANNER_PREVIEW = 280
TOOL_ARG_PREVIEW = 160


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def short_id(conversation_id: str) -> str:
    return conversation_id[:8] if conversation_id else ""


def log_slug(rel_path: str) -> str:
    """URL-safe slug from path relative to session_logs root (no .md suffix)."""
    s = rel_path.replace("\\", "/").strip("/")
    if s.lower().endswith(".md"):
        s = s[:-3]
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s or "log"


def strip_user_request_tags(text: str) -> str:
    t = re.sub(r"</?USER_REQUEST>", "", text, flags=re.IGNORECASE)
    return t.strip()


def extract_conversation_link(text: str) -> tuple[str, str] | None:
    """
    Strong-signal Conversation id from a Session Log body.

    Priority: Conversation ID field → metadata Session ID → brain path UUID.
    Returns (uuid_lower, reason) or None.
    """
    m = CONVERSATION_ID_RE.search(text)
    if m:
        cid = m.group("id") or m.group("id2")
        return cid.lower(), "conversation_id"

    # Prefer Conversation ID if both somehow present later; Session ID only as meta line.
    m = SESSION_ID_META_RE.search(text)
    if m:
        cid = m.group("id") or m.group("id2")
        return cid.lower(), "session_id"

    m = BRAIN_PATH_RE.search(text)
    if m:
        return m.group("id").lower(), "brain_path"

    return None


def _heading_level_and_title(line: str) -> tuple[int, str] | None:
    m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def extract_markdown_section(text: str, titles: Sequence[str]) -> tuple[str, str] | None:
    """
    Return (matched_title, body) for the first matching AT heading (any level).

    Title match is case-insensitive; prefers earlier titles in ``titles`` order
    when multiple match (scan once, pick best priority).
    """
    lines = text.splitlines()
    candidates: list[tuple[int, str, int, int]] = []  # priority, title, start, end
    i = 0
    while i < len(lines):
        ht = _heading_level_and_title(lines[i])
        if ht is None:
            i += 1
            continue
        level, title = ht
        for pri, want in enumerate(titles):
            tlow, wlow = title.lower(), want.lower()
            # Exact match; allow "Results Observed …" suffix variants only.
            if tlow == wlow or (
                wlow == "results observed" and tlow.startswith("results observed")
            ):
                j = i + 1
                while j < len(lines):
                    nxt = _heading_level_and_title(lines[j])
                    if nxt is not None and nxt[0] <= level:
                        break
                    j += 1
                candidates.append((pri, title, i + 1, j))
                break
        i += 1
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    _, title, start, end = candidates[0]
    body = "\n".join(lines[start:end]).strip()
    return title, body


def omit_markdown_section(text: str, section_title: str) -> str:
    """Drop the first heading block whose title matches section_title (ci)."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        ht = _heading_level_and_title(lines[i])
        if ht is not None and ht[1].lower() == section_title.lower():
            level = ht[0]
            i += 1
            while i < len(lines):
                nxt = _heading_level_and_title(lines[i])
                if nxt is not None and nxt[0] <= level:
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).strip() + ("\n" if text.endswith("\n") else "")


def extract_session_log_title(text: str, fallback_stem: str) -> str:
    for line in text.splitlines()[:30]:
        m = re.match(r"^#\s+(.+)$", line.strip())
        if not m:
            continue
        title = m.group(1).strip()
        title = re.sub(r"^Session Log\s*[:\-–—]\s*", "", title, flags=re.IGNORECASE)
        return title.strip() or fallback_stem
    return fallback_stem


def extract_label(text: str) -> str | None:
    m = re.search(r"\*\*Label\*\*\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"^\s*Label\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


def extract_log_date(text: str, path: Path) -> str:
    m = re.search(
        r"\*\*Date\*\*\s*:\s*(\d{4}-\d{2}-\d{2})",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    if m:
        return m.group(1)
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except OSError:
        return ""


def simple_markdown_to_html(text: str) -> str:
    """Minimal Markdown → HTML for session-log bodies (no external deps)."""
    if not text.strip():
        return ""
    lines = text.splitlines()
    parts: list[str] = []
    i = 0
    in_code = False
    code_buf: list[str] = []
    para: list[str] = []
    list_items: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if para:
            body = " ".join(para)
            parts.append(f"<p>{_inline_md(body)}</p>")
            para = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            items = "".join(f"<li>{_inline_md(it)}</li>" for it in list_items)
            parts.append(f"<ul>{items}</ul>")
            list_items = []

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush_para()
            flush_list()
            if in_code:
                parts.append(f"<pre><code>{_esc(chr(10).join(code_buf))}</code></pre>")
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        ht = _heading_level_and_title(line)
        if ht is not None:
            flush_para()
            flush_list()
            level, title = ht
            parts.append(f"<h{level}>{_inline_md(title)}</h{level}>")
            i += 1
            continue
        if re.match(r"^\s*[-*]\s+", line):
            flush_para()
            list_items.append(re.sub(r"^\s*[-*]\s+", "", line))
            i += 1
            continue
        if not line.strip():
            flush_para()
            flush_list()
            i += 1
            continue
        flush_list()
        para.append(line.strip())
        i += 1
    flush_para()
    flush_list()
    if in_code and code_buf:
        parts.append(f"<pre><code>{_esc(chr(10).join(code_buf))}</code></pre>")
    return "\n".join(parts)


def _inline_md(text: str) -> str:
    """Escape then apply limited bold/code/backtick."""
    # Protect code spans
    chunks: list[str] = []
    pos = 0
    for m in re.finditer(r"`([^`]+)`", text):
        chunks.append(_esc(text[pos : m.start()]))
        chunks.append(f"<code>{_esc(m.group(1))}</code>")
        pos = m.end()
    chunks.append(_esc(text[pos:]))
    s = "".join(chunks)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


@dataclass
class SessionLogRecord:
    rel_path: str
    slug: str
    abs_path: Path
    title: str
    date: str
    label: str | None
    text: str
    outcome_title: str | None
    outcome_body: str | None
    linked_conversation_id: str | None
    link_reason: str | None

    @property
    def outcome_snippet(self) -> str:
        if not self.outcome_body:
            return "—"
        one = re.sub(r"\s+", " ", self.outcome_body).strip()
        if len(one) <= OUTCOME_SNIPPET_CHARS:
            return one
        return one[: OUTCOME_SNIPPET_CHARS - 1] + "…"

    @property
    def path_hint(self) -> str:
        parent = str(Path(self.rel_path).parent)
        if parent in (".", ""):
            return ""
        return parent.replace("\\", "/") + "/"


@dataclass
class ConversationRecord:
    conversation_id: str
    brain_root: Path
    dir_path: Path
    transcript_path: Path | None
    has_full_transcript: bool
    has_compact_only: bool
    sidecars: dict[str, Path] = field(default_factory=dict)
    date_start: str = ""
    date_end: str = ""
    first_user_preview: str = ""
    user_requests: list[str] = field(default_factory=list)
    linked_logs: list[SessionLogRecord] = field(default_factory=list)

    @property
    def date_display(self) -> str:
        if self.date_start and self.date_end and self.date_start != self.date_end:
            return f"{self.date_start} → {self.date_end}"
        return self.date_start or self.date_end or ""

    @property
    def sort_date(self) -> str:
        return self.date_end or self.date_start or ""


def scan_session_logs(session_logs_root: Path) -> list[SessionLogRecord]:
    root = Path(session_logs_root)
    if not root.is_dir():
        return []
    records: list[SessionLogRecord] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        link = extract_conversation_link(text)
        outcome = extract_markdown_section(text, OUTCOME_HEADINGS)
        records.append(
            SessionLogRecord(
                rel_path=rel,
                slug=log_slug(rel),
                abs_path=path,
                title=extract_session_log_title(text, path.stem),
                date=extract_log_date(text, path),
                label=extract_label(text),
                text=text,
                outcome_title=outcome[0] if outcome else None,
                outcome_body=outcome[1] if outcome else None,
                linked_conversation_id=link[0] if link else None,
                link_reason=link[1] if link else None,
            )
        )
    # Stable unique slugs
    seen: dict[str, int] = {}
    for rec in records:
        base = rec.slug
        n = seen.get(base, 0)
        seen[base] = n + 1
        if n:
            rec.slug = f"{base}-{n + 1}"
    return records


def _read_transcript_meta(transcript_path: Path) -> tuple[str, str, str, list[str]]:
    """Return date_start, date_end, first_user_preview, all user request texts."""
    date_start = ""
    date_end = ""
    first_preview = ""
    user_requests: list[str] = []
    try:
        for line in transcript_path.open(encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(obj.get("created_at") or "")[:10]
            if ts:
                if not date_start or ts < date_start:
                    date_start = ts
                if not date_end or ts > date_end:
                    date_end = ts
            typ = str(obj.get("type") or "")
            src = str(obj.get("source") or "")
            if typ in USER_STEP_TYPES or src in USER_STEP_TYPES or typ == "USER_INPUT":
                content = strip_user_request_tags(str(obj.get("content") or ""))
                if content:
                    user_requests.append(content)
                    if not first_preview:
                        one = re.sub(r"\s+", " ", content)
                        first_preview = (
                            one
                            if len(one) <= PREVIEW_CHARS
                            else one[: PREVIEW_CHARS - 1] + "…"
                        )
    except OSError:
        pass
    return date_start, date_end, first_preview, user_requests


def scan_conversations(
    brain_roots: Sequence[Path],
) -> list[ConversationRecord]:
    by_id: dict[str, ConversationRecord] = {}
    for root in brain_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            cid = child.name.lower()
            if not UUID_RE.fullmatch(cid):
                continue
            logs_dir = child / ".system_generated" / "logs"
            full = logs_dir / "transcript_full.jsonl"
            compact = logs_dir / "transcript.jsonl"
            has_full = full.is_file()
            has_compact = compact.is_file() and not has_full
            transcript = full if has_full else (compact if compact.is_file() else None)
            sidecars: dict[str, Path] = {}
            for name in SIDECAR_NAMES:
                p = child / name
                if p.is_file():
                    sidecars[name] = p
            date_start = date_end = preview = ""
            user_reqs: list[str] = []
            if transcript is not None:
                date_start, date_end, preview, user_reqs = _read_transcript_meta(
                    transcript
                )
            if not date_start:
                try:
                    date_start = datetime.fromtimestamp(
                        child.stat().st_mtime, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                    date_end = date_start
                except OSError:
                    pass
            if not preview:
                preview = f"{short_id(cid)} — no transcript"
            rec = ConversationRecord(
                conversation_id=cid,
                brain_root=root,
                dir_path=child,
                transcript_path=transcript,
                has_full_transcript=has_full,
                has_compact_only=has_compact,
                sidecars=sidecars,
                date_start=date_start,
                date_end=date_end,
                first_user_preview=preview,
                user_requests=user_reqs,
            )
            # Prefer primary root if already seen (first root wins)
            if cid not in by_id:
                by_id[cid] = rec
    return list(by_id.values())


def link_records(
    conversations: list[ConversationRecord],
    logs: list[SessionLogRecord],
) -> None:
    """Attach matching logs to conversations; drop link if UUID not in brain scan."""
    by_id = {c.conversation_id: c for c in conversations}
    for log in logs:
        cid = log.linked_conversation_id
        if not cid:
            continue
        conv = by_id.get(cid)
        if conv is None:
            # Strong signal but brain dir missing — treat as unlinked for display
            log.linked_conversation_id = None
            log.link_reason = None
            continue
        conv.linked_logs.append(log)
    for conv in conversations:
        conv.linked_logs.sort(key=lambda L: (L.date, L.rel_path), reverse=True)


def _parse_step(line: str) -> dict[str, Any]:
    try:
        obj = json.loads(line if not line.endswith("\n") else line[:-1])
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return {"type": "RAW", "content": line.rstrip("\n")}


def _shorten(text: str, limit: int) -> str:
    one = re.sub(r"\s+", " ", text).strip()
    if len(one) <= limit:
        return one
    return one[: limit - 1] + "…"


def summarize_step_card(obj: dict[str, Any], *, partial: bool = False) -> str | None:
    """HTML card for summary trail, or None to omit (SYSTEM noise)."""
    typ = str(obj.get("type") or "")
    src = str(obj.get("source") or "")
    if typ in SYSTEM_NOISE_TYPES or src in SYSTEM_NOISE_TYPES:
        return None
    partial_note = ' <span class="badge badge-truncated">partial step</span>' if partial else ""
    if typ in USER_STEP_TYPES or typ == "USER_INPUT" or src in ("USER_EXPLICIT", "USER_INPUT"):
        content = strip_user_request_tags(str(obj.get("content") or ""))
        return (
            f'<div class="step-card step-user"><div class="step-kind">User</div>'
            f"<pre>{_esc(content)}</pre>{partial_note}</div>"
        )
    if typ == "PLANNER_RESPONSE" or (src == "MODEL" and not obj.get("tool_calls")):
        body = str(obj.get("content") or obj.get("thinking") or "")
        return (
            f'<div class="step-card step-planner"><div class="step-kind">Planner</div>'
            f"<pre>{_esc(_shorten(body, PLANNER_PREVIEW))}</pre>{partial_note}</div>"
        )
    # Tools: type name or tool_calls
    tools = obj.get("tool_calls")
    if isinstance(tools, list) and tools:
        bits = []
        for tc in tools[:3]:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name") or "tool"
            args = tc.get("args") or tc.get("arguments") or {}
            arg_s = _shorten(json.dumps(args, ensure_ascii=False), TOOL_ARG_PREVIEW)
            bits.append(f"<li><strong>{_esc(name)}</strong> <code>{_esc(arg_s)}</code></li>")
        return (
            f'<div class="step-card step-tool"><div class="step-kind">Tools</div>'
            f"<ul>{''.join(bits)}</ul>{partial_note}</div>"
        )
    # Named tool step types (VIEW_FILE, RUN_COMMAND, …)
    if typ and typ not in USER_STEP_TYPES:
        content = obj.get("content")
        extra = ""
        if content:
            extra = f"<pre>{_esc(_shorten(str(content), TOOL_ARG_PREVIEW))}</pre>"
        return (
            f'<div class="step-card step-tool"><div class="step-kind">{_esc(typ)}</div>'
            f"{extra}{partial_note}</div>"
        )
    return (
        f'<div class="step-card"><div class="step-kind">Step</div>'
        f"<pre>{_esc(_shorten(json.dumps(obj, ensure_ascii=False), PLANNER_PREVIEW))}</pre>"
        f"{partial_note}</div>"
    )


_SHARED_CSS = """
    body { font-family: system-ui, sans-serif; margin: 2rem; color: #0f172a; max-width: 1100px; }
    a { color: #0369a1; }
    .crumbs { color: #64748b; font-size: 0.9rem; margin-bottom: 1rem; }
    .crumbs a { color: #0369a1; text-decoration: none; }
    .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px;
             font-size: 0.75rem; font-weight: 600; margin-right: 0.35rem; }
    .badge-linked { background: #dcfce7; color: #166534; }
    .badge-unlinked { background: #f1f5f9; color: #475569; }
    .badge-artifact { background: #e0f2fe; color: #075985; }
    .badge-truncated { background: #fee2e2; color: #991b1b; }
    table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
    th, td { border: 1px solid #e2e8f0; padding: 0.5rem 0.75rem; text-align: left; vertical-align: top; }
    th { background: #f1f5f9; cursor: pointer; user-select: none; }
    th:hover { background: #e2e8f0; }
    .muted { color: #64748b; }
    .mono { font-family: ui-monospace, monospace; font-size: 0.85rem; }
    .outcome-band { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px;
                    padding: 1rem; margin: 1rem 0; }
    .outcome-band.empty { background: #f8fafc; border-color: #e2e8f0; }
    .truncation-banner { background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px;
                         padding: 0.75rem 1rem; margin: 1rem 0; }
    .step-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.75rem;
                 margin: 0.5rem 0; background: #f8fafc; }
    .step-kind { font-weight: 600; font-size: 0.8rem; color: #475569; margin-bottom: 0.35rem; }
    .step-user { background: #eff6ff; }
    .step-planner { background: #faf5ff; }
    pre { white-space: pre-wrap; word-break: break-word; margin: 0; font-size: 0.85rem; }
    details { margin: 1rem 0; }
    summary { cursor: pointer; font-weight: 600; }
    .path-hint { color: #94a3b8; font-size: 0.85rem; }
"""


def _crumbs(items: list[tuple[str, str | None]]) -> str:
    bits = []
    for label, href in items:
        if href:
            bits.append(f'<a href="{_esc(href)}">{_esc(label)}</a>')
        else:
            bits.append(_esc(label))
    return '<nav class="crumbs">' + " / ".join(bits) + "</nav>"


def _sort_script(table_id: str) -> str:
    return f"""
<script>
document.querySelectorAll('#{table_id} th[data-col]').forEach((th) => {{
  th.addEventListener('click', () => {{
    const table = document.getElementById('{table_id}');
    const tbody = table.tBodies[0];
    const col = Number(th.dataset.col);
    const rows = Array.from(tbody.rows);
    const asc = th.dataset.dir !== 'asc';
    th.dataset.dir = asc ? 'asc' : 'desc';
    rows.sort((a, b) => {{
      const av = a.cells[col].dataset.value ?? a.cells[col].textContent;
      const bv = b.cells[col].dataset.value ?? b.cells[col].textContent;
      const an = Number(av), bn = Number(bv);
      if (!Number.isNaN(an) && !Number.isNaN(bn) && av !== '' && bv !== '')
        return asc ? an - bn : bn - an;
      return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    }});
    rows.forEach((r) => tbody.appendChild(r));
  }});
}});
</script>
"""


def render_conversations_index(conversations: list[ConversationRecord]) -> str:
    rows_html = []
    ordered = sorted(conversations, key=lambda c: c.sort_date, reverse=True)
    for c in ordered:
        n_logs = len(c.linked_logs)
        if n_logs:
            link_cell = f'{n_logs} log(s)'
            outcome = c.linked_logs[0].outcome_snippet
        else:
            link_cell = '<span class="badge badge-unlinked">unlinked</span>'
            outcome = "—"
        badges = []
        if c.has_full_transcript:
            badges.append('<span class="badge badge-artifact">Full transcript</span>')
        elif c.has_compact_only:
            badges.append('<span class="badge badge-artifact">Compact only</span>')
        if "walkthrough.md" in c.sidecars:
            badges.append('<span class="badge badge-artifact">Walkthrough</span>')
        href = f"{_esc(c.conversation_id)}.html"
        rows_html.append(
            "<tr>"
            f'<td data-value="{_esc(c.sort_date)}">{_esc(c.date_display)}</td>'
            f'<td><a href="{href}">{_esc(c.first_user_preview)}</a></td>'
            f'<td class="mono" title="{_esc(c.conversation_id)}">'
            f'<a href="{href}">{_esc(short_id(c.conversation_id))}</a></td>'
            f"<td>{link_cell}</td>"
            f"<td>{_esc(outcome)}</td>"
            f"<td>{''.join(badges) if badges else '—'}</td>"
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Antigravity Conversations</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {_crumbs([("Leaderboard", "../index.html"), ("Antigravity Conversations", None)])}
  <h1>Antigravity Conversations</h1>
  <p class="muted">{len(ordered)} conversation(s). Default sort: date descending. Click headers to re-sort.</p>
  <table id="conv-table">
    <thead><tr>
      <th data-col="0">Date</th>
      <th data-col="1">Title / preview</th>
      <th data-col="2">Conversation id</th>
      <th data-col="3">Linked logs</th>
      <th data-col="4">Outcome snippet</th>
      <th data-col="5">Artifacts</th>
    </tr></thead>
    <tbody>
      {"".join(rows_html) if rows_html else '<tr><td colspan="6">No conversations found</td></tr>'}
    </tbody>
  </table>
  {_sort_script("conv-table")}
</body>
</html>
"""


def render_session_logs_index(logs: list[SessionLogRecord]) -> str:
    ordered = sorted(logs, key=lambda L: (L.date, L.rel_path), reverse=True)
    rows_html = []
    for log in ordered:
        if log.linked_conversation_id:
            sid = short_id(log.linked_conversation_id)
            link_cell = (
                f'<span class="badge badge-linked">Linked</span> '
                f'<a class="mono" href="../sessions/{_esc(log.linked_conversation_id)}.html">'
                f"{_esc(sid)}</a>"
            )
        else:
            link_cell = '<span class="badge badge-unlinked">Unlinked</span>'
        hint = f'<div class="path-hint">{_esc(log.path_hint)}</div>' if log.path_hint else ""
        rows_html.append(
            "<tr>"
            f'<td data-value="{_esc(log.date)}">{_esc(log.date)}</td>'
            f'<td><a href="{_esc(log.slug)}.html">{_esc(log.title)}</a>{hint}</td>'
            f"<td>{_esc(log.label or '—')}</td>"
            f"<td>{link_cell}</td>"
            f"<td>{_esc(log.outcome_snippet)}</td>"
            f'<td class="mono path-hint">{_esc(log.rel_path)}</td>'
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Session Logs</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {_crumbs([("Leaderboard", "../index.html"), ("Session Logs", None)])}
  <h1>Session Logs</h1>
  <p class="muted">{len(ordered)} log(s). Default sort: date descending. Click headers to re-sort.</p>
  <table id="log-table">
    <thead><tr>
      <th data-col="0">Date</th>
      <th data-col="1">Title</th>
      <th data-col="2">Label</th>
      <th data-col="3">Link status</th>
      <th data-col="4">Outcome snippet</th>
      <th data-col="5">Path</th>
    </tr></thead>
    <tbody>
      {"".join(rows_html) if rows_html else '<tr><td colspan="6">No session logs found</td></tr>'}
    </tbody>
  </table>
  {_sort_script("log-table")}
</body>
</html>
"""


def render_conversation_detail(
    conv: ConversationRecord,
    *,
    caps: dict[str, int | None],
) -> str:
    badges = []
    if conv.has_full_transcript:
        badges.append('<span class="badge badge-artifact">Full transcript</span>')
    elif conv.has_compact_only:
        badges.append('<span class="badge badge-artifact">Compact only</span>')
    for name in SIDECAR_NAMES:
        if name in conv.sidecars:
            badges.append(
                f'<span class="badge badge-artifact">{_esc(name.replace(".md", ""))}</span>'
            )

    # Outcome band
    if conv.linked_logs:
        outcome_bits = []
        for log in conv.linked_logs:
            excerpt = log.outcome_body or ""
            if len(excerpt) > 800:
                excerpt = excerpt[:799] + "…"
            if excerpt:
                body = f"<pre>{_esc(excerpt)}</pre>"
            else:
                body = '<p class="muted">(no Results/Outcomes section)</p>'
            outcome_bits.append(
                f"<div><strong><a href=\"../session-logs/{_esc(log.slug)}.html\">"
                f"{_esc(log.title)}</a></strong>{body}</div>"
            )
        outcome_html = (
            f'<div class="outcome-band"><h2>Outcome</h2>{"".join(outcome_bits)}</div>'
        )
    else:
        outcome_html = (
            '<div class="outcome-band empty"><h2>Outcome</h2>'
            "<p>No linked Session Log — Outcome unavailable</p></div>"
        )

    # Linked logs table
    if conv.linked_logs:
        log_rows = "".join(
            "<tr>"
            f'<td><a href="../session-logs/{_esc(L.slug)}.html">{_esc(L.title)}</a></td>'
            f"<td>{_esc(L.date)}</td>"
            f'<td class="mono">{_esc(L.rel_path)}</td>'
            "</tr>"
            for L in conv.linked_logs
        )
        linked_html = f"""
  <h2>Linked Session Logs</h2>
  <table><thead><tr><th>Title</th><th>Date</th><th>Path</th></tr></thead>
  <tbody>{log_rows}</tbody></table>
"""
    else:
        linked_html = (
            "<h2>Linked Session Logs</h2>"
            '<p class="muted">No linked Session Logs (unlinked conversation).</p>'
        )

    # User requests
    if conv.user_requests:
        ureq = "".join(f"<pre>{_esc(u)}</pre>" for u in conv.user_requests)
        user_html = f"<h2>User request(s)</h2>{ureq}"
    else:
        user_html = '<h2>User request(s)</h2><p class="muted">None found in transcript.</p>'

    # Transcript head + dual render
    summary_cards: list[str] = []
    raw_blocks: list[str] = []
    banner_html = ""
    badge_trunc = ""
    sentinel_html = ""
    head = None
    if conv.transcript_path and conv.transcript_path.is_file():
        lines = load_transcript_lines(conv.transcript_path)
        head = select_transcript_head(
            lines,
            max_steps=caps.get("max_steps"),
            max_transcript_bytes=caps.get("max_transcript_bytes"),
        )
        for step in head.steps:
            obj = _parse_step(step.embedded_line)
            card = summarize_step_card(obj, partial=step.partial)
            if card:
                summary_cards.append(card)
            raw_blocks.append(
                f'<div class="step-card"><div class="step-kind mono">'
                f"#{step.index} partial={step.partial}</div>"
                f"<pre>{_esc(step.embedded_line.rstrip())}</pre></div>"
            )
        sent = trail_end_sentinel(head)
        if sent:
            sentinel_html = f'<p class="muted"><em>{_esc(sent)}</em></p>'
    else:
        summary_cards = []
        raw_blocks = []

    # Sidecars
    sidecar_parts: list[str] = []
    sidecar_truncated = False
    for name in SIDECAR_NAMES:
        path = conv.sidecars.get(name)
        if not path:
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = truncate_sidecar(raw, caps.get("max_sidecar_bytes"))
        if body.truncated:
            sidecar_truncated = True
        note = sidecar_truncation_note(body)
        note_html = f'<p class="muted"><em>{_esc(note)}</em></p>' if note else ""
        sidecar_parts.append(
            f"<details><summary>{_esc(name)}</summary>"
            f"{simple_markdown_to_html(body.text)}{note_html}</details>"
        )

    if head is not None:
        banner_html = format_truncation_banner_html(
            head,
            sidecar_truncated=sidecar_truncated,
            summary_card_count=len(summary_cards),
        )
        badge_trunc = truncated_badge_html(head.truncated or sidecar_truncated)

    trail_html = (
        f"<h2>What the agent did</h2>"
        f"{''.join(summary_cards) if summary_cards else '<p class=\"muted\">No steps to show.</p>'}"
        f"{sentinel_html}"
        f"<details><summary>Full transcript (raw steps)</summary>"
        f"{''.join(raw_blocks) if raw_blocks else '<p class=\"muted\">No transcript.</p>'}"
        f"{sentinel_html}</details>"
    )
    if not conv.transcript_path:
        trail_html = (
            "<h2>What the agent did</h2>"
            '<p class="muted">No transcript on disk for this conversation.</p>'
        )

    sidecar_html = ""
    if sidecar_parts:
        sidecar_html = "<h2>Brain sidecars</h2>" + "".join(sidecar_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Conversation {_esc(short_id(conv.conversation_id))}</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {_crumbs([
      ("Leaderboard", "../index.html"),
      ("Antigravity Conversations", "index.html"),
      (short_id(conv.conversation_id), None),
  ])}
  <h1>Antigravity Conversation {badge_trunc}</h1>
  <p class="mono">{_esc(conv.conversation_id)}</p>
  <p>{_esc(conv.date_display)} {" ".join(badges)}</p>
  {banner_html}
  {outcome_html}
  {linked_html}
  {user_html}
  {trail_html}
  {sidecar_html}
</body>
</html>
"""


def render_session_log_detail(log: SessionLogRecord) -> str:
    if log.linked_conversation_id:
        link_status = (
            f'<span class="badge badge-linked">Linked</span> '
            f'<a class="mono" href="../sessions/{_esc(log.linked_conversation_id)}.html">'
            f"{_esc(log.linked_conversation_id)}</a>"
        )
        cross = (
            f'<p><a href="../sessions/{_esc(log.linked_conversation_id)}.html">'
            f"Open Antigravity Conversation</a></p>"
        )
    else:
        link_status = '<span class="badge badge-unlinked">Unlinked</span>'
        cross = '<p class="muted">No linked conversation</p>'

    if log.outcome_title and log.outcome_body is not None:
        outcome_html = (
            f'<div class="outcome-band"><h2>Outcome — {_esc(log.outcome_title)}</h2>'
            f"{simple_markdown_to_html(log.outcome_body)}</div>"
        )
        body_md = omit_markdown_section(log.text, log.outcome_title)
    else:
        outcome_html = (
            '<div class="outcome-band empty"><h2>Outcome</h2>'
            '<p class="muted">No Results/Outcomes section found.</p></div>'
        )
        body_md = log.text

    body_html = simple_markdown_to_html(body_md)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{_esc(log.title)}</title>
  <style>{_SHARED_CSS}</style>
</head>
<body>
  {_crumbs([
      ("Leaderboard", "../index.html"),
      ("Session Logs", "index.html"),
      (log.title, None),
  ])}
  <h1>{_esc(log.title)}</h1>
  <p>{_esc(log.date)} · Label: {_esc(log.label or "—")} · {link_status}</p>
  <p class="path-hint mono">{_esc(log.rel_path)}</p>
  {outcome_html}
  <h2>Full log</h2>
  <div class="log-body">{body_html}</div>
  <h2>Cross-link</h2>
  {cross}
  <details><summary>Raw Markdown source</summary>
  <pre>{_esc(log.text)}</pre></details>
</body>
</html>
"""


class SessionReviewGenerator:
    """Scan brain + session-logs roots and write static Session Review HTML."""

    def generate(
        self,
        *,
        antigravity_brain: Path,
        antigravity_ide_brain: Path | None = None,
        session_logs: Path,
        sessions_out: Path,
        session_logs_out: Path,
        caps: dict[str, int | None] | None = None,
    ) -> dict[str, Any]:
        roots = [Path(antigravity_brain)]
        if antigravity_ide_brain is not None:
            roots.append(Path(antigravity_ide_brain))
        conversations = scan_conversations(roots)
        logs = scan_session_logs(Path(session_logs))
        link_records(conversations, logs)

        effective_caps = caps if caps is not None else resolve_session_review_caps(None)

        sessions_out = Path(sessions_out)
        session_logs_out = Path(session_logs_out)
        sessions_out.mkdir(parents=True, exist_ok=True)
        session_logs_out.mkdir(parents=True, exist_ok=True)
        # Full regenerate: drop prior HTML so removed sources do not leave orphans.
        for out_dir in (sessions_out, session_logs_out):
            for stale in out_dir.glob("*.html"):
                try:
                    stale.unlink()
                except OSError:
                    pass

        (sessions_out / "index.html").write_text(
            render_conversations_index(conversations), encoding="utf-8"
        )
        (session_logs_out / "index.html").write_text(
            render_session_logs_index(logs), encoding="utf-8"
        )

        for conv in conversations:
            page = render_conversation_detail(conv, caps=effective_caps)
            (sessions_out / f"{conv.conversation_id}.html").write_text(
                page, encoding="utf-8"
            )

        for log in logs:
            page = render_session_log_detail(log)
            (session_logs_out / f"{log.slug}.html").write_text(page, encoding="utf-8")

        linked_logs = sum(1 for L in logs if L.linked_conversation_id)
        return {
            "conversations": len(conversations),
            "session_logs": len(logs),
            "linked_logs": linked_logs,
            "unlinked_logs": len(logs) - linked_logs,
            "sessions_out": str(sessions_out),
            "session_logs_out": str(session_logs_out),
            "generated_at": _utc_now_iso(),
        }


def generate_session_review(
    *,
    repo_root: Path | None = None,
    config: dict[str, Any] | None = None,
    antigravity_brain: Path | None = None,
    antigravity_ide_brain: Path | None = None,
    session_logs: Path | None = None,
    caps_overrides: dict[str, int | None] | None = None,
    caps_off: bool = False,
) -> dict[str, Any]:
    """Load config, resolve paths/caps, run SessionReviewGenerator."""
    from bench_suite.config import load_config

    root = Path(repo_root or Path.cwd()).resolve()
    cfg = config if config is not None else load_config(repo_root=root)
    resolved = cfg.get("_resolved_session_review") or {}
    brain = Path(antigravity_brain or resolved.get("antigravity_brain") or "")
    ide = Path(
        antigravity_ide_brain
        if antigravity_ide_brain is not None
        else resolved.get("antigravity_ide_brain") or ""
    )
    logs = Path(session_logs or resolved.get("session_logs") or "")
    sessions_out = Path(
        resolved.get("sessions_root")
        or (root / ".scratch/bench-suite/sessions")
    )
    logs_out = Path(
        resolved.get("session_logs_root")
        or (root / ".scratch/bench-suite/session-logs")
    )
    caps = resolve_session_review_caps(
        cfg, overrides=caps_overrides, caps_off=caps_off
    )
    return SessionReviewGenerator().generate(
        antigravity_brain=brain,
        antigravity_ide_brain=ide if str(ide) else None,
        session_logs=logs,
        sessions_out=sessions_out,
        session_logs_out=logs_out,
        caps=caps,
    )
