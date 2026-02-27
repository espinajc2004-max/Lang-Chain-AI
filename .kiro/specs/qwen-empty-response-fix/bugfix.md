# Bugfix Requirements Document

## Introduction

The AU-Ggregates AI Data Lookup app uses Qwen3:4b via Ollama's `/api/generate` endpoint with a 3-stage pipeline (Intent Extraction → SQL Generation → Response Formatting). All three stages use the `/no_think` directive in their prompts (defined in `prompts.py`). Qwen3:4b returns empty string responses (`""`) for any prompt longer than ~200 characters when `/no_think` is present, which completely breaks the pipeline. Short/simple prompts with `/no_think` work fine. The root cause is that the `/no_think` directive suppresses Qwen3's internal chain-of-thought reasoning, and the smaller 4B model cannot produce structured output (JSON, SQL) for complex prompts without that reasoning step.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a Stage 1 intent extraction prompt is sent to Qwen3:4b with the `/no_think` directive (prompt ~613 chars including schema references, table lists, intent types, and filter keys) THEN the system receives an empty string response from the model, causing intent parsing to fail

1.2 WHEN a Stage 2 SQL generation prompt is sent to Qwen3:4b with the `/no_think` directive (prompt ~1827 chars including the full database schema) THEN the system receives an empty string response from the model, causing SQL extraction to fail

1.3 WHEN a Stage 3 response formatting prompt is sent to Qwen3:4b with the `/no_think` directive and the prompt exceeds ~200 characters (due to large result data) THEN the system receives an empty string response from the model, causing the final answer to be blank

1.4 WHEN any prompt containing `/no_think` exceeds approximately 200 characters in length THEN the system receives an empty string response from Qwen3:4b, regardless of the prompt's purpose or content structure

### Expected Behavior (Correct)

2.1 WHEN a Stage 1 intent extraction prompt is sent to the model THEN the system SHALL receive a valid JSON response containing `intent_type`, `source_table`, `filters`, and `needs_clarification` fields

2.2 WHEN a Stage 2 SQL generation prompt is sent to the model with the full database schema THEN the system SHALL receive a valid SQL SELECT statement as a response

2.3 WHEN a Stage 3 response formatting prompt is sent to the model with query results THEN the system SHALL receive a natural language answer summarizing the data

2.4 WHEN any pipeline stage prompt is sent to the model THEN the system SHALL receive a non-empty response regardless of prompt length or complexity

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user asks a valid data query question THEN the system SHALL CONTINUE TO execute the 3-stage pipeline (Intent Extraction → SQL Generation → Response Formatting) in sequence and return a natural language answer

3.2 WHEN a user asks an out-of-scope question THEN the system SHALL CONTINUE TO return an appropriate out-of-scope message via the intent extraction stage

3.3 WHEN a user asks a vague question that needs clarification THEN the system SHALL CONTINUE TO return a clarification question via the intent extraction stage

3.4 WHEN the model generates a SQL query THEN the system SHALL CONTINUE TO enforce read-only access (SELECT only) and reject forbidden operations (INSERT, UPDATE, DELETE, DROP, etc.)

3.5 WHEN the pipeline is used via the FastAPI endpoint (`/api/query`) or the terminal chat (`chat.py`) THEN the system SHALL CONTINUE TO use the same prompt-building functions from `prompts.py` and the same `ask_qwen()` calling pattern

3.6 WHEN the model returns a response THEN the system SHALL CONTINUE TO extract JSON (for Stage 1) and SQL (for Stage 2) using the existing `extract_json()` and `extract_sql()` parsing functions
