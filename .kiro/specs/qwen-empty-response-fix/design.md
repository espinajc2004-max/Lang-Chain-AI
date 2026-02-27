# Qwen Empty Response Fix — Bugfix Design

## Overview

Qwen3:4b returns empty string responses (`""`) when prompts containing the `/no_think` directive exceed ~200 characters. This breaks the entire 3-stage pipeline (Intent Extraction → SQL Generation → Response Formatting) because all three prompt builders in `prompts.py` prepend `/no_think` and produce prompts well above that threshold. The fix removes `/no_think` from all prompts, allowing Qwen3 to use its chain-of-thought reasoning internally, then strips the `<think>...</think>` blocks from the raw response before the existing JSON/SQL extraction logic runs. The `data_lookup.py` standalone tool is also affected and requires the same treatment.

## Glossary

- **Bug_Condition (C)**: A prompt sent to Qwen3:4b that contains the `/no_think` directive AND exceeds ~200 characters in length, causing an empty response
- **Property (P)**: The model returns a non-empty, parseable response (JSON for Stage 1, SQL for Stage 2, natural language for Stage 3) regardless of prompt length
- **Preservation**: The 3-stage pipeline sequence, out-of-scope handling, clarification flow, read-only SQL enforcement, JSON/SQL extraction logic, and FastAPI/terminal chat calling patterns must remain unchanged
- **`build_stage1_prompt()`**: Function in `prompts.py` that constructs the intent extraction prompt with `/no_think`
- **`build_stage2_prompt()`**: Function in `prompts.py` that constructs the SQL generation prompt with `/no_think` and full schema
- **`build_stage3_prompt()`**: Function in `prompts.py` that constructs the response formatting prompt with `/no_think`
- **`build_prompt()`**: Function in `data_lookup.py` that constructs the CSV data lookup prompt with `/no_think`
- **`ask_qwen()`**: Function in both `chat.py` and `main.py` that sends a prompt to Ollama and returns the raw response string
- **`<think>...</think>` block**: Qwen3's chain-of-thought reasoning output that wraps internal reasoning when `/no_think` is NOT used

## Bug Details

### Fault Condition

The bug manifests when any prompt containing the `/no_think` directive exceeds approximately 200 characters. The Qwen3:4b model silently returns an empty string instead of generating structured output. All three pipeline stages produce prompts well above this threshold (Stage 1: ~613 chars, Stage 2: ~1827 chars, Stage 3: variable but typically >200 chars with result data). The `data_lookup.py` tool is similarly affected when the CSV data preview makes the prompt long.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type PromptRequest { prompt: string, model: string }
  OUTPUT: boolean

  RETURN input.prompt STARTS_WITH "/no_think"
         AND LENGTH(input.prompt) > ~200
         AND input.model == "qwen3:4b"
