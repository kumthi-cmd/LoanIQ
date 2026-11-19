"""Tests for serving the built SPA (main.serve_spa) and the OpenAPI export.

BUSINESS: one server gives a visitor the whole of LoanIQ: the screens at "/", any
  screen's URL on reload, and the API under /api. The front end's API types must
  match what the API really sends, or a KPI tile could silently read a field that
  no longer exists.
TECH: a fake build (index.html plus one asset) in a temp folder stands in for
  frontend/dist, so these tests do not need `npm run build`. The tape fixture is a
  small generated one, as in test_api.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app import export_openapi, main

INDEX_HTML = "<!doctype html><title>LoanIQ</title><div id=root></div>"


@pytest.fixture(scope="module")
def spa_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fake Vite build: index.html and assets/app.js."""
    root = tmp_path_factory.mktemp("dist")
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("console.log('loaniq')", encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory, spa_dir: Path) -> Iterator[TestClient]:
    """The API with the fake build. TECH: generates the default tape into a temp folder."""
    with TestClient(main.create_app(tmp_path_factory.mktemp("tape"), spa_dir)) as c:
        yield c


def test_root_serves_index(client: TestClient) -> None:
    """BUSINESS: opening LoanIQ shows the app."""
    r = client.get("/")
    assert r.status_code == 200
    assert "LoanIQ" in r.text


def test_asset_served_as_file(client: TestClient) -> None:
    """TECH: the built JavaScript is served as itself, not replaced by index.html."""
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "loaniq" in r.text


def test_screen_url_falls_back_to_index(client: TestClient) -> None:
    """BUSINESS: reloading a screen's URL (a later /slotting) still opens LoanIQ."""
    r = client.get("/slotting/some/deep/link")
    assert r.status_code == 200
    assert "LoanIQ" in r.text


def test_api_routes_still_win(client: TestClient) -> None:
    """BUSINESS: the catch-all never hides the loan API."""
    assert client.get("/api/health").json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/api", "/api/nope", "/api/loans/nope/deeper"])
def test_unknown_api_route_is_404(client: TestClient, path: str) -> None:
    """TECH: a typo in an API URL is a JSON 404, not the SPA's HTML."""
    r = client.get(path)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_path_traversal_cannot_leave_build(spa_dir: Path) -> None:
    """TECH: "../" can never reach files outside the build folder."""
    secret = spa_dir.parent / "secret.txt"
    secret.write_text("do not serve", encoding="utf-8")
    assert main.spa_file(spa_dir, "../secret.txt") == spa_dir / "index.html"
    assert main.spa_file(spa_dir, "..\\secret.txt") == spa_dir / "index.html"


def test_no_build_gives_helpful_404(tmp_path: Path) -> None:
    """TECH: before `npm run build`, "/" explains what to do instead of crashing."""
    with TestClient(main.create_app(tmp_path / "tape", tmp_path / "missing")) as c:
        r = c.get("/")
    assert r.status_code == 404
    assert "npm run build" in r.json()["detail"]


def test_catch_all_not_in_openapi() -> None:
    """TECH: the SPA route stays off /docs and out of the front end's generated types."""
    assert "/{path}" not in main.app.openapi()["paths"]


def test_committed_openapi_matches_code() -> None:
    """BUSINESS: the screen's API types describe what the API really sends.

    TECH: if this fails, run `.venv\\Scripts\\python.exe -m app.export_openapi`
      from backend/ and then `npm run gen:api` in frontend/.
    """
    committed = export_openapi.OPENAPI_PATH.read_text(encoding="utf-8")
    assert committed == export_openapi.openapi_text()


def test_export_writes_valid_json(tmp_path: Path) -> None:
    """TECH: the export command writes parseable JSON with the loan routes."""
    out = export_openapi.main(["--out", str(tmp_path / "spec.json")])
    paths = json.loads(out.read_text(encoding="utf-8"))["paths"]
    assert {"/api/loans", "/api/loans/columns", "/api/loans/summary"} <= set(paths)
