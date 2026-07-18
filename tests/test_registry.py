"""Registry seam: model×config hash keys and task recording."""

from __future__ import annotations

from pathlib import Path

from bench_suite.registry import Registry, registry_key


def test_registry_key_is_stable() -> None:
    key = registry_key("gemini-3.5-flash", {"thinking_level": "high"})
    # sha256 of {"thinking_level":"high"} truncated to 8 hex chars
    assert key == "gemini-3.5-flash:6584ecca"
    # order independence
    assert registry_key("gemini-3.5-flash", {"b": 1, "a": 2}) == registry_key(
        "gemini-3.5-flash", {"a": 2, "b": 1}
    )


def test_record_and_has_run(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    reg = Registry(path)
    cfg = {"thinking_level": "high"}
    assert not reg.has_run("gemini-3.5-flash", cfg, "offline_golden_01")
    reg.record("gemini-3.5-flash", cfg, "offline_golden_01")
    assert reg.has_run("gemini-3.5-flash", cfg, "offline_golden_01")

    reloaded = Registry(path)
    assert reloaded.has_run("gemini-3.5-flash", cfg, "offline_golden_01")
