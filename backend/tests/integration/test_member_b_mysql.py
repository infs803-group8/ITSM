"""HTTP-to-MySQL coverage for Member B API-12 through API-20."""

import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="Requires the disposable local MySQL integration schema.",
)


def _seed(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO vendor_organisations (vendor_org_id,name) "
                "VALUES (2101,'Member B Vendor'),(2102,'Second Vendor')"
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO users
                  (user_id,email,password_hash,display_name,role_code,
                   is_available,vendor_org_id)
                VALUES
                  (1101,'member-b-user@test.local','unused','Member B User','USER',NULL,NULL),
                  (1102,'member-b-t1@test.local','unused','Member B T1','ENGINEER_TIER1',1,NULL),
                  (1103,'member-b-t2@test.local','unused','Member B T2','ENGINEER_TIER2',1,NULL),
                  (1104,'member-b-manager@test.local','unused','Member B Manager',
                   'SERVICE_DESK_MANAGER',NULL,NULL),
                  (1105,'member-b-vendor@test.local','unused','Member B Vendor User',
                   'EXTERNAL_VENDOR',NULL,2101),
                  (1106,'member-b-vendor-2@test.local','unused','Second Vendor User',
                   'EXTERNAL_VENDOR',NULL,2102)
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO user_skills (user_id,category_code) "
                "VALUES (1102,'NETWORK'),(1103,'NETWORK'),(1103,'SOFTWARE')"
            )
        )


def _token(user_id: int) -> str:
    settings = get_settings()
    return jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _expect(response, status_code: int, label: str) -> dict:
    assert response.status_code == status_code, f"{label}: {response.text}"
    return response.json()


