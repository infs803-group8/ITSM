"""Comment persistence and visibility-filtered queries."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.comments.model import Comment


class CommentRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def list(
        self,
        *,
        ticket_id: int,
        page: int,
        page_size: int,
        visibility: str | None,
        user_visible_only: bool,
    ) -> tuple[Sequence[Mapping[str, Any]], int]:
        filters = ["c.ticket_id = :ticket_id"]
        params: dict[str, Any] = {
            "ticket_id": ticket_id,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if user_visible_only:
            filters.append("c.visibility = 'USER_VISIBLE'")
        elif visibility is not None:
            filters.append("c.visibility = :visibility")
            params["visibility"] = visibility
        where = " AND ".join(filters)
        total = int(
            self.database.execute(
                text(f"SELECT COUNT(*) FROM comments c WHERE {where}"), params
            ).scalar_one()
        )
        rows = self.database.execute(
            text(
                "SELECT c.comment_id, c.ticket_id, c.message, c.visibility, c.created_at, "
                "u.user_id AS author_id, u.display_name AS author_name, u.role_code AS author_role "
                "FROM comments c JOIN users u ON u.user_id=c.author_id "
                f"WHERE {where} ORDER BY c.created_at, c.comment_id "
                "LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings().all()
        return rows, total

    def create(
        self, *, ticket_id: int, author_id: int, message: str, visibility: str
    ) -> Comment:
        comment = Comment(
            ticket_id=ticket_id,
            author_id=author_id,
            message=message,
            visibility=visibility,
            comment_type="ORDINARY",
        )
        self.database.add(comment)
        self.database.flush()
        return comment

    def add_event(self, comment: Comment) -> None:
        self.database.execute(
            text(
                "INSERT INTO ticket_events "
                "(ticket_id, event_type, scope, actor_id, comment_id, metadata) "
                "VALUES (:ticket_id, 'COMMENT_ADDED', :scope, :actor_id, :comment_id, "
                "JSON_OBJECT('comment_id', :comment_id))"
            ),
            {
                "ticket_id": comment.ticket_id,
                "scope": comment.visibility,
                "actor_id": comment.author_id,
                "comment_id": comment.comment_id,
            },
        )

    def view(self, comment_id: int) -> Mapping[str, Any]:
        return self.database.execute(
            text(
                "SELECT c.comment_id, c.ticket_id, c.message, c.visibility, c.created_at, "
                "u.user_id AS author_id, u.display_name AS author_name, u.role_code AS author_role "
                "FROM comments c JOIN users u ON u.user_id=c.author_id "
                "WHERE c.comment_id=:comment_id"
            ),
            {"comment_id": comment_id},
        ).mappings().one()
