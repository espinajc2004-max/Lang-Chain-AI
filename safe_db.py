"""
SafeSQLDatabase — query-level access control wrapper.

Wraps LangChain's SQLDatabase to intercept and validate every SQL query
before execution. This is the HARD enforcement layer that works at code
level, independent of LLM prompts.

Even if the LLM ignores prompt instructions and tries to query a
restricted table, SafeSQLDatabase will block it.
"""

import os
import re
import time

from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase

from role_guard import validate_role, validate_sql_query, get_tables_for_role

load_dotenv()


class QueryMetadata:
    """Tracks metadata about queries executed during an agent invocation."""

    def __init__(self):
        self.queries: list[dict] = []
        self.total_time_ms: float = 0
        self.total_rows: int = 0
        self.tables_queried: set[str] = set()
        self.blocked_count: int = 0

    def record(self, sql: str, duration_ms: float, row_count: int, tables: set[str], blocked: bool = False):
        self.queries.append({
            "sql_preview": sql[:100] + "..." if len(sql) > 100 else sql,
            "duration_ms": round(duration_ms, 1),
            "row_count": row_count,
            "blocked": blocked,
        })
        self.total_time_ms += duration_ms
        self.total_rows += row_count
        self.tables_queried.update(tables)
        if blocked:
            self.blocked_count += 1

    def to_dict(self) -> dict:
        return {
            "query_count": len(self.queries),
            "total_time_ms": round(self.total_time_ms, 1),
            "total_rows": self.total_rows,
            "tables_queried": sorted(self.tables_queried),
            "blocked_count": self.blocked_count,
        }

    def reset(self):
        self.queries.clear()
        self.total_time_ms = 0
        self.total_rows = 0
        self.tables_queried.clear()
        self.blocked_count = 0


# Regex to extract table names from SQL (matches "TableName" or FROM/JOIN TableName)
_TABLE_PATTERN = re.compile(r'(?:FROM|JOIN)\s+"?(\w+)"?', re.IGNORECASE)


class SafeSQLDatabase:
    """Role-restricted wrapper around SQLDatabase.

    Layer 1: The underlying SQLDatabase is created with include_tables,
             so the toolkit can't even see restricted tables.
    Layer 2: This wrapper validates every query at runtime via
             validate_sql_query() before it hits the database.

    The wrapper monkey-patches the underlying SQLDatabase.run method
    so that SQLDatabaseToolkit (which requires a real SQLDatabase instance)
    still routes all queries through the safety layer.
    """

    def __init__(self, db: SQLDatabase, role: str):
        self._db = db
        self._role = validate_role(role)
        self.metadata = QueryMetadata()

        # Monkey-patch the underlying db.run so the toolkit's tools
        # go through our safety layer automatically
        self._original_run = db.run
        db.run = self._safe_run

    def _safe_run(self, command: str, fetch: str = "all", **kwargs):
        """Intercept SQL execution, validate, track metadata, then run."""
        is_valid, error_msg = validate_sql_query(command, self._role)

        # Extract table names from the query
        tables = set(_TABLE_PATTERN.findall(command))

        if not is_valid:
            self.metadata.record(command, 0, 0, tables, blocked=True)
            return f"BLOCKED: {error_msg}"

        start = time.perf_counter()
        result = self._original_run(command, fetch=fetch, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000

        # Estimate row count from result
        row_count = 0
        if isinstance(result, str):
            # LangChain returns results as string; count newlines as rough row estimate
            row_count = max(0, result.count("\n"))
        elif isinstance(result, list):
            row_count = len(result)

        self.metadata.record(command, duration_ms, row_count, tables)
        return result

    # Expose the underlying SQLDatabase for toolkit compatibility
    @property
    def db(self) -> SQLDatabase:
        return self._db


def create_safe_db(role: str) -> SafeSQLDatabase:
    """Create a role-restricted database connection.

    Args:
        role: User role (ADMIN, ENCODER, ACCOUNTANT).

    Returns:
        SafeSQLDatabase instance that only allows access to
        tables permitted for the given role.

    Raises:
        ValueError: If DATABASE_URL is not set or role is invalid.
    """
    role = validate_role(role)
    include_tables = get_tables_for_role(role)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set.")

    print(f"  ⏳ Connecting to database (role: {role}, {len(include_tables)} tables)...")

    # Layer 1: SQLDatabase only sees allowed tables
    raw_db = SQLDatabase.from_uri(database_url, include_tables=include_tables)

    # Layer 2: SafeSQLDatabase validates every query at runtime
    safe_db = SafeSQLDatabase(raw_db, role)

    print(f"  ✅ Database connected for {role}")
    return safe_db