def test_member_b_api_12_through_20_with_real_mysql():
    settings = get_settings()
    assert settings.database_url.endswith("/service_desk_member_a_test")
    engine = create_engine(settings.database_url)
    _seed(engine)

    with TestClient(app) as client:
        reference = _expect(
            client.get("/api/v1/reference-data", headers=_auth(1101)), 200, "API-12"
        )
        assert reference["data"]["timers"]["engineering_sla_hours"] == 48
        assert "PENDING_VENDOR" not in reference["data"]["ticket_statuses"]

        assignees = _expect(
            client.get(
                "/api/v1/users/assignees?tier=TIER2&category=NETWORK",
                headers=_auth(1104),
            ),
            200,
            "API-13",
        )
        assert 1103 in [item["user_id"] for item in assignees["data"]]
        assert all(item["tier"] == "TIER2" for item in assignees["data"])
        assert all("NETWORK" in item["skills"] for item in assignees["data"])

        vendors = _expect(
            client.get("/api/v1/vendors?is_active=true", headers=_auth(1103)),
            200,
            "API-14",
        )
        assert any(item["vendor_org_id"] == 2101 for item in vendors["data"])

        created = _expect(
            client.post(
                "/api/v1/tickets",
                headers=_auth(1101),
                json={
                    "title": "Member B integration ticket",
                    "description": "Validate API-15 through API-20.",
                    "category": "NETWORK",
                    "priority": "HIGH",
                },
            ),
            201,
            "API-15",
        )
        ticket_id = created["data"]["ticket_id"]
        assert created["data"]["status"] == "ASSIGNED"
        assert created["data"]["assignee"]["tier"] == "TIER1"
        assert "NETWORK" in created["data"]["assignee"]["skills"]
        assert created["data"]["sla"]["cycle_no"] == 1
        assert created["data"]["sla"]["deadline"] is not None
        assert "EDIT" not in created["data"]["available_actions"]

        with engine.connect() as connection:
            event_types = connection.execute(
                text(
                    "SELECT event_type FROM ticket_events "
                    "WHERE ticket_id=:ticket_id ORDER BY event_id"
                ),
                {"ticket_id": ticket_id},
            ).scalars().all()
        assert event_types == ["TICKET_CREATED", "SLA_CYCLE_STARTED", "AUTO_ASSIGNED"]

        listed = _expect(
            client.get("/api/v1/tickets?search=integration", headers=_auth(1101)),
            200,
            "API-16",
        )
        assert any(item["ticket_id"] == ticket_id for item in listed["data"])

        detail = _expect(
            client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(1101)),
            200,
            "API-17",
        )
        assert detail["data"]["requester"]["user_id"] == 1101

        updated = _expect(
            client.patch(
                f"/api/v1/tickets/{ticket_id}",
                headers=_auth(1104),
                json={"priority": "URGENT"},
            ),
            200,
            "API-18",
        )
        assert updated["data"]["priority"] == "URGENT"

        comment = _expect(
            client.post(
                f"/api/v1/tickets/{ticket_id}/comments",
                headers=_auth(1101),
                json={"message": "Additional information", "visibility": "USER_VISIBLE"},
            ),
            201,
            "API-20",
        )
        assert comment["data"]["author"]["user_id"] == 1101

        comments = _expect(
            client.get(f"/api/v1/tickets/{ticket_id}/comments", headers=_auth(1101)),
            200,
            "API-19",
        )
        assert comments["data"][0]["message"] == "Additional information"

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO vendor_requests "
                    "(ticket_id,vendor_org_id,requested_by_id,vendor_message,status,"
                    "created_at,responded_at) VALUES "
                    "(:ticket_id,2101,1103,'Please investigate','RESPONDED',"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"ticket_id": ticket_id},
            )
            connection.execute(
                text(
                    "UPDATE tickets SET status_code='PENDING_VENDOR', assignee_id=1103 "
                    "WHERE ticket_id=:ticket_id"
                ),
                {"ticket_id": ticket_id},
            )

        vendor_detail = _expect(
            client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(1105)),
            200,
            "API-17 vendor-safe status",
        )
        assert vendor_detail["data"]["status"] == "IN_PROGRESS"
        assert vendor_detail["data"]["display_status"] == "IN_PROGRESS"

        vendor_in_progress = _expect(
            client.get("/api/v1/tickets?status=IN_PROGRESS", headers=_auth(1105)),
            200,
            "API-16 vendor visible status filter",
        )
        assert ticket_id in [item["ticket_id"] for item in vendor_in_progress["data"]]
        assert (
            client.get("/api/v1/tickets?status=RESOLVED", headers=_auth(1105)).status_code
            == 403
        )
        assert (
            client.get("/api/v1/tickets?sla_status=OVERDUE", headers=_auth(1105)).status_code
            == 403
        )

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO vendor_requests "
                    "(ticket_id,vendor_org_id,requested_by_id,vendor_message,status,created_at) "
                    "VALUES (:ticket_id,2102,1103,'Second vendor investigate','ACTIVE',"
                    "DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 1 SECOND))"
                ),
                {"ticket_id": ticket_id},
            )

        historical_vendor_detail = _expect(
            client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(1105)),
            200,
            "API-17 historical vendor isolation",
        )
        assert historical_vendor_detail["data"]["status"] == "IN_PROGRESS"
        assert historical_vendor_detail["data"]["vendor_request"]["status"] == "RESPONDED"
        assert "VENDOR_RESPONSE" not in historical_vendor_detail["data"]["available_actions"]

        active_vendor_detail = _expect(
            client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(1106)),
            200,
            "API-17 active vendor status",
        )
        assert active_vendor_detail["data"]["status"] == "PENDING_VENDOR"
        assert active_vendor_detail["data"]["vendor_request"]["status"] == "ACTIVE"
        assert "VENDOR_RESPONSE" in active_vendor_detail["data"]["available_actions"]

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE tickets SET status_code='PENDING_VENDOR', assignee_id=1103 "
                    "WHERE ticket_id=:ticket_id"
                ),
                {"ticket_id": ticket_id},
            )
        in_progress = _expect(
            client.get(
                "/api/v1/tickets?status=IN_PROGRESS",
                headers=_auth(1101),
            ),
            200,
            "API-16 visible status filter",
        )
        filtered_ticket = next(
            item for item in in_progress["data"] if item["ticket_id"] == ticket_id
        )
        assert filtered_ticket["status"] == "IN_PROGRESS"

        hidden = client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(1102))
        assert hidden.status_code == 404
        internal = client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=_auth(1101),
            json={"message": "Private", "visibility": "INTERNAL_ONLY"},
        )
        assert internal.status_code == 403
