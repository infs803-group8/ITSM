"""Pure role-aware serialization for the workflow slice of TicketDetail (C021).

Everything here is dataclasses/enum-only and takes plain ``Mapping`` input
(whatever ``WorkflowRepository.get_workflow_snapshot``/``get_latest_vendor_request``
return, or an equivalent plain dict in tests) -- no SQLAlchemy, no Pydantic, no
HTTP -- so it can be unit-tested directly and, unlike the DB-touching parts of
this domain, actually *executed* rather than merely syntax-checked in an
environment without third-party packages installed.

Scope (per C021.01/.02/.03/.04 and the acceptance table's dependency on C016/
C017/C020/C007): this module owns the columns C's write-path already owns --
``status``/``display_status``, ``sla``, ``pending_user``, ``resolution``,
``closure``, ``vendor_request`` and the *workflow* subset of
``available_actions``. It deliberately does NOT touch ``ticket_id``, ``title``,
``description``, ``category``, ``priority``, ``requester`` (identity fields,
Member B's ``tickets`` domain) or the ``EDIT``/``COMMENT``/``UPLOAD_ATTACHMENT``
members of the public ``AvailableAction`` enum (owned by B's tickets domain and
the comments/attachments domains respectively). Whoever assembles the final
``TicketDetail``/``TicketSummary`` response merges this module's
``available_actions`` with those three domains' own availability checks --
merging is not this module's job, and doing it here would silently hide a
missing contribution from one of those domains behind an empty list.

The role-aware field rules are recorded in docs/project-management/
decision-log.md Q02/Q06 and called out here at the serialization boundary:

* Q02 (Vendor field leakage): Vendor gets ``description``/``requester``/
  ``assignee``/``sla``/``pending_user``/``resolution``/``closure`` = null.
  B/C/D confirmed that both ``status`` and ``display_status`` use the same
  Vendor-safe three-state representation: ``CLOSED``, ``PENDING_VENDOR``
  while this organisation has an ACTIVE request, otherwise ``IN_PROGRESS``.
  Raw internal lifecycle states are never returned to a Vendor.
* Q06 (AssigneeSummary over-exposure to USER): still unresolved between
  "change the OpenAPI contract" (plan A) and "fabricate placeholder values"
  (plan B, explicitly *not recommended* in the decision log). Until the team
  picks one, this module returns the full, real ``AssigneeSummary`` to every
  role that can see the assignee at all, since fabricating data is worse
  than the current over-exposure and changing the contract is not this
  module's call to make alone.

One masking rule this module does apply unconditionally, because it is
explicitly required by task C021.02 rather than merely proposed in a draft
decision log: a USER-role actor's ``PENDING_VENDOR`` ticket must display as
``IN_PROGRESS`` (the ticket's dealings with a vendor organisation are internal
to engineering and are not surfaced to the requester). Consistently with that
same intent, this module also does not expose ``vendor_request`` to USER-role
actors at all: showing "IN_PROGRESS" while attaching a Vendor
name/message/response timeline directly underneath it would defeat the
masking task C021.02 asks for.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.core.enums import Category, TicketStatus, UserRole
from app.domains.workflow.state_machine import (
    PendingUserReason,
    SlaStatus,
    TicketState,
    WorkflowAction,
    available_actions,
)

# ---------------------------------------------------------------------------
# Actor context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActorContext:
    """The subset of the authenticated caller's identity this module needs.

    ``vendor_org_id`` is only meaningful (and only ever set) for
    ``UserRole.EXTERNAL_VENDOR`` actors.
    """

    role: UserRole
    user_id: int | None
    vendor_org_id: int | None = None


_ENGINEER_TIER_LABELS: dict[UserRole, str] = {
    UserRole.ENGINEER_TIER1: "TIER1",
    UserRole.ENGINEER_TIER2: "TIER2",
}

# WorkflowAction -> the public AvailableAction string it corresponds to.
# The 3 AvailableAction members with no entry here (EDIT, COMMENT,
# UPLOAD_ATTACHMENT) are not workflow actions at all -- see module docstring.
_PUBLIC_ACTION_LABELS: dict[WorkflowAction, str] = {
    WorkflowAction.ASSIGN: "ASSIGN",
    WorkflowAction.ESCALATE: "ESCALATE",
    WorkflowAction.START: "START",
    WorkflowAction.REQUEST_USER_INFO: "REQUEST_USER_INFO",
    WorkflowAction.USER_RESUME: "RESUME",
    WorkflowAction.REQUEST_VENDOR: "REQUEST_VENDOR",
    WorkflowAction.VENDOR_RESPONSE: "VENDOR_RESPONSE",
    WorkflowAction.SUBMIT_RESOLUTION: "RESOLVE",
    WorkflowAction.CONFIRM_RESOLUTION: "CONFIRM_RESOLUTION",
    WorkflowAction.REOPEN: "REOPEN",
    WorkflowAction.MANUAL_CLOSE: "CLOSE",
}

# Deterministic response ordering -- matches the OpenAPI enum's own order.
_PUBLIC_ACTION_ORDER: dict[str, int] = {
    "ASSIGN": 0,
    "START": 1,
    "REQUEST_USER_INFO": 2,
    "RESUME": 3,
    "ESCALATE": 4,
    "REQUEST_VENDOR": 5,
    "VENDOR_RESPONSE": 6,
    "RESOLVE": 7,
    "CONFIRM_RESOLUTION": 8,
    "REOPEN": 9,
    "CLOSE": 10,
}


def derive_display_status(
    status: TicketStatus,
    *,
    actor: ActorContext,
    vendor_request_status: str | None,
) -> str:
    """Role-aware status label (task C021.02).

    * USER's ``PENDING_VENDOR`` reads as ``IN_PROGRESS`` -- required by
      C021.02 verbatim, not a draft decision.
    * EXTERNAL_VENDOR never sees ``tickets.status_code`` at all (Q02 draft):
      they get a status derived purely from their own vendor request's
      lifecycle instead, so a vendor can never infer internal engineering
      states (ASSIGNED/REOPENED/...) they have no business seeing.
    * Every other role (and every other USER-visible status) sees the raw
      internal status value unchanged.
    """
    if actor.role is UserRole.EXTERNAL_VENDOR:
        if status is TicketStatus.CLOSED:
            return TicketStatus.CLOSED.value
        if vendor_request_status == "ACTIVE":
            return TicketStatus.PENDING_VENDOR.value
        return TicketStatus.IN_PROGRESS.value
    if actor.role is UserRole.USER and status is TicketStatus.PENDING_VENDOR:
        return TicketStatus.IN_PROGRESS.value
    return status.value


def build_ticket_state(raw: Mapping[str, Any]) -> TicketState:
    """Assemble the pure ``state_machine.TicketState`` this ticket is in.

    ``raw`` is exactly what ``WorkflowRepository.get_workflow_snapshot``
    returns (or an equivalent plain dict in tests).
    """
    assignee_role_code = raw.get("assignee_role_code")
    return TicketState(
        status=TicketStatus(raw["status_code"]),
        assignee_id=raw.get("assignee_user_id") or raw.get("assignee_id"),
        assignee_role=UserRole(assignee_role_code) if assignee_role_code else None,
        requester_id=raw["requester_id"],
        sla_status=SlaStatus(raw["sla_status_code"]),
        pending_user_reason=(
            PendingUserReason(raw["pending_user_reason"])
            if raw.get("pending_user_reason")
            else None
        ),
        has_active_vendor_request=bool(raw.get("has_active_vendor_request", False)),
    )


def available_action_labels(state: TicketState, *, actor: ActorContext) -> list[str]:
    """The workflow-owned subset of ``TicketDetail.available_actions``
    (C021.04); empty for a CLOSED ticket, since ``state_machine.evaluate``
    denies every action once ``state.status is TicketStatus.CLOSED``.
    """
    found = available_actions(
        state,
        actor_role=actor.role,
        actor_id=actor.user_id,
        actor_vendor_org_id=actor.vendor_org_id,
    )
    labels = {_PUBLIC_ACTION_LABELS[action] for action in found if action in _PUBLIC_ACTION_LABELS}
    return sorted(labels, key=lambda label: _PUBLIC_ACTION_ORDER[label])


def serialize_requester(raw: Mapping[str, Any], *, actor: ActorContext) -> dict[str, Any] | None:
    """Q02 draft: Vendor gets ``requester`` = null."""
    if actor.role is UserRole.EXTERNAL_VENDOR:
        return None
    return {
        "user_id": raw["requester_id"],
        "display_name": raw["requester_display_name"],
    }


def serialize_assignee(raw: Mapping[str, Any], *, actor: ActorContext) -> dict[str, Any] | None:
    """Q02 draft: Vendor gets ``assignee`` = null.

    Q06 is unresolved for every other role (see module docstring): every
    role that can see the assignee at all currently gets the full, real
    ``AssigneeSummary``, not a role-slimmed or fabricated one.
    """
    if actor.role is UserRole.EXTERNAL_VENDOR:
        return None
    assignee_user_id = raw.get("assignee_user_id")
    if assignee_user_id is None:
        return None
    role_code = raw.get("assignee_role_code")
    tier = _ENGINEER_TIER_LABELS.get(UserRole(role_code)) if role_code else None
    skill_codes = raw.get("assignee_skill_codes") or ""
    skills = [code for code in skill_codes.split(",") if code]
    return {
        "user_id": assignee_user_id,
        "display_name": raw.get("assignee_display_name"),
        "tier": tier,
        "skills": [Category(code).value for code in skills],
        "is_available": bool(raw.get("assignee_is_available")),
        "active_load": int(raw.get("assignee_active_load") or 0),
    }


def serialize_sla(raw: Mapping[str, Any], *, actor: ActorContext) -> dict[str, Any] | None:
    """Q02 draft: Vendor gets ``sla`` = null (internal SLA clock is not
    Vendor-visible; they track their own request via ``vendor_request``).
    """
    if actor.role is UserRole.EXTERNAL_VENDOR:
        return None
    return {
        "cycle_no": raw["sla_cycle_no"],
        "status": raw["sla_status_code"],
        "started_at": raw.get("sla_started_at"),
        "deadline": raw.get("sla_deadline"),
    }


def serialize_pending_user(raw: Mapping[str, Any], *, actor: ActorContext) -> dict[str, Any] | None:
    """Q02 draft: Vendor gets ``pending_user`` = null; null for everyone else
    when the ticket isn't currently ``PENDING_USER`` (``chk_tickets_pending_user``
    guarantees ``pending_user_reason``/``pending_user_deadline`` are NULL
    together whenever the ticket is outside that status).
    """
    if actor.role is UserRole.EXTERNAL_VENDOR:
        return None
    if not raw.get("pending_user_reason"):
        return None
    return {
        "reason": raw["pending_user_reason"],
        "deadline": raw["pending_user_deadline"],
    }


def serialize_resolution(raw: Mapping[str, Any], *, actor: ActorContext) -> dict[str, Any] | None:
    """Q02 draft: Vendor gets ``resolution`` = null; null for everyone else
    while there is no resolution summary on record yet at all.
    """
    if actor.role is UserRole.EXTERNAL_VENDOR:
        return None
    if not raw.get("resolution_summary"):
        return None
    return {
        "summary": raw["resolution_summary"],
        "type": raw.get("resolution_type"),
        "resolved_at": raw.get("resolved_at"),
        "auto_close_at": raw.get("auto_close_at"),
    }


def serialize_closure(raw: Mapping[str, Any], *, actor: ActorContext) -> dict[str, Any] | None:
    """Q02 draft: Vendor gets ``closure`` = null; null for everyone else
    while the ticket has not been closed.
    """
    if actor.role is UserRole.EXTERNAL_VENDOR:
        return None
    if not raw.get("closure_type"):
        return None
    return {
        "type": raw["closure_type"],
        "closed_at": raw["closed_at"],
    }


def serialize_vendor_request(
    vendor_row: Mapping[str, Any] | None,
    *,
    actor: ActorContext,
) -> dict[str, Any] | None:
    """The single "current" vendor request (Q03 draft: no history array here).

    * USER never sees this at all -- keeps C021.02's PENDING_VENDOR-as-
      IN_PROGRESS masking meaningful (see module docstring).
    * EXTERNAL_VENDOR only ever sees a request that belongs to their own
      organisation -- cross-org isolation, never negotiable regardless of
      Q02/Q06's open sub-items.
    * TIER1/TIER2/MANAGER see it in full.
    """
    if vendor_row is None:
        return None
    if actor.role is UserRole.USER:
        return None
    if (
        actor.role is UserRole.EXTERNAL_VENDOR
        and vendor_row["vendor_org_id"] != actor.vendor_org_id
    ):
        return None
    return {
        "vendor_request_id": vendor_row["vendor_request_id"],
        "vendor_org": {
            "vendor_org_id": vendor_row["vendor_org_id"],
            "name": vendor_row["vendor_org_name"],
            "is_active": bool(vendor_row["vendor_org_is_active"]),
        },
        "status": vendor_row["status"],
        "vendor_message": vendor_row["vendor_message"],
        "created_at": vendor_row["created_at"],
        "responded_at": vendor_row.get("responded_at"),
    }


def build_ticket_workflow_view(
    raw: Mapping[str, Any],
    vendor_row: Mapping[str, Any] | None,
    *,
    actor: ActorContext,
) -> dict[str, Any]:
    """Assemble the workflow-owned slice of ``TicketDetail``/``TicketSummary``
    for one role (C021.01/.03/.04). The caller (B's tickets serializer) is
    responsible for merging this with ``ticket_id``/``title``/``description``/
    ``category``/``priority``/``created_at``/``updated_at`` and with the
    EDIT/COMMENT/UPLOAD_ATTACHMENT members of ``available_actions``.
    """
    status = TicketStatus(raw["status_code"])
    has_active_vendor_request = bool(vendor_row is not None and vendor_row["status"] == "ACTIVE")
    state = build_ticket_state({**raw, "has_active_vendor_request": has_active_vendor_request})
    vendor_request_status = vendor_row["status"] if vendor_row is not None else None
    visible_status = derive_display_status(
        status, actor=actor, vendor_request_status=vendor_request_status
    )
    return {
        "status": visible_status,
        "display_status": visible_status,
        "requester": serialize_requester(raw, actor=actor),
        "assignee": serialize_assignee(raw, actor=actor),
        "sla": serialize_sla(raw, actor=actor),
        "pending_user": serialize_pending_user(raw, actor=actor),
        "resolution": serialize_resolution(raw, actor=actor),
        "closure": serialize_closure(raw, actor=actor),
        "vendor_request": serialize_vendor_request(vendor_row, actor=actor),
        "available_actions": available_action_labels(state, actor=actor),
    }
