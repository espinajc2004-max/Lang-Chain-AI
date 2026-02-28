"""
AU-Ggregates AI — Agent orchestrator.

Thin module that wires together:
- llm.py         → LLM provider (Groq / Ollama)
- safe_db.py     → Role-restricted database access + query metadata
- prompts.py     → System prompts per role
- role_guard.py  → Role validation and table mappings
- suggestions.py → Follow-up suggestions and clarification detection

Both main.py (FastAPI) and chat.py (CLI) import from here.
"""

import json
import re
import time

from pydantic import BaseModel, validator

from langchain.agents import create_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_core.messages import AIMessage, HumanMessage

from llm import create_llm
from prompts import build_system_prompt
from role_guard import validate_role
from safe_db import create_safe_db, SafeSQLDatabase
from suggestions import generate_suggestions, detect_clarification


class ChartData(BaseModel):
    type: str  # "bar" or "pie"
    labels: list[str]
    values: list[float]

    @validator("labels")
    def validate_labels(cls, v):
        if not v:
            raise ValueError("labels must be non-empty")
        return v

    @validator("values")
    def validate_lengths(cls, v, values):
        if not v:
            raise ValueError("values must be non-empty")
        if "labels" in values and len(v) != len(values["labels"]):
            raise ValueError("labels and values must have the same length")
        return v

    @validator("type")
    def validate_type(cls, v):
        if v not in ("bar", "pie"):
            raise ValueError("type must be 'bar' or 'pie'")
        return v


class TableData(BaseModel):
    headers: list[str]
    rows: list[list[str]]

    @validator("headers")
    def validate_headers(cls, v):
        if not v:
            raise ValueError("headers must be non-empty")
        return v

    @validator("rows")
    def validate_rows(cls, v, values):
        if "headers" in values:
            expected_len = len(values["headers"])
            for i, row in enumerate(v):
                if len(row) != expected_len:
                    raise ValueError(
                        f"Row {i} length {len(row)} != headers length {expected_len}"
                    )
        return v


def _fix_json_quotes(s: str) -> str:
    """Convert single-quoted JSON to double-quoted JSON.

    LLMs sometimes output {'key': 'value'} instead of {"key": "value"}.
    This does a best-effort conversion so json.loads() can parse it.
    """
    # Replace single quotes around keys and string values with double quotes
    # Step 1: replace single-quoted strings, being careful with apostrophes
    result = re.sub(r"'([^']*)'", r'"\1"', s)
    return result


# Broad pattern: find JSON-like blocks that contain chart/table keys
CHART_DATA_PATTERN = re.compile(
    r'\{[^{}]*["\']type["\'][^{}]*["\']labels["\'][^{}]*["\']values["\'][^{}]*\}',
    re.DOTALL,
)
# Also match if keys are in different order
CHART_DATA_PATTERN_ALT = re.compile(
    r'\{[^{}]*["\'](?:type|labels|values)["\'].*?["\'](?:type|labels|values)["\'].*?["\'](?:type|labels|values)["\'].*?\}',
    re.DOTALL,
)
TABLE_DATA_PATTERN = re.compile(
    r'\{[^{}]*["\']headers["\'][^{}]*["\']rows["\'].*?\}',
    re.DOTALL,
)
TABLE_DATA_PATTERN_ALT = re.compile(
    r'\{[^{}]*["\']rows["\'][^{}]*["\']headers["\'].*?\}',
    re.DOTALL,
)

# Also look for labeled blocks like **chart_data**: {...} or chart_data: {...}
LABELED_CHART_PATTERN = re.compile(
    r'\*{0,2}chart_data\*{0,2}\s*:\s*(\{.*?\})',
    re.DOTALL,
)
LABELED_TABLE_PATTERN = re.compile(
    r'\*{0,2}table_data\*{0,2}\s*:\s*(\{.*?\})',
    re.DOTALL,
)


def _try_parse_json(raw_str: str) -> dict | None:
    """Try to parse a JSON string, fixing single quotes if needed."""
    try:
        return json.loads(raw_str)
    except json.JSONDecodeError:
        try:
            return json.loads(_fix_json_quotes(raw_str))
        except json.JSONDecodeError:
            return None


