"""assignment request and response schemas (API-21).

Re-exports the shared write-path shapes from ``app.domains.workflow.schema``
rather than redefining them -- ``TicketActionResponse``/``AssignmentRequest``
are used identically by every C024-C034 endpoint, not just this one.
"""

from app.domains.workflow.schema import AssignmentRequest, TicketActionResponse

__all__ = ["AssignmentRequest", "TicketActionResponse"]
