"""Vendor-workflow write-path services (C029 onward).

Follows the same lock/evaluate/apply/audit shape as
``app.domains.workflow.service``'s C025-C028 classes, reusing the same
shared ``action_engine`` infrastructure -- this domain's actions are
still workflow actions (``state_machine.WorkflowAction.REQUEST_VENDOR``
etc.), just ones whose own request/response payloads and their own
``vendor_requests``/``vendor_organisations`` table live in
``vendor_workflow`` rather than ``workflow``.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.common.request_context import RequestContext
from app.core.clock import utc_now
from app.core.enums import EventScope, EventType, UserRole
from app.core.errors import ApplicationError
from app.domains.audit.service import AuditService
from app.domains.workflow.action_engine import evaluate_or_raise, lock_ticket_state
from app.domains.workflow.error_mapping import error_for_denial
from app.domains.workflow.repository import WorkflowRepository
from app.domains.workflow.state_machine import ActionRequest, TicketStatus, WorkflowAction
from app.domains.vendor_workflow.repository import VendorWorkflowRepository


@dataclass(frozen=True)
class VendorRequestOutcome:
    status: TicketStatus
    event_id: int
    vendor_request_id: int


class RequestVendorService:
    """API-26 Request Vendor (C029): IN_PROGRESS -> PENDING_VENDOR,
    current Tier 2 assignee only. ``state_machine._eval_request_vendor``'s
    ``cycle_effect`` is "KEEP" -- the Engineering SLA cycle is left
    completely untouched (C029.04's "保持工程 SLA"), and its own
    ``has_active_vendor_request`` check is the ordinary-case guard
    against a second concurrent ACTIVE request, already denying with
    ``VENDOR_REQUEST_ALREADY_ACTIVE`` (-> public ``ACTIVE_VENDOR_REQUEST_
    EXISTS``) before this service ever attempts the INSERT.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.workflow_repository = WorkflowRepository(database)
        self.repository = VendorWorkflowRepository(database)
        self.audit = AuditService(database)

    def request_vendor(
        self,
        *,
        ticket_id: int,
        actor: RequestContext,
        vendor_org_id: int,
        vendor_message: str,
        now: datetime | None = None,
    ) -> VendorRequestOutcome:
        now = now or utc_now()
        locked = lock_ticket_state(self.workflow_repository, ticket_id=ticket_id, now=now)

        # C029.02: the target organisation itself is not a state_machine
        # concept -- validate it here. There is no dedicated ErrorCode
        # for "no such vendor organisation" in the frozen public
        # ErrorCode enum, so this uses VALIDATION_ERROR (422), the same
        # best-fit choice already used elsewhere in this stack for a
        # request value that fails validation with no more specific code
        # available (see RequestUserInfoService's blank-message check).
        org = self.repository.get_vendor_organisation(vendor_org_id)
        if org is None or not bool(org["is_active"]):
            raise ApplicationError(
                "VALIDATION_ERROR",
                "The selected vendor organisation does not exist or is not active.",
                422,
            )

        request = ActionRequest(
            action=WorkflowAction.REQUEST_VENDOR,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
        )
        result = evaluate_or_raise(locked.state, request)
        assert result.vendor_request_effect == "CREATE_ACTIVE"
        assert result.cycle_effect == "KEEP"

        # C029.03: save exactly the Tier 2 engineer's own de-identified
        # input -- never the ticket's own description or the requester's
        # profile, which this method never even reads.
        try:
            vendor_request_id = self.repository.create_active_request(
                ticket_id=ticket_id,
                vendor_org_id=vendor_org_id,
                requested_by_id=actor.user_id,
                vendor_message=vendor_message,
            )
        except IntegrityError:
            # C029.05: the has_active_vendor_request check above already
            # covers the ordinary case; reaching here means a genuine
            # concurrent request won the race between this transaction's
            # lock and its INSERT. Roll back this statement's failed
            # state and report the same, already-established denial the
            # ordinary case uses -- never let the raw IntegrityError (or
            # which unique key it was) reach the client.
            self.database.rollback()
            raise error_for_denial(
                "VENDOR_REQUEST_ALREADY_ACTIVE",
                "This ticket already has an active vendor request.",
            ) from None

        # C029.04: PENDING_VENDOR, Engineering SLA untouched (no sla.*
        # call -- see this class's own docstring).
        self.workflow_repository.apply_status_change(
            ticket_id=ticket_id, status_code=result.target_status.value
        )

        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.VENDOR_REQUESTED,
            scope=EventScope.VENDOR_SCOPE,
            actor_id=actor.user_id,
            vendor_org_id=vendor_org_id,
            vendor_request_id=vendor_request_id,
        )
        return VendorRequestOutcome(
            status=result.target_status, event_id=event_id, vendor_request_id=vendor_request_id
        )
