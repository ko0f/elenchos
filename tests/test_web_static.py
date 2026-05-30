from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from elenchos import __version__
from elenchos.web.app import create_app
from elenchos.web.static_files import has_built_ui


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-abc.js").write_text("console.log('ui');", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="/assets/index-abc.css">'
        '</head><body><div id="root"></div>'
        '<script type="module" src="/assets/index-abc.js"></script>'
        "</body></html>",
        encoding="utf-8",
    )
    (assets / "index-abc.css").write_text("body { margin: 0; }", encoding="utf-8")
    return tmp_path


def test_root_serves_spa(static_dir: Path):
    client = TestClient(create_app(static_dir=static_dir, enable_dev_cors=False))

    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="root"' in response.text


def test_unknown_client_route_falls_back_to_index(static_dir: Path):
    client = TestClient(create_app(static_dir=static_dir, enable_dev_cors=False))

    response = client.get("/benchmarks/text-reasoning-v1")
    assert response.status_code == 200
    assert 'id="root"' in response.text


def test_static_asset_served(static_dir: Path):
    client = TestClient(create_app(static_dir=static_dir, enable_dev_cors=False))

    response = client.get("/assets/index-abc.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_api_still_json_with_ui_mounted(static_dir: Path):
    client = TestClient(create_app(static_dir=static_dir, enable_dev_cors=False))

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_dev_cors_enabled_without_ui():
    client = TestClient(create_app(static_dir=Path("/nonexistent"), enable_dev_cors=True))

    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_package_includes_built_static_when_present():
    from importlib.resources import files

    if not has_built_ui():
        pytest.skip("built UI not present (run `cd web && npm run build`)")

    root = files("elenchos.web").joinpath("static")
    assert root.joinpath("index.html").is_file()
    assets = root.joinpath("assets")
    assert assets.is_dir()
    assert any(assets.iterdir())
