"""Member A HTTP-to-MySQL integration test.

Run only against the disposable ``service_desk_member_a_test`` schema:

RUN_MYSQL_INTEGRATION=1 pytest tests/integration/test_member_a_mysql.py
"""

import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.domains.attachments.router import get_object_storage
from app.integrations.s3.object_verification import ObjectInfo
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="Requires the disposable local MySQL integration schema.",
)


class FakeStorage:
    """Keeps this test local while exercising the real attachment DB flow."""

    def __init__(self) -> None:
        self.head_calls = 0

    def create_upload_url(self, *, object_key, content_type, expires_in):
        return f"https://storage.test/{object_key}?upload=1"

    def head_object(self, *, object_key):
        self.head_calls += 1
        return ObjectInfo(size_bytes=100, content_type="text/plain")

    def create_download_url(
        self, *, object_key, file_name, content_type, expires_in
    ):
        return f"https://storage.test/{object_key}?download=1"

    def delete_object(self, *, object_key):
        return None


def _seed_database(engine) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO vendor_organisations (vendor_org_id,name) "
                "VALUES (2001,'Integration Vendor')"
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO users
                  (user_id,email,password_hash,display_name,role_code,
                   is_available,vendor_org_id)
                VALUES
                  (1001,'requester@test.local','not-a-real-password',
                   'Requester','USER',NULL,NULL),
                  (1002,'tier1@test.local','not-a-real-password',
                   'Tier One','ENGINEER_TIER1',1,NULL),
                  (1003,'tier2@test.local','not-a-real-password',
                   'Tier Two','ENGINEER_TIER2',1,NULL),
                  (1004,'manager@test.local','not-a-real-password',
                   'Manager','SERVICE_DESK_MANAGER',NULL,NULL),
                  (1005,'vendor@test.local','not-a-real-password',
                   'Vendor User','EXTERNAL_VENDOR',NULL,2001)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO user_skills (user_id,category_code)
                VALUES (1002,'NETWORK'),(1003,'NETWORK'),(1003,'SOFTWARE')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO tickets
                  (ticket_id,requester_id,title,description,category_code,
                   priority_code,status_code,assignee_id,sla_cycle_no,
                   sla_status_code,sla_started_at,sla_deadline)
                VALUES
                  (5001,1001,'VPN unavailable','Integration dashboard ticket',
                   'NETWORK','HIGH','IN_PROGRESS',1003,1,'OVERDUE',
                   :started,:deadline),
                  (5002,1001,'Router vendor case','Integration vendor ticket',
                   'NETWORK','MEDIUM','PENDING_VENDOR',1003,1,'ON_TRACK',
                   :now,:future)
                """
            ),
            {
                "started": now - timedelta(hours=72),
                "deadline": now - timedelta(hours=24),
                "now": now,
                "future": now + timedelta(hours=48),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO vendor_requests
                  (vendor_request_id,ticket_id,vendor_org_id,requested_by_id,
                   vendor_message,status)
                VALUES
                  (6001,5002,2001,1003,'Please check the router logs.','ACTIVE')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO ticket_events
                  (ticket_id,event_type,scope,actor_id,cycle_no,metadata,occurred_at)
                VALUES
                  (5001,'SLA_OVERDUE','INTERNAL_ONLY',NULL,1,
                   JSON_OBJECT('sla_deadline', :deadline_iso), :deadline)
                """
            ),
            {
                "deadline_iso": (now - timedelta(hours=24)).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "deadline": now - timedelta(hours=24),
            },
        )


def _expect(response, status_code: int, label: str) -> dict:
    assert response.status_code == status_code, f"{label}: {response.text}"
    return response.json()


