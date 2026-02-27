# Requirements Document

## Introduction

The AU-Ggregates AI Data Lookup project currently uses a manual 3-stage Ollama HTTP pipeline (Intent Extraction → SQL Generation → Response Formatting) to answer natural language questions against a Supabase PostgreSQL database. This feature replaces that pipeline with a LangChain SQL agent architecture using `SQLDatabaseToolkit` and a ReAct agent, connected to the same Qwen3:4b model via `ChatOllama`. The conversion simplifies the codebase by eliminating custom prompt engineering stages while gaining automatic schema introspection, SQL validation, and error-recovery capabilities provided by LangChain's SQL agent toolkit.

## Glossary

- **SQL_Agent**: The LangChain ReAct agent created via `create_react_agent` (or equivalent `create_sql_agent`) that autonomously decides which SQL tools to invoke to answer a user question
- **ChatOllama**: The LangChain LLM wrapper (`langchain_ollama.ChatOllama`) that connects to a local Ollama instance running Qwen3:4b
- **SQLDatabase**: The LangChain database wrapper (`langchain_community.utilities.SQLDatabase`) that connects to Supabase PostgreSQL via SQLAlchemy and provides schema introspection
- **SQLDatabaseToolkit**: The LangChain toolkit (`langchain_community.agent_toolkits.SQLDatabaseToolkit`) that bundles SQL tools (list tables, get schema, query, query checker) for the agent
- **FastAPI_Server**: The FastAPI application in `main.py` that exposes the `/api/query` HTTP endpoint
- **Terminal_Chat**: The interactive terminal interface in `chat.py` for asking questions via the command line
- **Agent_Module**: The new shared Python module that encapsulates SQL_Agent creation and invocation, used by both FastAPI_Server and Terminal_Chat
- **System_Prompt**: The Querymancer-style personality prompt that instructs the SQL_Agent on response formatting, language handling, and domain context
- **Think_Block**: The `<think>...</think>` reasoning block that Qwen3 emits before its final answer
- **Conversation_History**: The list of previous user questions and agent answers maintained per session to support follow-up questions
- **Pipeline**: The current 3-stage architecture (Intent Extraction, SQL Generation, Response Formatting) in `main.py`, `chat.py`, and `prompts.py` that the SQL_Agent replaces

## Requirements

### Requirement 1: LangChain SQL Agent Core Module

**User Story:** As a developer, I want a shared agent module that encapsulates the LangChain SQL agent setup, so that both the FastAPI server and terminal chat can use the same agent logic without duplication.

#### Acceptance Criteria

1. THE Agent_Module SHALL create a SQLDatabase instance connected to Supabase PostgreSQL using the `DATABASE_URL` environment variable via `SQLDatabase.from_uri()`
2. THE Agent_Module SHALL create a ChatOllama instance configured to use the Qwen3:4b model on the local Ollama server specified by environment variables
3. THE Agent_Module SHALL create a SQLDatabaseToolkit instance using the SQLDatabase and ChatOllama instances
4. THE Agent_Module SHALL create a SQL_Agent using LangChain's agent creation function with the tools from SQLDatabaseToolkit
5. THE Agent_Module SHALL expose a function that accepts a user question string and optional Conversation_History and returns the agent's text response
6. THE Agent_Module SHALL be importable by both FastAPI_Server and Terminal_Chat without requiring separate agent initialization logic in each entry point

### Requirement 2: ChatOllama Configuration with Qwen3 Think Block Handling

**User Story:** As a developer, I want ChatOllama properly configured for Qwen3:4b including think block handling, so that the agent receives clean responses without reasoning artifacts.

#### Acceptance Criteria