def extract_chart_data(text: str) -> tuple[ChartData | None, str]:
    """Extract and validate chart_data from LLM response text.

    Handles both single and double quoted JSON, labeled blocks like
    **chart_data**: {...}, and keys in any order.

    Returns (ChartData or None, cleaned text with JSON block removed).
    """
    # Try labeled pattern first (e.g., **chart_data**: {...})
    for pattern in [LABELED_CHART_PATTERN]:
        match = pattern.search(text)
        if match:
            raw = _try_parse_json(match.group(1))
            if raw and "type" in raw and "labels" in raw and "values" in raw:
                try:
                    chart = ChartData(**raw)
                    cleaned = text[: match.start()] + text[match.end() :]
                    return chart, cleaned.strip()
                except (ValueError, TypeError):
                    pass

    # Try unlabeled patterns
    for pattern in [CHART_DATA_PATTERN, CHART_DATA_PATTERN_ALT]:
        match = pattern.search(text)
        if match:
            raw = _try_parse_json(match.group())
            if raw and "type" in raw and "labels" in raw and "values" in raw:
                try:
                    chart = ChartData(**raw)
                    cleaned = text[: match.start()] + text[match.end() :]
                    return chart, cleaned.strip()
                except (ValueError, TypeError):
                    pass

    return None, text


def extract_table_data(text: str) -> tuple[TableData | None, str]:
    """Extract and validate table_data from LLM response text.

    Handles both single and double quoted JSON, labeled blocks, and
    keys in any order.

    Returns (TableData or None, cleaned text with JSON block removed).
    """
    # Try labeled pattern first
    for pattern in [LABELED_TABLE_PATTERN]:
        match = pattern.search(text)
        if match:
            raw = _try_parse_json(match.group(1))
            if raw and "headers" in raw and "rows" in raw:
                try:
                    table = TableData(**raw)
                    cleaned = text[: match.start()] + text[match.end() :]
                    return table, cleaned.strip()
                except (ValueError, TypeError):
                    pass

    # Try unlabeled patterns
    for pattern in [TABLE_DATA_PATTERN, TABLE_DATA_PATTERN_ALT]:
        match = pattern.search(text)
        if match:
            raw = _try_parse_json(match.group())
            if raw and "headers" in raw and "rows" in raw:
                try:
                    table = TableData(**raw)
                    cleaned = text[: match.start()] + text[match.end() :]
                    return table, cleaned.strip()
                except (ValueError, TypeError):
                    pass

    return None, text


class AgentExecutor:
    """Wraps the LangChain agent with its associated SafeSQLDatabase.

    This lets us access query metadata after invocation.
    """

    def __init__(self, agent, safe_db: SafeSQLDatabase, role: str):
        self.agent = agent
        self.safe_db = safe_db
        self.role = role

    def invoke(self, inputs: dict) -> dict:
        return self.agent.invoke(inputs)


def create_agent_executor(role: str = "ADMIN") -> AgentExecutor:
    """Create a role-restricted LangChain SQL agent.

    Access control is enforced at code level:
    1. SQLDatabase only sees tables for this role (include_tables)
    2. SafeSQLDatabase validates every query before execution
    3. System prompt guides the LLM (soft layer)

    Args:
        role: User role (ADMIN, ENCODER, ACCOUNTANT).

    Returns:
        AgentExecutor wrapping the compiled agent graph.
    """
    role = validate_role(role)

    llm = create_llm()
    safe_db = create_safe_db(role)

    # Pass the raw SQLDatabase to the toolkit (Pydantic requires the exact type).
    # SafeSQLDatabase has already monkey-patched db.run with the safety layer.
    toolkit = SQLDatabaseToolkit(db=safe_db.db, llm=llm)
    tools = toolkit.get_tools()

    system_prompt = build_system_prompt(role)

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )

    return AgentExecutor(agent, safe_db, role)


