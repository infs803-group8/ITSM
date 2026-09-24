"""Import all ORM models here before metadata operations.

The reviewed SQL schema remains authoritative during v6.0. Each domain
owner adds their own model import below (additive only -- do not remove
another owner's import without checking with them first, per
.github/CODEOWNERS and docs/development/git-workflow.md's shared-hotspot
rule).
"""

from app.domains.audit.model import TicketEvent  # noqa: F401  (Member C)
