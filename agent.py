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


CHART_DATA_PATTERN = re.compile(
    r'\{[^{}]*"type"\s*:\s*"(?:bar|pie)"[^{}]*"labels"\s*:\s*\[.*?\][^{}]*"values"\s*:\s*\[.*?\][^{}]*\}',
    re.DOTALL,
)
TABLE_DATA_PATTERN = re.compile(
    r'\{[^{}]*"headers"\s*:\s*\[.*?\][^{}]*"rows"\s*:\s*\[.*?\][^{}]*\}',
    re.DOTALL,
)


def extract_chart_data(text: str) -> tuple[ChartData | None, str]:
    """Extract and validate chart_data from LLM response text.

    Returns (ChartData or None, cleaned text with JSON block removed).
    On malformed JSON or validation failure, returns (None, original text).
    """
    match = CHART_DATA_PATTERN.search(text)
    if not match:
        return None, text
    try:
        raw = json.loads(match.group())
        chart = ChartData(**raw)
        cleaned = text[: match.start()] + text[match.end() :]
        return chart, cleaned.strip()
    except (json.JSONDecodeError, ValueError):
        return None, text


def extract_table_data(text: str) -> tuple[TableData | None, str]:
    """Extract and validate table_data from LLM response text.

    Returns (TableData or None, cleaned text with JSON block removed).
    On malformed JSON or validation failure, returns (None, original text).
    """
    match = TABLE_DATA_PATTERN.search(text)
    if not match:
        return None, text
    try:
        raw = json.loads(match.group())
        table = TableData(**raw)
        cleaned = text[: match.start()] + text[match.end() :]
        return table, cleaned.strip()
    except (json.JSONDecodeError, ValueError):
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

    toolkit = SQLDatabaseToolkit(db=safe_db, llm=llm)
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

    for attempt in range(2):
        try:
            result = executor.invoke({"messages": messages})
            answer = result["messages"][-1].content
            break
        except Exception as exc:
            if attempt == 0 and "incomplete" in str(exc).lower():
                print(f"  ⚠ [{role}] Connection dropped, retrying...")
                continue
            raise

    total_time_ms = (time.perf_counter() - start) * 1000

    # Collect metadata
    meta = executor.safe_db.metadata.to_dict()
    meta["total_response_time_ms"] = round(total_time_ms, 1)

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
