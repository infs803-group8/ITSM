"""Stopgap USER_VISIBLE/WORKFLOW comment writer for workflow actions that
must record a comment in the same transaction as their own ticket/SLA/
audit writes (C026 Request User Info today; likely also whichever of
C029/C030/C031/C033 turn out to need one).

Member B's ``comments`` domain (``model.py``/``repository.py``/
``service.py``) is still an empty scaffold -- see
``backend/app/domains/comments/*.py`` -- so there is no in-transaction
Comment repository interface yet for C to call, as
the original Member C project-management checklist's C026 "Ownership and
collaboration" item describes (B provides an in-transaction Comment
interface; C calls it). Rather than block on B's domain, or call the
plain HTTP API-20 endpoint (explicitly forbidden by C026.02: a second,
separate HTTP request/transaction would defeat the whole point of
writing the comment atomically with the ticket/SLA/audit changes), this
module is a narrow, raw-SQL INSERT against the same ``comments`` table B
will eventually own, matching schema.sql's ``comments`` CHECK constraints
exactly (``chk_comments_message``, ``chk_comments_visibility``,
``chk_comments_type``).

Once B publishes a real in-transaction Comment repository, every call
site of ``insert_workflow_comment`` should switch to it instead --
this function's signature (returns the new ``comment_id``, takes the
same ``Session`` the caller's own transaction is already using, never
commits) is deliberately shaped to make that swap a one-line change per
call site, not a redesign.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_workflow_comment(
    database: Session,
    *,
    ticket_id: int,
    author_id: int,
    message: str,
    workflow_action: str,
    visibility: str = "USER_VISIBLE",
) -> int:
    """Insert one WORKFLOW-type comment and return its ``comment_id``.

    Never commits -- shares the caller's own transaction, the same
    convention as ``AuditRepository.append``. The caller must still write
    its own ``COMMENT_ADDED`` audit event referencing the returned id
    (``chk_ticket_events_comment_type`` requires exactly that pairing,
    and only for that one event type -- this function does not, and must
    not, write to ``ticket_events`` itself). Callers are responsible for
    keeping ``workflow_action`` one of the ``state_machine.WorkflowAction``
    values that actually produces a user-visible comment; this function
    does not re-validate that choice, and it does not TRIM ``message``
    itself -- ``chk_comments_message`` checks ``TRIM(message)`` length at
    the database, so a caller must reject a whitespace-only message
    before calling this (C026's own service does).
    """
    result = database.execute(
        text(
            """
            INSERT INTO comments
                (ticket_id, author_id, message, visibility, comment_type, workflow_action)
            VALUES
                (:ticket_id, :author_id, :message, :visibility, 'WORKFLOW', :workflow_action)
            """
        ),
        {
            "ticket_id": ticket_id,
            "author_id": author_id,
            "message": message,
            "visibility": visibility,
            "workflow_action": workflow_action,
        },
    )
    return int(result.lastrowid)
