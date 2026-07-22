"""Session Review soft size caps and truncation markers (#16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bench_suite.config import (
    DEFAULT_SESSION_REVIEW_CAPS,
    load_config,
    parse_cap_overrides,
    resolve_session_review_caps,
)
from bench_suite.session_caps import (
    format_truncation_banner,
    format_truncation_banner_html,
    load_transcript_lines,
    select_transcript_head,
    sidecar_truncation_note,
    trail_end_sentinel,
    truncate_sidecar,
    truncated_badge_html,
    utf8_prefix,
)


def _lines(*bodies: str) -> list[str]:
    """Build jsonl-like lines with trailing newlines (on-disk style)."""
    return [b if b.endswith("\n") else b + "\n" for b in bodies]


def test_defaults_match_grilling_resolution() -> None:
    assert DEFAULT_SESSION_REVIEW_CAPS == {
        "max_steps": 200,
        "max_transcript_bytes": 524_288,
        "max_sidecar_bytes": 65_536,
    }
    caps = resolve_session_review_caps(None)
    assert caps == DEFAULT_SESSION_REVIEW_CAPS


def test_resolve_caps_off_and_overrides() -> None:
    off = resolve_session_review_caps(None, caps_off=True)
    assert off == {
        "max_steps": None,
        "max_transcript_bytes": None,
        "max_sidecar_bytes": None,
    }
    custom = resolve_session_review_caps(
        {"session_review": {"caps": {"max_steps": 10}}},
        overrides={"max_transcript_bytes": 100},
    )
    assert custom["max_steps"] == 10
    assert custom["max_transcript_bytes"] == 100
    assert custom["max_sidecar_bytes"] == 65_536

    with pytest.raises(ValueError, match="Unknown session review cap"):
        resolve_session_review_caps(None, overrides={"max_files": 1})


def test_load_config_includes_session_review(tmp_suite: Path) -> None:
    cfg = load_config(repo_root=tmp_suite)
    sr = cfg["session_review"]
    assert sr["caps"]["max_steps"] == 200
    assert "antigravity_brain" in cfg["_resolved_session_review"]
    assert "sessions_root" in cfg["_resolved_session_review"]
    # Output roots resolve under the tmp suite
    assert str(tmp_suite) in cfg["_resolved_session_review"]["sessions_root"]


def test_parse_cap_overrides() -> None:
    assert parse_cap_overrides(["max_steps=50", "max_transcript_bytes=1024"]) == {
        "max_steps": 50,
        "max_transcript_bytes": 1024,
    }
    with pytest.raises(ValueError):
        parse_cap_overrides(["nope"])


def test_under_cap_full_render() -> None:
    lines = _lines('{"type":"USER_INPUT"}', '{"type":"PLANNER_RESPONSE"}')
    head = select_transcript_head(lines, max_steps=200, max_transcript_bytes=524_288)
    assert head.truncated is False
    assert head.head_steps == 2
    assert head.embedded_bytes == head.total_bytes
    assert trail_end_sentinel(head) is None
    assert format_truncation_banner(head) is None
    assert truncated_badge_html(False) == ""


def test_max_steps_shared_head() -> None:
    lines = _lines(*[f'{{"i":{i}}}' for i in range(5)])
    head = select_transcript_head(lines, max_steps=3, max_transcript_bytes=None)
    assert head.truncated is True
    assert head.head_steps == 3
    assert head.total_steps == 5
    assert "max_steps" in head.reasons
    assert [s.index for s in head.steps] == [0, 1, 2]
    assert all(not s.partial for s in head.steps)
    sentinel = trail_end_sentinel(head)
    assert sentinel is not None
    assert "max_steps" in sentinel
    assert "Source transcript on disk is complete" in sentinel
    banner = format_truncation_banner(head)
    assert banner is not None
    assert "Showing 3 of 5 source steps" in banner
    assert truncated_badge_html(True) == '<span class="badge badge-truncated">truncated</span>'


def test_max_transcript_bytes_partial_last_step() -> None:
    # Two small lines then one large — byte budget cuts mid third line.
    small = "aa\n"  # 3 bytes
    big = "b" * 50 + "\n"  # 51 bytes
    lines = [small, small, big]
    # Budget: 3 + 3 + 10 = 16 → third step partial at 10 bytes
    head = select_transcript_head(lines, max_steps=None, max_transcript_bytes=16)
    assert head.truncated is True
    assert "max_transcript_bytes" in head.reasons
    assert head.head_steps == 3
    assert head.steps[0].partial is False
    assert head.steps[1].partial is False
    assert head.steps[2].partial is True
    assert head.steps[2].embedded_bytes == 10
    assert head.steps[2].embedded_line == "b" * 10
    assert head.embedded_bytes == 16
    assert head.last_step_partial is True
    banner = format_truncation_banner(head)
    assert banner is not None
    assert "partial" in banner.lower()


def test_byte_cap_stops_before_empty_partial() -> None:
    lines = _lines("xxxx", "yyyy")
    # Exactly first line; remaining 0 → second step not included
    first_len = len(lines[0].encode("utf-8"))
    head = select_transcript_head(
        lines, max_steps=None, max_transcript_bytes=first_len
    )
    assert head.head_steps == 1
    assert head.truncated is True
    assert head.steps[0].partial is False


def test_both_axes_first_limit_wins_steps() -> None:
    lines = _lines(*[f'{{"i":{i}}}' for i in range(10)])
    head = select_transcript_head(lines, max_steps=2, max_transcript_bytes=10_000)
    assert head.head_steps == 2
    assert "max_steps" in head.reasons


def test_both_axes_first_limit_wins_bytes() -> None:
    lines = _lines(*["x" * 20 for _ in range(10)])
    head = select_transcript_head(lines, max_steps=50, max_transcript_bytes=25)
    assert head.truncated is True
    assert "max_transcript_bytes" in head.reasons
    assert head.head_steps <= 2


def test_caps_off_includes_all() -> None:
    lines = _lines(*[f'{{"i":{i}}}' for i in range(300)])
    head = select_transcript_head(lines, max_steps=None, max_transcript_bytes=None)
    assert head.truncated is False
    assert head.head_steps == 300


def test_empty_transcript_no_marker() -> None:
    head = select_transcript_head([], max_steps=200, max_transcript_bytes=100)
    assert head.total_steps == 0
    assert head.truncated is False
    assert format_truncation_banner(head) is None


def test_utf8_prefix_does_not_split_multibyte() -> None:
    text = "ab😀cd"  # grinning face is 4 bytes
    # "ab" = 2 bytes; next would split emoji if naïvely sliced at 3
    assert utf8_prefix(text, 3) == "ab"
    assert utf8_prefix(text, 6) == "ab😀"


def test_truncate_sidecar() -> None:
    body = truncate_sidecar("hello world", max_sidecar_bytes=5)
    assert body.truncated is True
    assert body.text == "hello"
    assert body.reason == "max_sidecar_bytes"
    assert sidecar_truncation_note(body) is not None

    full = truncate_sidecar("short", max_sidecar_bytes=65_536)
    assert full.truncated is False
    assert sidecar_truncation_note(full) is None

    uncapped = truncate_sidecar("x" * 1000, max_sidecar_bytes=None)
    assert uncapped.truncated is False
    assert len(uncapped.text) == 1000


def test_session_logs_not_capped_by_this_module() -> None:
    """Session Log bodies are out of scope for soft caps — no API truncates them."""
    # Documented by absence: only truncate_sidecar + select_transcript_head exist.
    import bench_suite.session_caps as m

    assert not hasattr(m, "truncate_session_log")


def test_banner_html_escapes_and_badge() -> None:
    lines = _lines(*[f'{{"i":{i}}}' for i in range(5)])
    head = select_transcript_head(lines, max_steps=2, max_transcript_bytes=None)
    html_out = format_truncation_banner_html(head, summary_card_count=1)
    assert "truncation-banner" in html_out
    assert "Showing 2 of 5" in html_out
    assert "Summary cards: 1" in html_out
    assert format_truncation_banner_html(
        select_transcript_head(lines, max_steps=None, max_transcript_bytes=None)
    ) == ""


def test_load_transcript_lines_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "transcript_full.jsonl"
    p.write_text('{"type":"A"}\n{"type":"B"}\n', encoding="utf-8")
    lines = load_transcript_lines(p)
    head = select_transcript_head(lines, max_steps=200, max_transcript_bytes=524_288)
    assert head.head_steps == 2
    assert head.truncated is False
