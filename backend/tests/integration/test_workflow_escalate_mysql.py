"""HTTP-to-MySQL regression for ESCALATE (API-25) through the shared
TicketDetail assembler (PR-2, agreed B/C).

The Tier 1 caller loses normal GET scope the moment the ticket moves to
Tier 2. The action response must still be HTTP 200 with the committed
state, ``available_actions == []`` and ``vendor_request == null``; a later
GET by the former Tier 1 assignee is 404 and by the new Tier 2 assignee
200. Run through ``scripts/run_mysql_integration.py`` (disposable schema).

Uses its own user IDs (3101-3104) and the ACCOUNT category, which no other
integration test seeds a skill for, so auto-assignment is deterministic.
"""

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

REQUESTER, TIER1, TIER2, MANAGER = 3101, 3102, 3103, 3104
VENDOR_ORG = 3201


def _seed(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO vendor_organisations (vendor_org_id,name) "
                "VALUES (:org,'C Escalate Vendor')"
            ),
            {"org": VENDOR_ORG},
        )
        connection.execute(
            text(
                """
                INSERT INTO users
                  (user_id,email,password_hash,display_name,role_code,
                   is_available,vendor_org_id)
                VALUES
                  (3101,'c-esc-user@test.local','unused','C Esc User','USER',NULL,NULL),
                  (3102,'c-esc-t1@test.local','unused','C Esc T1','ENGINEER_TIER1',1,NULL),
                  (3103,'c-esc-t2@test.local','unused','C Esc T2','ENGINEER_TIER2',1,NULL),
                  (3104,'c-esc-manager@test.local','unused','C Esc Manager',
                   'SERVICE_DESK_MANAGER',NULL,NULL)
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO user_skills (user_id,category_code) "
                "VALUES (3102,'ACCOUNT'),(3103,'ACCOUNT')"
            )
        )


def _auth(user_id: int) -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _expect(response, status_code: int, label: str) -> dict:
    assert response.status_code == status_code, f"{label}: {response.text}"
    return response.json()


def test_escalate_response_and_follow_up_scope_with_real_mysql():
    settings = get_settings()
    assert settings.database_url.endswith("/service_desk_member_a_test")
    engine = create_engine(settings.database_url)
    _seed(engine)

    with TestClient(app) as client:
        created = _expect(
            client.post(
                "/api/v1/tickets",
                headers=_auth(REQUESTER),
                json={
                    "title": "C escalate regression",
                    "description": "Account locked after password reset.",
                    "category": "ACCOUNT",
                    "priority": "HIGH",
                },
            ),
            201,
            "API-15",
        )
        ticket_id = created["data"]["ticket_id"]
        assert created["data"]["assignee"]["user_id"] == TIER1

        _expect(
            client.post(f"/api/v1/tickets/{ticket_id}/start", headers=_auth(TIER1)),
            200,
            "API-22",
        )

        # A historical (already answered) vendor request, so the Tier 1
        # vendor-payload isolation is actually exercised.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO vendor_requests "
                    "(ticket_id,vendor_org_id,requested_by_id,vendor_message,status,"
                    "created_at,responded_at) VALUES "
                    "(:ticket_id,:org,:t2,'Historical request','RESPONDED',"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"ticket_id": ticket_id, "org": VENDOR_ORG, "t2": TIER2},
            )

        escalated = _expect(
            client.post(
                f"/api/v1/tickets/{ticket_id}/escalate",
                headers=_auth(TIER1),
                json={"tier2_assignee_id": TIER2, "reason": "Needs directory access."},
            ),
            200,
            "API-25",
        )
        data = escalated["data"]
        assert data["action"] == "ESCALATE"
        assert data["ticket"]["status"] == "ASSIGNED"
        assert data["ticket"]["assignee"]["user_id"] == TIER2
        assert data["ticket"]["available_actions"] == []
        assert data["ticket"]["vendor_request"] is None
        assert data["vendor_request"] is None
        assert data["ticket"]["updated_at"].endswith(("Z", "+00:00"))

        with engine.connect() as connection:
            saved = connection.execute(
                text("SELECT status_code, assignee_id FROM tickets WHERE ticket_id=:id"),
                {"id": ticket_id},
            ).one()
        assert saved.status_code == "ASSIGNED"
        assert saved.assignee_id == TIER2

        _expect(
            client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(TIER1)),
            404,
            "API-17 former Tier 1 assignee",
        )
        tier2_view = _expect(
            client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth(TIER2)),
            200,
            "API-17 new Tier 2 assignee",
        )
        assert "START" in tier2_view["data"]["available_actions"]
        assert tier2_view["data"]["vendor_request"] is not None
