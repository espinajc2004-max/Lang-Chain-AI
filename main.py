"""
FastAPI AI Data Lookup — AU-Ggregates
LangChain SQL Agent Architecture
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import create_agent_executor, invoke_agent
from role_guard import VALID_ROLES

load_dotenv()

app = FastAPI(title="AU-Ggregates AI Data Lookup", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create one agent executor per role at startup
agent_executors: dict = {}

for _role in sorted(VALID_ROLES):
    print(f"\n🔧 Initializing agent for {_role}...")
    agent_executors[_role] = create_agent_executor(role=_role)

print("\n✅ All role-based agents ready\n")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str
    role: str = "ADMIN"
    conversation_history: list[dict] = []


class QueryMetadata(BaseModel):
    query_count: int = 0
    total_time_ms: float = 0
    total_rows: int = 0
    tables_queried: list[str] = []
    blocked_count: int = 0
    total_response_time_ms: float = 0


class ClarificationResponse(BaseModel):
    clarification: str
    options: list[str]


class QueryResponse(BaseModel):
    question: str
    answer: str
    role: str
    metadata: QueryMetadata
    suggestions: list[str] = []
    clarification: ClarificationResponse | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/query", response_model=QueryResponse)
async def query_data(req: QueryRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Question cannot be empty")

    role = req.role.upper()
    if role not in VALID_ROLES:
        raise HTTPException(403, f"Role '{req.role}' is not authorized to use the AI assistant")

    try:
        executor = agent_executors[role]
        result = invoke_agent(executor, question, req.conversation_history, role)
    except Exception as exc:
        raise HTTPException(500, f"Agent error: {exc}")

    return QueryResponse(
        question=question,
        answer=result["answer"],
        role=role,
        metadata=QueryMetadata(**result["metadata"]),
        suggestions=result["suggestions"],
        clarification=ClarificationResponse(**result["clarification"]) if result["clarification"] else None,
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": os.getenv("GROQ_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:4b")),
        "roles": sorted(VALID_ROLES),
    }
