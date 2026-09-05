"""Run regression tests in an exclusively owned, disposable MySQL schema.

Set ITSM_TEST_ADMIN_URL to a local MySQL URL with CREATE/DROP DATABASE rights.
An existing test schema is never overwritten. Application data is not touched.
"""

import os
import sys
from pathlib import Path

import pymysql
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
TEST_SCHEMA = "service_desk_member_a_test"


def sql_statements(source):
    """Read the canonical SQL's mysql-client DELIMITER directives."""
    delimiter = ";"
    buffer = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped.upper().startswith("DELIMITER "):
            if buffer:
                raise ValueError("Unexpected pending SQL before DELIMITER")
            delimiter = stripped.split()[1]
            continue
        buffer.append(line)
        if stripped.endswith(delimiter):
            yield "\n".join(buffer).rstrip()[: -len(delimiter)]
            buffer = []
    if buffer:
        raise ValueError("Unterminated canonical SQL statement")


def main():
    url = make_url(os.environ["ITSM_TEST_ADMIN_URL"])
    if url.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("This disposable test runner only accepts local MySQL")
    connection = pymysql.connect(
        host=url.host,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        autocommit=True,
        connect_timeout=5,
        charset="utf8mb4",
    )
    owned = False
    try:
        with connection.cursor() as cursor:
            # No IF NOT EXISTS: fail if another run already owns this schema.
            cursor.execute(
                f"CREATE DATABASE `{TEST_SCHEMA}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            owned = True
            canonical = (BACKEND / "database/schema.sql").read_text(encoding="utf-8")
            for statement in sql_statements(canonical.replace("service_desk", TEST_SCHEMA)):
                cursor.execute(statement)
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s",
                (TEST_SCHEMA,),
            )
            assert cursor.fetchone()[0] == 19
            print("Canonical MySQL schema initialized: 19 tables.", flush=True)
        os.environ["DATABASE_URL"] = url.set(
            drivername="mysql+pymysql", database=TEST_SCHEMA
        ).render_as_string(hide_password=False)
        os.environ["RUN_MYSQL_INTEGRATION"] = "1"
        os.environ["JWT_SECRET"] = "local-integration-only-secret-at-least-32-bytes"
        os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
        sys.path.insert(0, str(BACKEND))
        os.chdir(BACKEND)
        import pytest

        return pytest.main(["-q", "-rs", "tests"])
    finally:
        if owned:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{TEST_SCHEMA}`")
            print("Disposable MySQL test schema removed.", flush=True)
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
