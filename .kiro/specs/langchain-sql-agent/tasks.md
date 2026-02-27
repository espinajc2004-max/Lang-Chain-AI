# Implementation Plan: LangChain SQL Agent

## Overview

Convert the AU-Ggregates AI Data Lookup from a manual 3-stage Ollama HTTP pipeline to a LangChain SQL agent. The implementation proceeds bottom-up: dependencies first, then the core agent module, then rewiring both entry points, then cleanup of legacy code.

## Tasks

- [ ] 1. Update dependencies and environment configuration
  - [x] 1.1 Add LangChain dependencies to the project
    - Install `langchain`, `langchain-community`, `langchain-ollama`, and `sqlalchemy` packages
    - Ensure existing dependencies (`fastapi`, `psycopg2-binary`, `python-dotenv`, `uvicorn`) are retained
    - Create or update `requirements.txt` with all required packages
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 1.2 Update `.env` with `OLLAMA_BASE_URL`
    - Add `OLLAMA_BASE_URL=http://localhost:11434` to `.env`
    - Keep existing `DATABASE_URL` and `OLLAMA_MODEL` variables
    - _Requirements: 2.1, 2.2_

- [ ] 2. Implement core agent module (`agent.py`)
  - [x] 2.1 Create `agent.py` with system prompt and table list constants
    - Define `SYSTEM_PROMPT` constant with Querymancer-style personality: AU-Ggregates Data Assistant identity, ₱XX,XXX.XX monetary formatting, English/Taglish input with English output, Markdown response formatting, double-quoted PostgreSQL identifiers, ILIKE for case-insensitive search, LIMIT 100, current date injection, and SELECT-only enforcement
    - Define `INCLUDE_TABLES` list with all 14 tables (Project, Trip, TruckDetails, Expenses, CashFlow, product_category, product, Quotation, QuotationItem, ExpensesTableTemplate, ExpensesColumn, ExpensesCellValue, CashFlowCustomTable, CashFlowColumn, CashFlowCellValue)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 3.2, 9.4_
  - [x] 2.2 Implement `create_agent_executor()` function
    - Create `ChatOllama` instance: read `OLLAMA_BASE_URL` (fallback: strip `/api/generate` from `OLLAMA_URL`), read `OLLAMA_MODEL` (default `qwen3:4b`), set temperature=0.1, set reasoning=True for think block handling
    - Create `SQLDatabase.from_uri()` using `DATABASE_URL`, pass `include_tables=INCLUDE_TABLES`
    - Create `SQLDatabaseToolkit` with the db and llm instances
    - Create ReAct agent via `create_react_agent` with the LLM, toolkit tools, and system prompt
    - Wrap in `AgentExecutor` with handle_parsing_errors=True, max_iterations=10
    - Raise descriptive `ConnectionError` if Ollama is unreachable
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.3, 9.1, 9.2, 9.3_
  - [x] 2.3 Implement `invoke_agent()` function
    - Accept `agent_executor`, `question` string, and optional `conversation_history` (list of dicts)
    - Convert conversation history (last 5 entries) to `HumanMessage`/`AIMessage` objects
    - Append current question as final `HumanMessage`
    - Invoke the agent executor and return the text response
    - _Requirements: 1.5, 1.6, 7.1, 7.2, 7.3, 7.4_
  - [ ]* 2.4 Write unit tests for `agent.py`
    - Test `OLLAMA_BASE_URL` fallback logic (strips `/api/generate` from `OLLAMA_URL`)
    - Test conversation history conversion to LangChain messages (truncation to last 5)
    - Test that `invoke_agent` passes history correctly
    - _Requirements: 1.5, 2.1, 7.3_

- [x] 3. Checkpoint - Verify agent module
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Simplify FastAPI server (`main.py`)
  - [x] 4.1 Rewrite `main.py` to use the agent module
    - Import `create_agent_executor` and `invoke_agent` from `agent.py`
    - Initialize agent executor at module level
    - Simplify `QueryRequest` to `question: str` and `conversation_history: list[dict] = []`
    - Simplify `QueryResponse` to `question: str` and `answer: str` (remove `intent`, `sql`, `data` fields)
    - Rewrite `POST /api/query` to validate question, call `invoke_agent`, return response
    - Return HTTP 400 for empty question, HTTP 500 with descriptive message for agent errors
    - Keep CORS middleware allowing all origins/methods/headers
    - Update `GET /health` to return status and model name from env
    - Remove all pipeline functions: `ask_qwen`, `extract_json`, `extract_sql`, `execute_query`, `strip_think_blocks`, `format_history`
    - Remove `requests`, `psycopg2`, `json`, `re` imports that are no longer needed
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.2, 8.4, 8.5_
  - [ ]* 4.2 Write unit tests for simplified `main.py`
    - Test POST `/api/query` returns 400 for empty question
    - Test POST `/api/query` returns question and answer in response
    - Test GET `/health` returns status and model name
    - _Requirements: 5.4, 5.7_

- [ ] 5. Simplify terminal chat (`chat.py`)
  - [x] 5.1 Rewrite `chat.py` to use the agent module
    - Import `create_agent_executor` and `invoke_agent` from `agent.py`
    - Initialize agent executor in `main()`
    - Implement interactive prompt loop: read input, call `invoke_agent`, print response
    - Maintain session-level `conversation_history` list, append after each exchange, trim to last 5
    - Handle exit commands: "quit", "exit", "q"
    - Catch `ConnectionError` and display message to start Ollama
    - Catch database errors and continue accepting questions
    - Remove all pipeline functions: `ask_qwen`, `ask_qwen_stream`, `extract_json`, `extract_sql`, `execute_query`, `strip_think_blocks`, `format_history`, `print_table`, `process_question`
    - Remove `requests`, `psycopg2`, `json`, `re` imports that are no longer needed
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.3, 8.4, 8.5_

- [ ] 6. Remove legacy pipeline files
  - [x] 6.1 Delete `prompts.py`
    - Remove the file entirely; its functionality is replaced by `SYSTEM_PROMPT` in `agent.py`
    - _Requirements: 8.1_
  - [x] 6.2 Delete `data_lookup.py`
    - Remove the CSV-based lookup tool; not part of the SQL agent architecture
    - _Requirements: 8.1_
  - [x] 6.3 Remove `requests` from dependencies
    - Update `requirements.txt` to remove `requests` since direct Ollama HTTP calls are eliminated
    - _Requirements: 10.6, 8.4_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirement clauses for traceability
- The implementation language is Python, matching the existing codebase and design document
- Checkpoints ensure incremental validation between major phases
