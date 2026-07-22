"""Session Review generator: matching, scan, static HTML, soft caps, CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path

from bench_suite.config import load_config, resolve_session_review_caps
from bench_suite.session_review import (
    SessionReviewGenerator,
    extract_conversation_link,
    extract_markdown_section,
    generate_session_review,
    log_slug,
    omit_markdown_section,
    scan_conversations,
    scan_session_logs,
)


def _write_transcript(path: Path, steps: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(s) + "\n" for s in steps),
        encoding="utf-8",
    )


def _fixture_tree(tmp: Path) -> dict[str, Path]:
    brain = tmp / "brain"
    ide = tmp / "ide-brain"
    logs = tmp / "session-logs"
    brain.mkdir()
    ide.mkdir()
    logs.mkdir()

    cid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    conv = brain / cid
    conv.mkdir()
    (conv / "walkthrough.md").write_text("# Walk\nDid the thing.\n", encoding="utf-8")
    _write_transcript(
        conv / ".system_generated" / "logs" / "transcript_full.jsonl",
        [
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "created_at": "2026-07-01T10:00:00Z",
                "content": "<USER_REQUEST>\nShip session review\n</USER_REQUEST>",
            },
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-07-01T10:01:00Z",
                "content": "I will implement the generator.",
            },
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "VIEW_FILE",
                "created_at": "2026-07-01T10:02:00Z",
                "content": "path: foo.py",
            },
            {
                "step_index": 3,
                "source": "SYSTEM",
                "type": "CHECKPOINT",
                "created_at": "2026-07-01T10:03:00Z",
                "content": "noise",
            },
        ],
    )

    # Log with Conversation ID
    (logs / "linked.md").write_text(
        f"# Session Log: Linked Work\n\n"
        f"**Date:** 2026-07-01\n"
        f"**Label:** Feature\n"
        f"**Conversation ID**: {cid}\n\n"
        f"## Actions\n- Built generator\n\n"
        f"## Results / Outcomes\n- HTML pages written\n",
        encoding="utf-8",
    )
    # Orphan log
    (logs / "orphan.md").write_text(
        "# Session Log: Orphan Note\n\n**Date:** 2026-06-01\n\n## Notes\nNo link.\n",
        encoding="utf-8",
    )
    # Brain-path linked log
    cid2 = "11111111-2222-3333-4444-555555555555"
    conv2 = brain / cid2
    conv2.mkdir()
    _write_transcript(
        conv2 / ".system_generated" / "logs" / "transcript_full.jsonl",
        [
            {
                "type": "USER_INPUT",
                "source": "USER_EXPLICIT",
                "created_at": "2026-06-15T12:00:00Z",
                "content": "Second conversation",
            }
        ],
    )
    (logs / "subdir").mkdir()
    (logs / "subdir" / "brainpath.md").write_text(
        "# Session Log: Via Path\n\n**Date:** 2026-06-15\n\n"
        f"Opened `file:///Users/x/.gemini/antigravity/brain/{cid2}/task.md`\n\n"
        "## Results Observed\nPath join worked.\n",
        encoding="utf-8",
    )
    # Session ID metadata link
    cid3 = "99999999-8888-7777-6666-555555555555"
    (brain / cid3).mkdir()
    (logs / "session_id_meta.md").write_text(
        f"# Session Log: Meta SID\n\n**Date:** 2026-05-01\n"
        f"**Session ID:** {cid3}\n\n## Result\nDone.\n",
        encoding="utf-8",
    )
    # Prose Session ID should NOT match
    (logs / "jesse_prose.md").write_text(
        "# Session Log: Jesse\n\n**Date:** 2026-05-02\n\n"
        "6. Verified successful database registration (Session ID: "
        "`14071903-6be3-4e33-b257-c2a68552ca73`) and metrics.\n",
        encoding="utf-8",
    )

    out_sessions = tmp / "out" / "sessions"
    out_logs = tmp / "out" / "session-logs"
    return {
        "brain": brain,
        "ide": ide,
        "logs": logs,
        "out_sessions": out_sessions,
        "out_logs": out_logs,
        "cid": Path(cid),  # type misuse — store as str below
        "cid_str": cid,
        "cid2": cid2,
        "cid3": cid3,
    }


def test_extract_conversation_link_priority() -> None:
    cid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    text = (
        f"**Conversation ID**: {cid}\n"
        f"Also brain path antigravity/brain/11111111-2222-3333-4444-555555555555/\n"
    )
    assert extract_conversation_link(text) == (cid, "conversation_id")

    text2 = f"**Session ID:** {cid}\n"
    assert extract_conversation_link(text2) == (cid, "session_id")

    text3 = f"file:///Users/x/.gemini/antigravity-ide/brain/{cid}/x.md\n"
    assert extract_conversation_link(text3) == (cid, "brain_path")

    prose = (
        "Verified registration (Session ID: "
        "`14071903-6be3-4e33-b257-c2a68552ca73`) and metrics.\n"
    )
    assert extract_conversation_link(prose) is None


def test_log_slug_and_outcome_section() -> None:
    assert log_slug("subdir/foo bar.md") == "subdir-foo-bar"
    md = "# T\n\n## Actions\nx\n\n## Results / Outcomes\n- ok\n\n## Next\ny\n"
    sec = extract_markdown_section(md, ("Results / Outcomes", "Results"))
    assert sec is not None
    assert sec[0] == "Results / Outcomes"
    assert "ok" in sec[1]
    body = omit_markdown_section(md, "Results / Outcomes")
    assert "Results / Outcomes" not in body
    assert "## Actions" in body
    assert "## Next" in body


def test_scan_and_link(tmp_path: Path) -> None:
    fx = _fixture_tree(tmp_path)
    convs = scan_conversations([fx["brain"], fx["ide"]])
    logs = scan_session_logs(fx["logs"])
    assert len(convs) >= 3
    assert any(L.linked_conversation_id == fx["cid_str"] for L in logs)
    # prose session id not linked
    jesse = next(L for L in logs if L.rel_path == "jesse_prose.md")
    assert jesse.linked_conversation_id is None


def test_generate_writes_lists_and_details(tmp_path: Path) -> None:
    fx = _fixture_tree(tmp_path)
    result = SessionReviewGenerator().generate(
        antigravity_brain=fx["brain"],
        antigravity_ide_brain=fx["ide"],
        session_logs=fx["logs"],
        sessions_out=fx["out_sessions"],
        session_logs_out=fx["out_logs"],
        caps=resolve_session_review_caps(None),
    )
    assert result["conversations"] >= 3
    assert result["session_logs"] >= 4
    assert result["linked_logs"] >= 2

    sessions_index = (fx["out_sessions"] / "index.html").read_text(encoding="utf-8")
    assert "Antigravity Conversations" in sessions_index
    assert "Ship session review" in sessions_index
    assert fx["cid_str"][:8] in sessions_index

    logs_index = (fx["out_logs"] / "index.html").read_text(encoding="utf-8")
    assert "Session Logs" in logs_index
    assert "Linked Work" in logs_index
    assert "Unlinked" in logs_index

    detail = (fx["out_sessions"] / f"{fx['cid_str']}.html").read_text(encoding="utf-8")
    assert "No linked Session Log" not in detail
    assert "HTML pages written" in detail
    assert "What the agent did" in detail
    assert "Ship session review" in detail
    assert "Full transcript (raw steps)" in detail
    assert "CHECKPOINT" not in detail or "noise"  # summary omits; raw may include
    # SYSTEM noise omitted from summary cards but present in raw section
    assert "CHECKPOINT" in detail  # raw trail includes full head
    assert "walkthrough" in detail.lower()

    linked_pages = list(fx["out_logs"].glob("*.html"))
    assert linked_pages
    log_detail = next(
        p.read_text(encoding="utf-8")
        for p in linked_pages
        if p.name != "index.html" and "Linked Work" in p.read_text(encoding="utf-8")
    )
    assert "Outcome" in log_detail
    assert "Open Antigravity Conversation" in log_detail
    assert "HTML pages written" in log_detail

    orphan = next(
        p.read_text(encoding="utf-8")
        for p in linked_pages
        if p.name != "index.html" and "Orphan Note" in p.read_text(encoding="utf-8")
    )
    assert "No linked conversation" in orphan


def test_soft_caps_banner_on_conversation(tmp_path: Path) -> None:
    fx = _fixture_tree(tmp_path)
    # Many steps to trigger max_steps
    cid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    conv = fx["brain"] / cid
    conv.mkdir()
    steps = [
        {
            "type": "USER_INPUT",
            "source": "USER_EXPLICIT",
            "created_at": "2026-07-10T00:00:00Z",
            "content": f"step {i}",
        }
        for i in range(30)
    ]
    _write_transcript(
        conv / ".system_generated" / "logs" / "transcript_full.jsonl", steps
    )
    SessionReviewGenerator().generate(
        antigravity_brain=fx["brain"],
        session_logs=fx["logs"],
        sessions_out=fx["out_sessions"],
        session_logs_out=fx["out_logs"],
        caps={"max_steps": 5, "max_transcript_bytes": 524_288, "max_sidecar_bytes": 65_536},
    )
    page = (fx["out_sessions"] / f"{cid}.html").read_text(encoding="utf-8")
    assert "truncation-banner" in page
    assert "Showing 5 of 30" in page
    assert "truncated by soft size caps" in page
    assert "badge-truncated" in page


def test_missing_roots_are_noop(tmp_path: Path) -> None:
    out_s = tmp_path / "s"
    out_l = tmp_path / "l"
    result = SessionReviewGenerator().generate(
        antigravity_brain=tmp_path / "nope",
        session_logs=tmp_path / "nope2",
        sessions_out=out_s,
        session_logs_out=out_l,
    )
    assert result["conversations"] == 0
    assert result["session_logs"] == 0
    assert (out_s / "index.html").is_file()
    assert (out_l / "index.html").is_file()


def test_generate_session_review_uses_config(tmp_path: Path, tmp_suite: Path) -> None:
    fx = _fixture_tree(tmp_path)
    # Point suite config at fixture roots via env-less override by writing config
    cfg_path = tmp_suite / ".scratch" / "bench-suite" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
    cfg["session_review"] = {
        "antigravity_brain": str(fx["brain"]),
        "antigravity_ide_brain": str(fx["ide"]),
        "session_logs": str(fx["logs"]),
        "output": {
            "sessions_root": str(tmp_suite / ".scratch/bench-suite/sessions"),
            "session_logs_root": str(tmp_suite / ".scratch/bench-suite/session-logs"),
        },
        "caps": {"max_steps": 200},
    }
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    result = generate_session_review(repo_root=tmp_suite)
    assert result["conversations"] >= 3
    assert Path(result["sessions_out"]).joinpath("index.html").is_file()


def test_cli_generate_session_review(tmp_path: Path, tmp_suite: Path) -> None:
    from bench_suite.cli import main

    fx = _fixture_tree(tmp_path)
    code = main(
        [
            "generate-session-review",
            "--repo-root",
            str(tmp_suite),
            "--brain",
            str(fx["brain"]),
            "--ide-brain",
            str(fx["ide"]),
            "--session-logs",
            str(fx["logs"]),
            "--session-cap",
            "max_steps=50",
        ]
    )
    assert code == 0
    # Default output under suite
    assert (tmp_suite / ".scratch/bench-suite/sessions/index.html").is_file()
