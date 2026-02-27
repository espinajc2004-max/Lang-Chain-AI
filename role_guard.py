"""
Role-based access guard for AU-Ggregates AI backend.

Code-level enforcement that does NOT rely on LLM prompts.
Three layers of protection:
1. Table whitelist per role (SQLDatabase include_tables)
2. SQL query validator (blocks forbidden table references)
3. Role validation (rejects unknown roles at the API level)
"""

import re

# ---------------------------------------------------------------------------
# Role → allowed tables mapping (single source of truth)
# ---------------------------------------------------------------------------

ROLE_TABLES: dict[str, list[str]] = {
    "ADMIN": [
        "Project", "Trip", "TruckDetails", "Expenses", "CashFlow",
        "product_category", "product", "Quotation", "QuotationItem",
        "ExpensesTableTemplate", "ExpensesColumn", "ExpensesCellValue",
        "CashFlowCustomTable", "CashFlowColumn", "CashFlowCellValue",
        "Billing",
    ],
    "ENCODER": [
        "Project", "Expenses", "ExpensesTableTemplate", "ExpensesColumn",
        "ExpensesCellValue", "Quotation", "QuotationItem", "Trip",
        "TruckDetails", "product", "product_category",
    ],
    "ACCOUNTANT": [
        "Project", "Expenses", "ExpensesTableTemplate", "ExpensesColumn",
        "ExpensesCellValue", "CashFlow", "CashFlowCustomTable",
        "CashFlowColumn", "CashFlowCellValue", "Quotation",
        "QuotationItem", "Billing",
    ],
}

VALID_ROLES = set(ROLE_TABLES.keys())

# All known tables in the system (union of all roles)
ALL_TABLES = sorted(set(t for tables in ROLE_TABLES.values() for t in tables))


# ---------------------------------------------------------------------------
# Role validation
# ---------------------------------------------------------------------------

def validate_role(role: str) -> str:
    """Validate and normalize a role string.

    Returns the uppercase role if valid.
    Raises ValueError if the role is not allowed.
    """
    normalized = role.strip().upper()
    if normalized not in VALID_ROLES:
        raise ValueError(
            f"Role '{role}' is not authorized. "
            f"Allowed roles: {', '.join(sorted(VALID_ROLES))}"
        )
    return normalized


def get_tables_for_role(role: str) -> list[str]:
    """Return the list of allowed tables for a given role."""
    return ROLE_TABLES[validate_role(role)]


def get_blocked_tables_for_role(role: str) -> set[str]:
    """Return the set of tables a role is NOT allowed to access."""
    allowed = set(get_tables_for_role(role))
    return set(ALL_TABLES) - allowed


# ---------------------------------------------------------------------------
# SQL query validator
# ---------------------------------------------------------------------------

# Dangerous SQL operations that should never be allowed
_WRITE_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def validate_sql_query(sql: str, role: str) -> tuple[bool, str]:
    """Validate a SQL query against role-based restrictions.

    Returns (is_valid, error_message).
    If is_valid is True, error_message is empty.

    Checks:
    1. No write operations (INSERT, UPDATE, DELETE, DROP, etc.)
    2. No references to tables the role cannot access
    """
    # Block write operations
    write_match = _WRITE_PATTERN.search(sql)
    if write_match:
        return False, f"Write operation '{write_match.group()}' is not allowed. Only SELECT queries are permitted."

    # Check for blocked table references
    blocked = get_blocked_tables_for_role(role)
    if not blocked:
        return True, ""  # ADMIN has no blocked tables

    # Check both quoted and unquoted table references
    for table in blocked:
        # Match "TableName" (quoted) or FROM/JOIN TableName (unquoted)
        patterns = [
            rf'"{re.escape(table)}"',  # "TableName"
            rf'\b{re.escape(table)}\b',  # TableName (unquoted)
        ]
        for pattern in patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                return False, f"Access denied: role '{role}' cannot query table '{table}'."

    return True, ""


# ---------------------------------------------------------------------------
# Friendly denial messages per role
# ---------------------------------------------------------------------------

DENIAL_MESSAGES: dict[str, dict[str, str]] = {
    "ENCODER": {
        "CashFlow": "Cash flow data is managed by the Accountant. Please contact your accountant for cash flow information.",
        "CashFlowCustomTable": "Cash flow data is managed by the Accountant.",
        "CashFlowColumn": "Cash flow data is managed by the Accountant.",
        "CashFlowCellValue": "Cash flow data is managed by the Accountant.",
        "Billing": "Billing records are managed by the Accountant. Please contact your accountant for billing information.",
    },
    "ACCOUNTANT": {
        "Trip": "Trip management is handled by the Dispatcher. Please contact your dispatcher for trip information.",
        "TruckDetails": "Fleet management is handled by the Dispatcher and Admin.",
        "product": "Product management is handled by the Admin.",
        "product_category": "Product categories are managed by the Admin.",
    },
}


def get_denial_message(role: str, table: str) -> str:
    """Get a user-friendly denial message for a blocked table access."""
    role = validate_role(role)
    role_denials = DENIAL_MESSAGES.get(role, {})
    return role_denials.get(
        table,
        f"You don't have access to '{table}' data with your current role ({role})."
    )
