from fastapi.testclient import TestClient

from elenchos import __version__
from elenchos.web.app import create_app


def test_health_returns_ok_and_version():
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