1. THE ChatOllama instance SHALL connect to the Ollama server URL specified by the `OLLAMA_URL` environment variable
2. THE ChatOllama instance SHALL use the model name specified by the `OLLAMA_MODEL` environment variable, defaulting to `qwen3:4b`
3. THE ChatOllama instance SHALL set the temperature to a low value suitable for SQL generation tasks
4. WHEN Qwen3 emits Think_Block content in its response, THE ChatOllama instance SHALL handle Think_Block filtering so that only the final answer reaches the SQL_Agent (using the `reasoning` parameter or equivalent configuration)
5. IF the Ollama server is unreachable, THEN THE Agent_Module SHALL raise a descriptive connection error indicating that Ollama is not running

### Requirement 3: Read-Only SQL Enforcement

**User Story:** As a system administrator, I want the SQL agent restricted to read-only queries, so that the database cannot be modified through the AI interface.

#### Acceptance Criteria

1. THE SQL_Agent SHALL only execute SELECT statements against the database
2. THE System_Prompt SHALL instruct the SQL_Agent to generate only SELECT queries and to refuse any data modification requests
3. THE SQLDatabase connection SHALL be configured with read-only access where supported by the connection method
4. IF a user asks the SQL_Agent to modify, insert, update, or delete data, THEN THE SQL_Agent SHALL decline the request and explain that only read operations are supported

### Requirement 4: Querymancer-Style System Prompt

**User Story:** As a product owner, I want the SQL agent to maintain the AU-Ggregates Data Assistant personality, so that users get a consistent experience with domain-aware, well-formatted responses.

#### Acceptance Criteria

1. THE System_Prompt SHALL identify the SQL_Agent as "AU-Ggregates Data Assistant" with expertise in PostgreSQL query construction
2. THE System_Prompt SHALL instruct the SQL_Agent to format monetary values as ₱XX,XXX.XX
3. THE System_Prompt SHALL instruct the SQL_Agent to accept questions in English or Taglish and always respond in English
4. THE System_Prompt SHALL instruct the SQL_Agent to format responses as Markdown, preferring tables or lists for data display
5. THE System_Prompt SHALL instruct the SQL_Agent to double-quote all PostgreSQL table and column names in generated queries
6. THE System_Prompt SHALL instruct the SQL_Agent to use ILIKE for case-insensitive text searches
7. THE System_Prompt SHALL instruct the SQL_Agent to add LIMIT 100 to queries to prevent excessive results
8. THE System_Prompt SHALL include the current date for time-relative queries

### Requirement 5: FastAPI Endpoint Integration

**User Story:** As a frontend developer, I want the `/api/query` endpoint to use the new LangChain SQL agent, so that the API continues to serve AI-powered data lookups without breaking the existing contract.

#### Acceptance Criteria

1. THE FastAPI_Server SHALL expose a POST `/api/query` endpoint that accepts a JSON body with a `question` string field and an optional `conversation_history` list field
2. WHEN a valid question is received, THE FastAPI_Server SHALL invoke the SQL_Agent via the Agent_Module and return the agent's response
3. THE FastAPI_Server SHALL return a JSON response containing at minimum the original `question` and the agent's `answer` text
4. IF the question field is empty, THEN THE FastAPI_Server SHALL return an HTTP 400 error with a descriptive message
5. IF the SQL_Agent encounters an error during processing, THEN THE FastAPI_Server SHALL return an appropriate HTTP error status with a descriptive message
6. THE FastAPI_Server SHALL maintain CORS middleware allowing all origins, methods, and headers
7. THE FastAPI_Server SHALL expose a GET `/health` endpoint that returns the service status and configured model name

### Requirement 6: Terminal Chat Integration

**User Story:** As a developer, I want the terminal chat interface to use the new LangChain SQL agent, so that I can interactively query the database from the command line with the same agent capabilities.

#### Acceptance Criteria

