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
                "VALUES (2101,'Member B Vendor')"
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
                   'EXTERNAL_VENDOR',NULL,2101)
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
        assert created["data"]["status"] == "UNASSIGNED"
        assert created["data"]["sla"]["cycle_no"] == 1

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
                headers=_auth(1101),
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

        hidden = client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(1102))
        assert hidden.status_code == 404
        internal = client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=_auth(1101),
            json={"message": "Private", "visibility": "INTERNAL_ONLY"},
        )
        assert internal.status_code == 403
