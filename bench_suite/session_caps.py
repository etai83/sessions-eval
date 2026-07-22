"""Soft size caps and truncation markers for Session Review static HTML (#16).

Generate-time only: source transcripts and Session Logs on disk are never modified.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any, Sequence


TRAIL_END_SENTINEL = (
    "… truncated by soft size caps ({reasons}). "
    "Source transcript on disk is complete."
)

SIDECAR_NOTE = (
    "Sidecar truncated by soft size cap; full file remains on disk under the brain root."
)


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def utf8_prefix(text: str, max_bytes: int) -> str:
    """UTF-8-safe prefix of at most ``max_bytes`` content bytes.

    Incomplete trailing multi-byte sequences are dropped; complete characters
    that fit entirely within the budget are kept.
    """
    if max_bytes <= 0:
        return ""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="ignore")


@dataclass(frozen=True)
class IncludedStep:
    """One transcript record admitted into the shared head."""

    index: int
    raw_line: str
    embedded_line: str
    source_bytes: int
    embedded_bytes: int
    partial: bool


@dataclass
class TranscriptHead:
    """Shared chronological head for summarized trail and raw ``<details>``."""

    steps: list[IncludedStep] = field(default_factory=list)
    total_steps: int = 0
    total_bytes: int = 0
    embedded_bytes: int = 0
    truncated: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def head_steps(self) -> int:
        return len(self.steps)

    @property
    def last_step_partial(self) -> bool:
        return bool(self.steps and self.steps[-1].partial)

    def to_dict(self) -> dict[str, Any]:
        return {
            "truncated": self.truncated,
            "reasons": list(self.reasons),
            "head_steps": self.head_steps,
            "total_steps": self.total_steps,
            "embedded_bytes": self.embedded_bytes,
            "total_bytes": self.total_bytes,
            "last_step_partial": self.last_step_partial,
            "steps": [
                {
                    "index": s.index,
                    "source_bytes": s.source_bytes,
                    "embedded_bytes": s.embedded_bytes,
                    "partial": s.partial,
                    "embedded_line": s.embedded_line,
                    "raw_line": s.raw_line,
                }
                for s in self.steps
            ],
        }


@dataclass(frozen=True)
class SidecarBody:
    """Sidecar Markdown after optional soft byte cap."""

    text: str
    original_bytes: int
    stored_bytes: int
    truncated: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "truncated": self.truncated,
            "original_bytes": self.original_bytes,
            "stored_bytes": self.stored_bytes,
            "reason": self.reason,
            "text": self.text,
        }


def select_transcript_head(
    lines: Sequence[str],
    *,
    max_steps: int | None = 200,
    max_transcript_bytes: int | None = 524_288,
) -> TranscriptHead:
    """
    Walk jsonl records in order; build a shared head under soft size caps.

    A step is one source line (including SYSTEM noise). Both axes must pass;
    the first limit wins. Mid-step byte overflow keeps a partial last step.
    """
    # Preserve caller lines as-is for embedding; count raw UTF-8 bytes of each
    # line body as provided (including newline if present).
    total_steps = len(lines)
    total_bytes = sum(_utf8_len(line) for line in lines)
    head = TranscriptHead(total_steps=total_steps, total_bytes=total_bytes)

    if total_steps == 0:
        return head

    for index, line in enumerate(lines):
        if max_steps is not None and len(head.steps) >= max_steps:
            head.truncated = True
            if "max_steps" not in head.reasons:
                head.reasons.append("max_steps")
            break

        source_bytes = _utf8_len(line)
        if max_transcript_bytes is None:
            head.steps.append(
                IncludedStep(
                    index=index,
                    raw_line=line,
                    embedded_line=line,
                    source_bytes=source_bytes,
                    embedded_bytes=source_bytes,
                    partial=False,
                )
            )
            head.embedded_bytes += source_bytes
            continue

        remaining = max_transcript_bytes - head.embedded_bytes
        if remaining <= 0:
            head.truncated = True
            if "max_transcript_bytes" not in head.reasons:
                head.reasons.append("max_transcript_bytes")
            break

        if source_bytes <= remaining:
            head.steps.append(
                IncludedStep(
                    index=index,
                    raw_line=line,
                    embedded_line=line,
                    source_bytes=source_bytes,
                    embedded_bytes=source_bytes,
                    partial=False,
                )
            )
            head.embedded_bytes += source_bytes
            continue

        # Partial last step: UTF-8-safe prefix of remaining budget.
        partial_text = utf8_prefix(line, remaining)
        embedded_bytes = _utf8_len(partial_text)
        head.steps.append(
            IncludedStep(
                index=index,
                raw_line=line,
                embedded_line=partial_text,
                source_bytes=source_bytes,
                embedded_bytes=embedded_bytes,
                partial=True,
            )
        )
        head.embedded_bytes += embedded_bytes
        head.truncated = True
        if "max_transcript_bytes" not in head.reasons:
            head.reasons.append("max_transcript_bytes")
        break

    return head


def load_transcript_lines(path: Any) -> list[str]:
    """Read a transcript_full.jsonl file into lines (keeps line endings stripped of \\r)."""
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8")
    if not text:
        return []
    # splitlines(keepends=True) preserves content for byte accounting close to on-disk.
    lines = text.splitlines(keepends=True)
    return lines


def truncate_sidecar(
    text: str,
    max_sidecar_bytes: int | None,
) -> SidecarBody:
    """Cap a brain sidecar Markdown body by UTF-8 bytes."""
    original_bytes = _utf8_len(text)
    if max_sidecar_bytes is None or original_bytes <= max_sidecar_bytes:
        return SidecarBody(
            text=text,
            original_bytes=original_bytes,
            stored_bytes=original_bytes,
            truncated=False,
            reason=None,
        )
    stored = utf8_prefix(text, max_sidecar_bytes)
    return SidecarBody(
        text=stored,
        original_bytes=original_bytes,
        stored_bytes=_utf8_len(stored),
        truncated=True,
        reason="max_sidecar_bytes",
    )


def trail_end_sentinel(head: TranscriptHead) -> str | None:
    """Human trail-end truncation marker, or None when not truncated."""
    if not head.truncated:
        return None
    reasons = " / ".join(head.reasons) if head.reasons else "soft size caps"
    return TRAIL_END_SENTINEL.format(reasons=reasons)


def sidecar_truncation_note(body: SidecarBody) -> str | None:
    if not body.truncated:
        return None
    return SIDECAR_NOTE


def format_truncation_banner(
    head: TranscriptHead,
    *,
    sidecar_truncated: bool = False,
    summary_card_count: int | None = None,
) -> str | None:
    """
    Plain-text banner body for conversation detail when any soft cap fired.

    Returns None when nothing was truncated (including sidecars).
    """
    if not head.truncated and not sidecar_truncated:
        return None
    reasons: list[str] = list(head.reasons)
    if sidecar_truncated and "max_sidecar_bytes" not in reasons:
        reasons.append("max_sidecar_bytes")
    reason_txt = ", ".join(reasons) if reasons else "soft size caps"
    lines = [
        "Conversation content was truncated by soft size caps.",
        (
            f"Showing {head.head_steps} of {head.total_steps} source steps; "
            f"embedded {head.embedded_bytes} of {head.total_bytes} bytes."
        ),
        f"Caps hit: {reason_txt}.",
    ]
    if summary_card_count is not None:
        lines.append(f"Summary cards: {summary_card_count}.")
    if head.last_step_partial:
        lines.append("Last included step is partial (byte budget exhausted mid-step).")
    lines.append("Source transcript and sidecars on disk are complete.")
    return "\n".join(lines)


def format_truncation_banner_html(
    head: TranscriptHead,
    *,
    sidecar_truncated: bool = False,
    summary_card_count: int | None = None,
) -> str:
    """HTML callout for the banner, or empty string when not truncated."""
    text = format_truncation_banner(
        head,
        sidecar_truncated=sidecar_truncated,
        summary_card_count=summary_card_count,
    )
    if not text:
        return ""
    parts = text.split("\n")
    title = html.escape(parts[0])
    rest = "".join(f"<p>{html.escape(p)}</p>" for p in parts[1:])
    return (
        f'<div class="truncation-banner" role="status">'
        f"<strong>{title}</strong>{rest}</div>"
    )


def truncated_badge_html(truncated: bool) -> str:
    """Optional header badge matching Run Review visual language."""
    if not truncated:
        return ""
    return '<span class="badge badge-truncated">truncated</span>'
