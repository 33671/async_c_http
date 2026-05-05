# AGENT.md — Project Progress Summary

## Project: cop

An **async AI coding agent in C** using **libmill** coroutines, **libcurl** in
`mfork()`-ed child processes, **SQLite** history, and **isocline** terminal UI.

---

## Component Status

| Component | Files | Status | Description |
|---|---|---|---|
| **SSE Parser** | `openai_sse_parser.h/.c` | ✅ Stable | SSE event extraction, JSON validation, chunk parsing |
| **Tool Call Parser** | `tool_call_parser.h/.c` | ✅ Stable | Streaming tool_call delta fragment accumulation |
| **Stream Client** | `openai_stream_client.h/.c` | ✅ Stable | Async streaming via mfork child + curl + pipe. Dynamic request body builder. Runtime model/api switching |
| **LLM Parser** | `llm_parser.h/.c` | ✅ Stable | Multi-turn state machine. `force_finish()` for cancellation cleanup. Always emits valid `content` field |
| **LLM Runtime** | `llm_runtime.h/.c` | ✅ Stable | Orchestration: stream + parser + tool execution + cancellation + `llm_runtime_popen()` |
| **Tool Functions** | `tool_functions.h/.c` | ✅ Stable | shell, read, write, edit, sleep. User approval via isocline |
| **History DB** | `history_db.h/.c` | ✅ Stable | SQLite session/message storage. CWD-scoped. Lazy session creation. `/delete all` |
| **Models Config** | `models_config.h/.c` | ✅ Stable | Parse `~/.cop/models.json`. Model lookup by id |
| **Terminal UI** | `cop_ui.h/.c` | ✅ Stable | REPL loop, tab completion, streaming output formatting, command handlers |
| **Main Entry** | `cop.c` | ✅ Stable | 120-line main(): config, runtime, tools, launch REPL |
| **Legacy Test** | `llm_runtime_test.c` | ⚠️ Legacy | Still builds but deprecated in favor of cop |

---

## Architecture

```
cop.c (main entry, 120 lines)
  ├── models_config  → ~/.cop/models.json
  ├── history_db     → ~/.cop/history.sql (~/.cop/ dir)
  ├── llm_runtime
  │     ├── openai_stream_client (mfork + curl + pipe)
  │     │     └── openai_sse_parser
  │     └── llm_parser
  │           └── tool_call_parser
  ├── tool_functions (shell / read / write / edit / sleep)
  └── cop_ui (isocline REPL, completion, streaming display)
        └── isocline (multiline input, history, tab completion, bbcode colors)
```

### Data Flow

```
User input → cop_ui_repl() → llm_runtime_send()
  → stream_client_start_chat() [mfork child → curl → pipe]
  → next_chunk() [fdwait on pipe → SSE parse]
  → llm_parser_feed_chunk() → on_runtime_event() [cop_ui streaming display]
  → execute_tool_calls() → tool_fn() [user approval via isocline]
  → loop if tools called
  → save_history_step() → history_db [SQLite append]
```

---

## Cancellation Architecture

- `g_rt->running` is the single source of truth
- `cop_ui_sigint()` → `llm_runtime_cancel()` → `running = 0`
- Checks at every phase:
  - Before stream start → return
  - Mid-stream → kill child (SIGKILL), `force_finish()` parser
  - During tool execution → remaining tools get cancelled result
- `force_finish()` **always sets a valid `content` field** (empty string, null, or actual text) to prevent API 400 errors

---

## Key Debug History

### Bug 1: `fdwait` FDW_ERR / FDW_IN ordering (FIXED)
First turn worked; second turn skipped finish_reason. Root cause: FDW_ERR checked before FDW_IN drain. Fix: drain FDW_IN first, only break on pure FDW_ERR.

### Bug 2: `llm_runtime_popen` always returns -1 (FIXED)
Short-lived commands returned FDW_ERR-only on pipe close. Fix: try `read()` one more time on FDW_ERR-only to catch EOF.

### Bug 3: `force_finish()` missing `content` field (FIXED)
After Ctrl+C during reasoning-only stream, the finalized message had no `content` key. API rejected with "content or tool_calls must be set". Fix: always set content to `""` when no text and no tool calls.

### `end` macro conflict with libmill (FIXED)
`end` is a macro in libmill.h. Using it as a variable name causes catastrophic compile errors. Renamed all `end` variables to `e`.

### isocline `~` path not expanded (FIXED)
`ic_set_history("~/.cop/.history")` — isocline doesn't expand `~`. Fixed by building absolute path with `$HOME`.

### isocline tab completion: `ic_complete_word` strips `/` (FIXED)
Default word boundary treats `/` as separator, stripping it from `/mo` → `mo`. Fixed with custom `slash_is_word_char` that treats only whitespace as separator.

---

## Dependencies

| Library | Path | Purpose |
|---|---|---|
| **libmill** | `libmill/` | Coroutines / async I/O |
| **libcurl** | system | HTTP client |
| **cjson** | `cjson/` | JSON parsing |
| **isocline** | `isocline/` | Terminal input, history, completion, bbcode colors |
| **sqlite3** | `sqlite/` | Amalgamation: conversation history persistence |
