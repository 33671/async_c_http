# AGENT.md - Project Progress Summary

## Project: async_c_http

An **async HTTP SSE (Server-Sent Events) client in C** for streaming OpenAI-compatible API responses, using **libmill** coroutines and **libcurl** threads.

---

## Architecture

```
                        Main Thread (libmill)
  ┌─────────────────┐     ┌─────────────────┐
  │  SSE Coroutine  │     │  SSE Coroutine  │    ...
  │  fdwait(pipe)   │     │  fdwait(pipe)   │
  └────────┬────────┘     └────────┬────────┘
           │                       │
           └───────────────────────┘
                       │
              ┌────────┴────────┐
              │    Pipe (fd)    │
              │  [read]←[write] │
              └────────┬────────┘
                       │
  ┌────────────────────┼────────────────────┐
  │    Curl Thread     │    Curl Thread     │
  │ curl_easy_perform()│ curl_easy_perform()│
  └────────────────────┘────────────────────┘
                       │
                       ▼
                 HTTP Server
```

- **libcurl** runs in dedicated thread(s) for blocking HTTP I/O
- **pipe** transfers data from curl thread to libmill coroutine
- **fdwait()** enables async waiting on pipe in libmill's event loop

---

## Component Status

| Component | Files | Status | Description |
|---|---|---|---|
| **SSE Parser** | `openai_sse_parser.h/.c` | ✅ Stable | SSE event extraction, JSON validation, chunk parsing (content, reasoning, tool_calls, usage) |
| **Tool Call Parser** | `tool_call_parser.h/.c` | ✅ Stable | Streaming tool_call delta fragment accumulation |
| **Stream Client** | `openai_stream_client.h/.c` | ✅ Stable | Async streaming client (libmill + libcurl + pipe). Dynamic request body builder with tool schema support |
| **LLM Parser** | `llm_parser.h/.c` | ✅ Stable | Multi-turn conversation state machine. `force_finish()` for cancellation cleanup |
| **LLM Runtime** | `llm_runtime.h/.c` | ✅ Stable | High-level orchestration: wraps stream_client + llm_parser + tool execution + cancellation |
| **Runtime Test** | `llm_runtime_test.c` | ✅ Stable | Interactive REPL with isocline multiline input, tool demo, streaming callbacks |
| **Old Test** | `openai_stream_client_async_test.c` | ⚠️ Legacy | Still works but deprecated |
| **Utils** | `utils.c/.h` | ✅ Done | .env file loader |
| **Test Server** | `test_server.py` | ✅ Done | Python aiohttp SSE test server |
| **isocline** | `isocline/` | ✅ Integrated | Terminal input: multiline, history, BBCode colors |
| **hl-vt100** | `hl-vt100/` | ❌ Not used | Available for future rich terminal rendering |

---

## Detailed Breakdown

### 1. SSE Parser (`openai_sse_parser.h/.c`)
- `stream_buffer_t` — Ring-buffer for accumulating raw SSE data
- `StreamChunk` — Parsed struct: `content`, `reasoning_content`, `tool_calls`, `role`, `finish_reason`, `usage`
- `extract_next_chunk()` — Main parsing entry point

### 2. Tool Call Parser (`tool_call_parser.h/.c`)
- `ToolCallDeltaParser` — Up to 256 parallel tool call slots by index
- `feed_toolcall_delta()` — Accumulates incremental fragments across chunks
- Produces complete `cJSON` array on stream end

### 3. Stream Client (`openai_stream_client.h/.c`)
- `stream_client_new/free()` — Lifecycle
- `stream_client_start_chat(client, messages)` — Accepts cJSON messages array, builds full request body internally
- `build_request_body()` — Static helper using cJSON API. Includes: model, messages, temperature, stream=true, tool schemas (if set)
- `stream_client_set_tool_schemas()` — Set tool definition JSON array (deep-copied, included in every subsequent request)
- `next_chunk()` / `next_chunk_nowait()` — Coroutine-based async chunk iteration
- `stream_client_cancel()` — Sets running=0, curl checks via xfer callback

### 4. LLM Parser (`llm_parser.h/.c`)
- State machine: `IDLE → IN_ASSISTANT → FINISHED`
- Status reporting: `REASONING`, `RESPONDING`, `WRITING_TOOL_CALL`, `FINISHED`
- `llm_parser_force_finish()` — On cancellation: finalizes partial content/reasoning, discards incomplete tool calls, keeps history valid

### 5. LLM Runtime (`llm_runtime.h/.c`)
High-level orchestration layer:

| API | Description |
|---|---|
| `llm_runtime_new/free()` | Lifecycle |
| `llm_runtime_send()` | **Coroutine**: sends message, streams via callback, auto tool loop |
| `llm_runtime_register_tool()` | Register C handler for a tool name |
| `llm_runtime_set_tool_schema()` | Set tool JSON schema for API request body |
| `llm_runtime_add_user_message()` | Add to history without sending |
| `llm_runtime_force_finish()` | Force-close partial assistant message |
| `llm_runtime_get_history()` | Read-only `{"messages":[...]}` |
| `llm_runtime_cancel()` | Cancel current turn |
| `llm_runtime_is_cancelled()` | Check cancellation (for tool functions) |

**Cancellation architecture**:
- `rt->running` is the single source of truth
- `llm_runtime_send()` resets `running=1` at start of each turn
- SIGINT → `llm_runtime_cancel()` → sets `running=0`
- Cancellation checks at every phase of send():
  - Before starting a stream → return
  - Mid-stream → cancel curl, force_finish parser, return
  - During tool execution → remaining tools get `{"error":"User has cancelled"}` result
- Tool functions receive `llm_runtime_t *rt` for cooperative cancellation

### 6. Runtime Test Program (`llm_runtime_test.c`)
- Global `g_rt` for SIGINT handler access
- **isocline** for input (replaced linenoise):
  - `ic_enable_multiline(true)` — **Enter submits**, **Shift+Enter / Ctrl+J inserts newline**
  - Persistent history via `ic_set_history(".history", 100)`
  - BBCode colored prompt: `[green][b]User[/] `
- Registered `sleep` tool demo with cancellation-aware stepping
- SIGINT: 1st press → cancel, 2nd press → exit

---

## Dependencies

| Library | Path | Purpose | Status |
|---|---|---|---|
| **libmill** | `libmill/` | Coroutines / async I/O | ✅ Integrated |
| **cjson** | `cjson/` | JSON parsing | ✅ Integrated |
| **isocline** | `isocline/` | Terminal input (multiline, history, colors) | ✅ Integrated |
| **hl-vt100** | `hl-vt100/` | VT100 rendering | ❌ Not yet used |

---

## Build

```bash
cd build && cmake .. && make -j$(nproc)
```

## Environment (`.env`)

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-v4-flash
```
