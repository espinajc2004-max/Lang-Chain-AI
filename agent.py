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

import time

from langchain.agents import create_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_core.messages import AIMessage, HumanMessage

from llm import create_llm
from prompts import build_system_prompt
from role_guard import validate_role
from safe_db import create_safe_db, SafeSQLDatabase
from suggestions import generate_suggestions, detect_clarification


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

    return {
        "answer": answer,
        "metadata": meta,
        "suggestions": suggestions,
        "clarification": None,
    }
