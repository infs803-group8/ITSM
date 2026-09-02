from app.api.dependencies import get_db
from app.main import app


class ReadyDatabase:
    def execute(self, _statement):
        return None


def override_ready_database():
    yield ReadyDatabase()


def test_health(client):
    app.dependency_overrides[get_db] = override_ready_database
    try:
        response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
    assert response.json()["data"]["checks"] == {"database": "ok"}
    assert "X-Request-ID" in response.headers
