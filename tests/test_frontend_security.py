from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_avoids_dangerous_dom_and_code_execution_sinks() -> None:
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    forbidden = [
        ".innerHTML",
        ".outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
        "localStorage",
        "sessionStorage",
    ]
    for token in forbidden:
        assert token not in script
    assert ".textContent" in script


def test_frontend_has_no_remote_assets_or_inline_script() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "https://" not in html
    assert "http://" not in html
    assert "<script>" not in html
    assert "onclick=" not in html


def test_accessibility_and_reduced_motion_baseline() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    assert 'aria-live="polite"' in html
    assert "skip-link" in html
    assert "focus-visible" in css
    assert "prefers-reduced-motion" in css


def test_frontend_labels_dangerous_candidates_and_skips_empty_handoff() -> None:
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "危险候选" in script
    assert "没有候选 SQL，不向网关发送载荷" in script


def test_runtime_dependencies_do_not_include_database_driver() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for driver in ("psycopg", "sqlalchemy", "asyncpg", "pymysql"):
        assert driver not in pyproject

