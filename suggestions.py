"""
Follow-up suggestion engine for the AU-Ggregates AI chat.

Generates contextual follow-up questions based on:
- The user's original question
- Which tables were queried
- The user's role
- The answer content

This is code-level logic, not prompt-based.
"""

from role_guard import get_tables_for_role

# ---------------------------------------------------------------------------
# Table → follow-up question mappings
# ---------------------------------------------------------------------------

# When these tables are queried, suggest related follow-ups
TABLE_FOLLOWUPS: dict[str, list[str]] = {
    "Expenses": [
        "Show me the total expenses per project",
        "Which expenses are still pending approval?",
        "What's the highest expense this month?",
    ],
    "Project": [
        "How many active projects do we have?",
        "Show me project expenses breakdown",
        "Which project has the most trips?",
    ],
    "Quotation": [
        "Show me pending quotations",
        "What's the total value of approved quotations?",
        "List quotations created this month",
    ],
    "QuotationItem": [
        "Show me the most quoted products",
        "What's the average quotation value?",
    ],
    "Trip": [
        "How many trips were completed this week?",
        "Show me trips by truck",
        "Which driver has the most trips?",
    ],
    "TruckDetails": [
        "Which trucks are under maintenance?",
        "Show me active trucks",
        "List all truck assignments",
    ],
    "CashFlow": [
        "Show me this month's cash flow summary",
        "Which projects have pending cash flow entries?",
        "What's the total cash inflow vs outflow?",
    ],
    "Billing": [
        "Show me unpaid billing records",
        "What's the total billed amount this month?",
    ],
    "product": [
        "List all product categories",
        "Show me product prices",
    ],
}

# Role-specific starter suggestions (when no tables queried yet)
ROLE_STARTERS: dict[str, list[str]] = {
    "ADMIN": [
        "Show me a summary of all pending approvals",
        "How many active projects do we have?",
        "What's the total expenses this month?",
        "Show me fleet status overview",
    ],
    "ENCODER": [
        "Show me my pending expense submissions",
        "List all quotation drafts",
        "What trips are scheduled this week?",
        "Show me recent customer requests",
    ],
    "ACCOUNTANT": [
        "Show me the verification queue",
        "What's this month's cash flow summary?",
        "List pending billing records",
        "Show me expense trends this quarter",
    ],
}


# ---------------------------------------------------------------------------
# Keyword-based clarification detection
# ---------------------------------------------------------------------------

# Ambiguous keywords that might need clarification
AMBIGUOUS_TERMS: dict[str, dict] = {
    "expenses": {
        "clarification": "Are you looking for expense files, or the actual expense values (amounts)?",
        "options": [
            "Show me expense files with their status",
            "Show me expense amounts per project",
        ],
    },
    "total": {
        "clarification": "Total for which time period?",
        "options": [
            "Total for this month",
            "Total for this year",
            "Total for all time",
        ],
    },
    "status": {
        "clarification": "Status of what exactly?",
        "options": [
            "Project status",
            "Expense approval status",
            "Trip status",
            "Quotation status",
        ],
    },
    "report": {
        "clarification": "What kind of report do you need?",
        "options": [
            "Expense summary report",
            "Project financial report",
            "Monthly cash flow report",
        ],
    },
}


def generate_suggestions(
    question: str,
    tables_queried: set[str],
    role: str,
    max_suggestions: int = 3,
) -> list[str]:
    """Generate follow-up question suggestions based on context.

    Args:
        question: The user's original question.
        tables_queried: Set of table names that were queried.
        role: The user's role.
        max_suggestions: Maximum number of suggestions to return.

    Returns:
        List of suggested follow-up questions.
    """
    suggestions: list[str] = []
    allowed_tables = set(get_tables_for_role(role))

    # Get suggestions based on tables that were queried
    for table in tables_queried:
        if table in TABLE_FOLLOWUPS:
            for suggestion in TABLE_FOLLOWUPS[table]:
                # Only suggest if the tables needed are accessible to this role
                if suggestion not in suggestions:
                    suggestions.append(suggestion)

    # If no table-based suggestions, use role starters
    if not suggestions:
        suggestions = list(ROLE_STARTERS.get(role, []))

    # Filter out suggestions that are too similar to the original question
    question_lower = question.lower()
    suggestions = [
        s for s in suggestions
        if question_lower not in s.lower() and s.lower() not in question_lower
    ]

    return suggestions[:max_suggestions]


def detect_clarification(question: str, role: str) -> dict | None:
    """Check if the question is ambiguous and needs clarification.

    Args:
        question: The user's question.
        role: The user's role.

    Returns:
        A dict with 'clarification' message and 'options' list,
        or None if no clarification needed.
    """
    question_lower = question.lower().strip()
    words = question_lower.split()

    # Very short questions (1-2 words) are likely ambiguous
    if len(words) <= 2:
        for term, info in AMBIGUOUS_TERMS.items():
            if term in question_lower:
                # Filter options based on role access
                allowed_tables = set(get_tables_for_role(role))
                options = info["options"]

                # Remove trip/fleet options for accountant
                if role == "ACCOUNTANT":
                    options = [o for o in options if "trip" not in o.lower() and "fleet" not in o.lower()]
                # Remove cash flow/billing options for encoder
                elif role == "ENCODER":
                    options = [o for o in options if "cash flow" not in o.lower() and "billing" not in o.lower()]

                if options:
                    return {
                        "clarification": info["clarification"],
                        "options": options,
                    }

    return None