END FUNCTION
```

### Examples

- **Stage 1 (Intent Extraction)**: User asks "show me the list of expenses file we have" → `build_stage1_prompt()` produces a ~613 char prompt starting with `/no_think` → Qwen3:4b returns `""` → `extract_json()` raises `ValueError: No JSON found in response` → pipeline fails
- **Stage 2 (SQL Generation)**: Intent is parsed (if Stage 1 somehow succeeds) → `build_stage2_prompt()` produces a ~1827 char prompt with full schema starting with `/no_think` → Qwen3:4b returns `""` → `extract_sql()` returns empty string → SQL execution fails
- **Stage 3 (Response Formatting)**: Query results are available → `build_stage3_prompt()` produces a prompt starting with `/no_think` that exceeds 200 chars when result data is included → Qwen3:4b returns `""` → user sees blank answer
- **Data Lookup Tool**: User asks a question about CSV data → `build_prompt()` in `data_lookup.py` produces a prompt with `/no_think` plus data preview → Qwen3:4b returns `""` for any non-trivial dataset
- **Short prompt (no bug)**: A prompt like `/no_think\nReturn this JSON: {"name":"test"}\nJSON:` (~60 chars) works fine and returns valid JSON — the bug only triggers above the ~200 char threshold

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The 3-stage pipeline sequence (Intent Extraction → SQL Generation → Response Formatting) must continue to execute in order
- Out-of-scope questions must still return an `out_of_scope_message` via Stage 1 intent classification
- Vague questions must still return a `clarification_question` via Stage 1 intent classification
- SQL enforcement must remain read-only (SELECT only, forbidden operations rejected)
- `extract_json()` and `extract_sql()` parsing functions must continue to work on the actual content (JSON/SQL) within responses
- FastAPI `/api/query` endpoint and terminal `chat.py` must continue using the same `ask_qwen()` calling pattern
- The `ask_qwen_stream()` function in `chat.py` must continue to stream tokens for Stage 3
- Prompt structure and instructions (schema, table lists, output format directives) must remain semantically equivalent

**Scope:**
All inputs that do NOT involve the `/no_think` directive interaction are completely unaffected. The fix changes only:
- How prompts are constructed (removing `/no_think` prefix)
- How raw responses are post-processed (stripping `<think>` blocks before extraction)

No changes to SQL execution, database connectivity, API routing, request/response models, or conversation history management.

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **`/no_think` Directive Incompatibility with Long Prompts on 4B Model**: The `/no_think` directive tells Qwen3 to skip its internal chain-of-thought reasoning. The smaller 4B parameter model lacks the capacity to produce structured output (JSON, SQL) for complex prompts without that reasoning step. When the prompt is short/simple enough, the model can handle it without thinking. Beyond ~200 chars, the model needs its reasoning chain to process the instructions and produce output, but `/no_think` prevents this, resulting in an empty generation.

2. **All Prompt Builders Prepend `/no_think`**: Every prompt function (`build_stage1_prompt`, `build_stage2_prompt`, `build_stage3_prompt` in `prompts.py`, and `build_prompt` in `data_lookup.py`) starts with `/no_think\n`. This means every pipeline stage is affected once prompts exceed the threshold.

3. **No Response Validation or Fallback**: The `ask_qwen()` functions in both `chat.py` and `main.py` return the raw response with only `.strip()`. There is no check for empty responses, no retry logic, and no handling of `<think>` blocks that would appear if `/no_think` were removed.

4. **No `<think>` Block Stripping**: The existing `extract_json()` and `extract_sql()` functions search for JSON/SQL patterns in the response text. If `/no_think` is removed and Qwen3 produces `<think>reasoning here</think>\n{"intent_type":...}`, the extraction functions would still work for JSON (since `re.search` finds the `{...}` pattern), but the `<think>` content could interfere with SQL extraction or produce unexpected matches. A dedicated stripping step is needed for reliability.

## Correctness Properties

Property 1: Fault Condition - Non-Empty Responses for All Prompt Lengths

_For any_ prompt sent to Qwen3:4b through the pipeline (Stage 1, Stage 2, Stage 3, or data lookup) where the prompt exceeds 200 characters, the fixed system SHALL return a non-empty, parseable response containing the expected structured output (JSON for Stage 1, SQL for Stage 2, natural language for Stage 3).

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - Pipeline Behavior for Valid Queries

_For any_ input that exercises the existing pipeline logic (out-of-scope detection, clarification requests, SQL enforcement, JSON/SQL extraction, API routing), the fixed code SHALL produce the same behavioral outcomes as the original code, preserving all existing functionality for query processing, security enforcement, and response formatting.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `prompts.py`

**Functions**: `build_stage1_prompt()`, `build_stage2_prompt()`, `build_stage3_prompt()`

**Specific Changes**:
1. **Remove `/no_think` directive**: Delete the `/no_think\n` prefix from all three prompt builder return strings. The prompt content and instructions remain identical otherwise.

**File**: `data_lookup.py`

**Function**: `build_prompt()`

**Specific Changes**:
2. **Remove `/no_think` directive**: Delete the `/no_think\n` prefix from the data lookup prompt builder.

**File**: `chat.py`

**Functions**: `ask_qwen()`, `ask_qwen_stream()`

**Specific Changes**:
3. **Add `<think>` block stripping**: After receiving the raw response from Ollama, strip any `<think>...</think>` block (including the tags and content between them) before returning the text. Use a regex like `re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)` to handle multi-line thinking blocks.

**File**: `main.py`

**Function**: `ask_qwen()`

**Specific Changes**:
4. **Add `<think>` block stripping**: Same `<think>` stripping logic as in `chat.py` — strip thinking blocks from the raw response before returning.

**File**: `data_lookup.py`

**Function**: `query_qwen()`

**Specific Changes**:
5. **Add `<think>` block stripping**: Strip `<think>` blocks from the accumulated full response before returning. For the streaming case, accumulate the full response first, then strip before returning (the streamed output to terminal may include thinking tokens, but the returned string used for further processing will be clean).

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code (empty responses for long prompts with `/no_think`), then verify the fix works correctly (non-empty responses without `/no_think`, with `<think>` blocks stripped) and preserves existing behavior (pipeline sequence, extraction logic, security enforcement).

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that `/no_think` + long prompts = empty responses on Qwen3:4b.

**Test Plan**: Use the existing `debug_qwen.py` pattern to send prompts of varying lengths with and without `/no_think` to Qwen3:4b. Observe which combinations produce empty responses.

**Test Cases**:
1. **Stage 1 Full Prompt Test**: Send `build_stage1_prompt("show me expenses")` with `/no_think` — expect empty response (will fail on unfixed code)
2. **Stage 2 Full Prompt Test**: Send `build_stage2_prompt("show expenses", intent)` with `/no_think` — expect empty response (will fail on unfixed code)
3. **Stage 3 Long Data Test**: Send `build_stage3_prompt("show expenses", large_data_json, 50)` with `/no_think` — expect empty response (will fail on unfixed code)
4. **Short Prompt Control**: Send a short prompt (<100 chars) with `/no_think` — expect valid response (confirms threshold behavior)

**Expected Counterexamples**:
- All prompts >200 chars with `/no_think` return empty string `""`
- Possible root cause confirmed: Qwen3:4b cannot generate structured output without chain-of-thought for complex prompts

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (long prompts that previously had `/no_think`), the fixed functions produce non-empty, parseable responses.

**Pseudocode:**
```
FOR ALL prompt WHERE isBugCondition(prompt) DO
  result := ask_qwen_fixed(prompt_without_no_think)
  cleaned := strip_think_blocks(result)
  ASSERT LENGTH(cleaned) > 0
  ASSERT is_parseable(cleaned, expected_format)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (pipeline logic, extraction, security), the fixed code produces the same result as the original code.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT pipeline_behavior_fixed(input) == pipeline_behavior_original(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It can generate many prompt variations to verify `<think>` stripping doesn't corrupt valid content
- It catches edge cases in regex stripping (nested tags, partial tags, no tags present)
- It provides strong guarantees that extraction functions work identically on cleaned responses

**Test Plan**: Observe behavior on UNFIXED code first for extraction functions and pipeline flow, then write tests capturing that behavior continues after the fix.

**Test Cases**:
1. **JSON Extraction Preservation**: Verify `extract_json()` works on responses both with and without `<think>` blocks — the JSON content must be extracted identically
2. **SQL Extraction Preservation**: Verify `extract_sql()` works on responses both with and without `<think>` blocks — the SQL content must be extracted identically
3. **Out-of-Scope Handling Preservation**: Verify out-of-scope questions still produce `out_of_scope_message` in the intent response
4. **SQL Security Preservation**: Verify read-only enforcement still rejects forbidden operations

### Unit Tests

- Test `<think>` block stripping with various formats: `<think>text</think>`, multi-line thinking, empty thinking blocks, no thinking blocks present, multiple thinking blocks
- Test that `extract_json()` correctly parses JSON from responses that had `<think>` blocks stripped
- Test that `extract_sql()` correctly parses SQL from responses that had `<think>` blocks stripped
- Test prompt builders no longer include `/no_think` in output

### Property-Based Tests

- Generate random strings and verify `strip_think_blocks()` is idempotent (stripping twice = stripping once)
- Generate random JSON objects wrapped in `<think>...</think>` prefixes and verify `extract_json()` still finds the JSON after stripping
- Generate random SQL SELECT statements wrapped in `<think>...</think>` prefixes and verify `extract_sql()` still finds the SQL after stripping
- Generate responses with no `<think>` blocks and verify stripping produces identical output

### Integration Tests

- Test full Stage 1 → Stage 2 → Stage 3 pipeline with a real question against Qwen3:4b (without `/no_think`) and verify non-empty responses at each stage
- Test `data_lookup.py` with a CSV file and verify non-empty response
- Test FastAPI `/api/query` endpoint end-to-end and verify `QueryResponse` has non-empty `answer` field
