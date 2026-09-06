"""Import all ORM models here before metadata operations.

The reviewed SQL schema remains authoritative during v6.0.
"""

from app.domains.comments.model import Comment
from app.domains.tickets.model import Ticket
from app.domains.users.model import User, UserSkill, VendorOrganisation

__all__ = ["Comment", "Ticket", "User", "UserSkill", "VendorOrganisation"]
