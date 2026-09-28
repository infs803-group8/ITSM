"""Real-MySQL coverage for the Q03 vendor history read (C047):
organisation isolation, ordering and response attachment.

Reads through ``VendorHistoryReader`` directly; the public route is B's
follow-up PR. Run through ``scripts/run_mysql_integration.py``. Uses its
own IDs (33xx) and the OTHER category so no other integration test's seed
data interferes.
"""

import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.config import get_settings
from app.core.errors import ApplicationError
from app.domains.vendor_workflow.history import VendorHistoryReader
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="Requires the disposable local MySQL integration schema.",
)

ORG_A, ORG_B = 3301, 3302
REQUESTER, TIER2, VENDOR_A, VENDOR_B, MANAGER, TIER1 = 3310, 3311, 3312, 3313, 3314, 3315


def _seed(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO vendor_organisations (vendor_org_id,name) "
                "VALUES (3301,'History Vendor A'),(3302,'History Vendor B')"
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO users
                  (user_id,email,password_hash,display_name,role_code,
                   is_available,vendor_org_id)
                VALUES
                  (3310,'c-hist-user@test.local','unused','Hist User','USER',NULL,NULL),
                  (3311,'c-hist-t2@test.local','unused','Hist T2','ENGINEER_TIER2',1,NULL),
                  (3312,'c-hist-va@test.local','unused','Hist Vendor A',
                   'EXTERNAL_VENDOR',NULL,3301),
                  (3313,'c-hist-vb@test.local','unused','Hist Vendor B',
                   'EXTERNAL_VENDOR',NULL,3302),
                  (3314,'c-hist-mgr@test.local','unused','Hist Manager',
                   'SERVICE_DESK_MANAGER',NULL,NULL),
                  (3315,'c-hist-t1@test.local','unused','Hist T1','ENGINEER_TIER1',1,NULL)
                """
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


def _create_ticket() -> int:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tickets",
            headers=_auth(REQUESTER),
            json={
                "title": "C vendor history regression",
                "description": "Printer driver keeps crashing.",
                "category": "OTHER",
                "priority": "MEDIUM",
            },
        )
    assert response.status_code == 201, response.text
    return response.json()["data"]["ticket_id"]


def _seed_history(engine, ticket_id: int) -> tuple[int, int, int]:
    base = datetime(2026, 9, 1, 1, 0, 0)
    with engine.begin() as connection:
        # 1) Org A, answered.
        first = connection.execute(
            text(
                "INSERT INTO vendor_requests (ticket_id,vendor_org_id,requested_by_id,"
                "vendor_message,status,created_at,responded_at) VALUES "
                "(:t,:org,:by,'First question for A','RESPONDED',:c,:r)"
            ),
            {"t": ticket_id, "org": ORG_A, "by": TIER2, "c": base, "r": base + timedelta(hours=1)},
        ).lastrowid
        connection.execute(
            text(
                "INSERT INTO vendor_responses (vendor_request_id,responder_id,message,created_at) "
                "VALUES (:vr,:who,'Answer from A',:c)"
            ),
            {"vr": first, "who": VENDOR_A, "c": base + timedelta(hours=1)},
        )
        # 2) Org B, cancelled.
        second = connection.execute(
            text(
                "INSERT INTO vendor_requests (ticket_id,vendor_org_id,requested_by_id,"
                "vendor_message,status,created_at,cancelled_at,cancelled_by_id,"
                "cancellation_reason) VALUES "
                "(:t,:org,:by,'Question for B','CANCELLED',:c,:x,:by,'No longer needed')"
            ),
            {
                "t": ticket_id,
                "org": ORG_B,
                "by": TIER2,
                "c": base + timedelta(hours=2),
                "x": base + timedelta(hours=3),
            },
        ).lastrowid
        # 3) Org A again, still active.
        third = connection.execute(
            text(
                "INSERT INTO vendor_requests (ticket_id,vendor_org_id,requested_by_id,"
                "vendor_message,status,created_at) VALUES "
                "(:t,:org,:by,'Follow-up for A','ACTIVE',:c)"
            ),
            {"t": ticket_id, "org": ORG_A, "by": TIER2, "c": base + timedelta(hours=4)},
        ).lastrowid
    return first, second, third


def _ctx(user_id: int, role: str, vendor_org_id: int | None = None) -> RequestContext:
    return RequestContext(user_id=user_id, role=role, vendor_org_id=vendor_org_id)


def test_vendor_history_isolation_and_order_with_real_mysql():
    settings = get_settings()
    assert settings.database_url.endswith("/service_desk_member_a_test")
    engine = create_engine(settings.database_url)
    _seed(engine)
    ticket_id = _create_ticket()
    first, second, third = _seed_history(engine, ticket_id)

    with Session(engine) as database:
        reader = VendorHistoryReader(database)

        for actor in (_ctx(TIER2, "ENGINEER_TIER2"), _ctx(MANAGER, "SERVICE_DESK_MANAGER")):
            items = reader.list_for_actor(ticket_id=ticket_id, actor=actor)
            assert [i["vendor_request_id"] for i in items] == [first, second, third]
            assert [i["status"] for i in items] == ["RESPONDED", "CANCELLED", "ACTIVE"]
            assert items[0]["response"]["message"] == "Answer from A"
            assert items[1]["response"] is None
            assert items[2]["response"] is None
            assert items[0]["created_at"].tzinfo is not None

        vendor_a = reader.list_for_actor(
            ticket_id=ticket_id, actor=_ctx(VENDOR_A, "EXTERNAL_VENDOR", ORG_A)
        )
        assert [i["vendor_request_id"] for i in vendor_a] == [first, third]
        assert {i["vendor_org"]["vendor_org_id"] for i in vendor_a} == {ORG_A}
        assert vendor_a[0]["response"]["message"] == "Answer from A"

        vendor_b = reader.list_for_actor(
            ticket_id=ticket_id, actor=_ctx(VENDOR_B, "EXTERNAL_VENDOR", ORG_B)
        )
        assert [i["vendor_request_id"] for i in vendor_b] == [second]
        assert all("Answer from A" != (i["response"] or {}).get("message") for i in vendor_b)

        for actor in (_ctx(REQUESTER, "USER"), _ctx(TIER1, "ENGINEER_TIER1")):
            with pytest.raises(ApplicationError) as excinfo:
                reader.list_for_actor(ticket_id=ticket_id, actor=actor)
            assert excinfo.value.status_code == 403

        # Read-only: nothing was written by the reads above.
        assert not database.dirty and not database.new