def test_member_a_api_01_through_07_with_real_mysql():
    settings = get_settings()
    assert settings.database_url.endswith("/service_desk_member_a_test")
    engine = create_engine(settings.database_url)
    _seed_database(engine)

    def token(user_id: int) -> str:
        return jwt.encode(
            {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(hours=1)},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

    def auth(user_id: int) -> dict[str, str]:
        return {"Authorization": f"Bearer {token(user_id)}"}

    storage = FakeStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            health = _expect(client.get("/api/v1/health"), 200, "API-01")
            assert health["data"]["checks"]["database"] == "ok"

            presign = _expect(
                client.post(
                    "/api/v1/tickets/5001/attachments/presign",
                    headers=auth(1003),
                    json={
                        "file_name": "router.log",
                        "content_type": "text/plain",
                        "size_bytes": 100,
                        "visibility": "INTERNAL_ONLY",
                    },
                ),
                201,
                "API-02",
            )
            upload_id = presign["data"]["upload_id"]
            assert presign["data"]["signed_headers"] == {
                "Content-Type": "text/plain"
            }

            completed = _expect(
                client.post(
                    "/api/v1/tickets/5001/attachments/complete",
                    headers=auth(1003),
                    json={"upload_id": upload_id},
                ),
                200,
                "API-03",
            )
            attachment_id = completed["data"]["attachment_id"]
            repeated = _expect(
                client.post(
                    "/api/v1/tickets/5001/attachments/complete",
                    headers=auth(1003),
                    json={"upload_id": upload_id},
                ),
                200,
                "API-03 idempotency",
            )
            assert repeated["data"]["attachment_id"] == attachment_id

            listed = _expect(
                client.get(
                    "/api/v1/tickets/5001/attachments", headers=auth(1003)
                ),
                200,
                "API-04",
            )
            assert listed["meta"]["total"] == 1
            assert listed["data"][0]["visibility"] == "INTERNAL_ONLY"

            download = _expect(
                client.get(
                    f"/api/v1/tickets/5001/attachments/{attachment_id}/download",
                    headers=auth(1003),
                ),
                200,
                "API-05",
            )
            assert download["data"]["download_url"].startswith(
                "https://storage.test/"
            )

            summary = _expect(
                client.get("/api/v1/dashboard/summary", headers=auth(1003)),
                200,
                "API-06",
            )
            assert summary["data"]["scope"] == "MY_ASSIGNED"
            assert summary["data"]["counts"]["total_active"] == 2
            assert summary["data"]["sla"]["overdue"] == 1

            current = _expect(
                client.get(
                    "/api/v1/dashboard/overdue-tickets?mode=current",
                    headers=auth(1003),
                ),
                200,
                "API-07 current",
            )
            history = _expect(
                client.get(
                    "/api/v1/dashboard/overdue-tickets?mode=history",
                    headers=auth(1003),
                ),
                200,
                "API-07 history",
            )
            assert current["meta"]["total"] == 1
            assert current["data"][0]["ticket_id"] == 5001
            assert history["meta"]["total"] == 1
            assert history["data"][0]["ticket_id"] == 5001

            vendor_presign = _expect(
                client.post(
                    "/api/v1/tickets/5002/attachments/presign",
                    headers=auth(1003),
                    json={
                        "file_name": "vendor.log",
                        "content_type": "text/plain",
                        "size_bytes": 100,
                        "visibility": "VENDOR_SHARED",
                    },
                ),
                201,
                "API-02 vendor",
            )
            vendor_complete = _expect(
                client.post(
                    "/api/v1/tickets/5002/attachments/complete",
                    headers=auth(1003),
                    json={"upload_id": vendor_presign["data"]["upload_id"]},
                ),
                200,
                "API-03 vendor",
            )
            vendor_list = _expect(
                client.get(
                    "/api/v1/tickets/5002/attachments", headers=auth(1005)
                ),
                200,
                "API-04 vendor scope",
            )
            assert vendor_list["meta"]["total"] == 1
            assert (
                vendor_list["data"][0]["attachment_id"]
                == vendor_complete["data"]["attachment_id"]
            )

            hidden = _expect(
                client.get(
                    "/api/v1/tickets/5002/attachments", headers=auth(1002)
                ),
                404,
                "Tier 1 hidden scope",
            )
            assert hidden["error"]["code"] == "RESOURCE_NOT_FOUND"

            manager = _expect(
                client.get("/api/v1/dashboard/summary", headers=auth(1004)),
                200,
                "Manager dashboard",
            )
            assert manager["data"]["scope"] == "GLOBAL"

        with engine.connect() as connection:
            counts = connection.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM attachment_uploads) AS uploads,
                      (SELECT COUNT(*) FROM attachments) AS attachments,
                      (SELECT COUNT(*) FROM ticket_events
                       WHERE event_type='ATTACHMENT_ADDED') AS attachment_events
                    """
                )
            ).mappings().one()
            assert dict(counts) == {
                "uploads": 2,
                "attachments": 2,
                "attachment_events": 2,
            }
        assert storage.head_calls == 2
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
