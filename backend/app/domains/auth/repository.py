"""Persistence operations used by registration and login."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.users.model import User


class AuthRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def get_by_email(self, email: str) -> User | None:
        return self.database.execute(select(User).where(User.email == email)).scalar_one_or_none()

    def add(self, user: User) -> User:
        self.database.add(user)
        self.database.flush()
        self.database.refresh(user)
        return user