def invoke_agent(
    executor: AgentExecutor,
    question: str,
    conversation_history: list[dict] | None = None,
    role: str = "ADMIN",
) -> dict:
    """Invoke the agent and return answer with metadata and suggestions.

    Args:
        executor: AgentExecutor from create_agent_executor().
        question: The user's current question.
        conversation_history: Optional list of {"question": str, "answer": str}.
            Only the last 5 entries are used.
        role: The user's role.

    Returns:
        Dict with keys:
        - answer: The agent's text response
        - metadata: Query stats (time, row count, tables queried)
        - suggestions: Follow-up question suggestions
        - clarification: Clarification prompt if question is ambiguous (or None)
    """
    role = validate_role(role)

    # Check if the question needs clarification first
    clarification = detect_clarification(question, role)
    if clarification:
        return {
            "answer": clarification["clarification"],
            "metadata": {"query_count": 0, "total_time_ms": 0, "total_rows": 0, "tables_queried": [], "blocked_count": 0},
            "suggestions": clarification["options"],
            "clarification": clarification,
            "chart_data": None,
            "table_data": None,
        }

    # Reset metadata tracking for this invocation
    executor.safe_db.metadata.reset()

    # Build message history
    messages: list = []
    if conversation_history:
        for entry in conversation_history[-5:]:
            messages.append(HumanMessage(content=entry["question"]))
            messages.append(AIMessage(content=entry["answer"]))
    messages.append(HumanMessage(content=question))

    # Invoke with timing
    start = time.perf_counter()

    answer = ""
    for attempt in range(2):
        try:
            # Reset metadata each attempt so we can detect tool usage
            executor.safe_db.metadata.reset()

            result = executor.invoke({"messages": messages})
            answer = result["messages"][-1].content

            # HALLUCINATION GUARD: If the model responded without calling any
            # SQL tool (query_count == 0), it likely fabricated data.
            # Retry once with a stronger nudge to use tools.
            meta_check = executor.safe_db.metadata.to_dict()
            if attempt == 0 and meta_check["query_count"] == 0:
                print(f"  ⚠ [{role}] No SQL tool called — possible hallucination, retrying with nudge...")
                messages.append(AIMessage(content=answer))
                messages.append(HumanMessage(
                    content="You did NOT query the database. You MUST use the sql_db_query tool "
                            "to search for the answer. Do NOT make up data. Execute a SQL query now."
                ))
                continue

            break
        except Exception as exc:
            exc_str = str(exc).lower()
            # Handle rate limit errors gracefully
            if "rate_limit" in exc_str or "429" in exc_str or "rate limit" in exc_str:
                print(f"  ⚠ [{role}] Rate limit hit — returning friendly message")
                answer = ("I'm temporarily unable to process your request due to API rate limits. "
                          "Please wait a few minutes and try again.")
                break
            if attempt == 0 and "incomplete" in exc_str:
                print(f"  ⚠ [{role}] Connection dropped, retrying...")
                continue
            raise

    total_time_ms = (time.perf_counter() - start) * 1000

    # Collect metadata
    meta = executor.safe_db.metadata.to_dict()
    meta["total_response_time_ms"] = round(total_time_ms, 1)

    # Final hallucination check: if still no queries after retry, return safe message
    if meta["query_count"] == 0:
        print(f"  ❌ [{role}] No SQL queries executed after retry — returning safe fallback")
        answer = ("I wasn't able to retrieve data from the database for your query. "
                  "Could you try rephrasing your question? For example: "
                  "'show all expenses for [project name]' or 'list all projects'.")

    # Generate follow-up suggestions
    suggestions = generate_suggestions(
        question=question,
        tables_queried=set(meta.get("tables_queried", [])),
        role=role,
    )

    # Extract visualization data from answer
    chart_data, answer = extract_chart_data(answer)
    table_data, answer = extract_table_data(answer)

    return {
        "answer": answer,
        "metadata": meta,
        "suggestions": suggestions,
        "clarification": None,
        "chart_data": chart_data,
        "table_data": table_data,
    }