1. THE Terminal_Chat SHALL present an interactive prompt loop that accepts user questions and displays agent responses
2. WHEN a user enters a question, THE Terminal_Chat SHALL invoke the SQL_Agent via the Agent_Module and display the response
3. THE Terminal_Chat SHALL maintain Conversation_History across questions within the same session for follow-up support
4. WHEN the user types "quit", "exit", or "q", THE Terminal_Chat SHALL terminate the session gracefully
5. IF the Ollama server is unreachable, THEN THE Terminal_Chat SHALL display a message instructing the user to start Ollama
6. IF a database error occurs, THEN THE Terminal_Chat SHALL display the error and continue accepting new questions

### Requirement 7: Conversation History Support

**User Story:** As a user, I want the agent to remember previous questions in my session, so that I can ask follow-up questions without repeating context.

#### Acceptance Criteria

1. THE Agent_Module SHALL accept Conversation_History as input when invoking the SQL_Agent
2. THE Agent_Module SHALL pass Conversation_History to the SQL_Agent so that previous exchanges inform the current response
3. THE Conversation_History SHALL store the last 5 question-answer pairs per session to provide context without exceeding token limits
4. WHEN a follow-up question references a previous query (e.g., "what about last month?"), THE SQL_Agent SHALL use Conversation_History to resolve the reference

### Requirement 8: Elimination of Manual Pipeline Code

**User Story:** As a developer, I want the manual 3-stage pipeline code removed, so that the codebase is simplified and all query logic flows through the LangChain SQL agent.

#### Acceptance Criteria

1. THE Agent_Module SHALL replace the functionality previously provided by the `build_stage1_prompt`, `build_stage2_prompt`, and `build_stage3_prompt` functions in `prompts.py`
2. THE FastAPI_Server SHALL remove the `ask_qwen`, `extract_json`, `extract_sql`, and `execute_query` helper functions that implemented the manual Pipeline
3. THE Terminal_Chat SHALL remove the `ask_qwen`, `ask_qwen_stream`, `extract_json`, `extract_sql`, and `execute_query` helper functions that implemented the manual Pipeline
4. THE Agent_Module SHALL remove the dependency on the `requests` library for direct Ollama HTTP calls, relying on ChatOllama instead
5. THE `strip_think_blocks` function SHALL be removed from both FastAPI_Server and Terminal_Chat since Think_Block handling is managed by ChatOllama

### Requirement 9: Database Schema Awareness

**User Story:** As a user, I want the SQL agent to automatically understand the database schema, so that it generates accurate queries without hardcoded schema definitions in prompts.

#### Acceptance Criteria

1. THE SQLDatabase instance SHALL introspect the Supabase PostgreSQL schema to discover available tables and their columns automatically
2. THE SQLDatabaseToolkit SHALL provide the SQL_Agent with tools to list tables, read table schemas, execute queries, and check query correctness
3. WHEN the SQL_Agent needs schema information, THE SQL_Agent SHALL use the toolkit's schema introspection tools rather than relying on a hardcoded schema string
4. THE SQLDatabase instance SHALL be configured to include the relevant tables (Project, Trip, TruckDetails, Expenses, CashFlow, product_category, product, Quotation, QuotationItem, ExpensesTableTemplate, ExpensesColumn, ExpensesCellValue, CashFlowCustomTable, CashFlowColumn, CashFlowCellValue) via the `include_tables` parameter

### Requirement 10: Dependency Management

**User Story:** As a developer, I want the project dependencies updated to include LangChain packages, so that the new agent architecture has all required libraries available.

#### Acceptance Criteria

1. THE project SHALL include `langchain` as a dependency
2. THE project SHALL include `langchain-community` as a dependency for SQLDatabaseToolkit and SQLDatabase
3. THE project SHALL include `langchain-ollama` as a dependency for ChatOllama
4. THE project SHALL include `sqlalchemy` as a dependency for database connectivity used by SQLDatabase
5. THE project SHALL retain existing dependencies: `fastapi`, `psycopg2` (or `psycopg2-binary`), `python-dotenv`, and `uvicorn`
6. THE project SHALL remove `requests` from required dependencies since direct Ollama HTTP calls are no longer needed
