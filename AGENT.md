# AGENT.md - Project Progress Summary

## Project: async_c_http

An **async HTTP SSE (Server-Sent Events) client in C** for streaming OpenAI-compatible API responses, using **libmill** coroutines and **libcurl** in forked child processes (`mfork`).

---

## Architecture

```
                       Main Process (libmill)
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
  │   Child Process    │   Child Process    │
  │ curl_easy_perform()│ curl_easy_perform()│
  └────────────────────┘────────────────────┘
                       │
                       ▼
                 HTTP Server
```

- **libcurl** runs in forked child process(es) via `mfork()` for blocking HTTP I/O
- **pipe** transfers data from child process to libmill coroutine in parent process
- **fdwait()** enables async waiting on pipe in libmill's event loop
- **Cancellation**: `kill(child_pid, SIGKILL)` terminates the child process immediately — no xfer callback needed

---

## Component Status

| Component | Files | Status | Description |
|---|---|---|---|
| **SSE Parser** | `openai_sse_parser.h/.c` | ✅ Stable | SSE event extraction, JSON validation, chunk parsing (content, reasoning, tool_calls, usage) |
| **Tool Call Parser** | `tool_call_parser.h/.c` | ✅ Stable | Streaming tool_call delta fragment accumulation |
| **Stream Client** | `openai_stream_client.h/.c` | ✅ Stable | Async streaming client (libmill coroutines + mfork child process + libcurl + pipe). Dynamic request body builder with tool schema support |
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
- `stream_client_new/free()` — Lifecycle. `free()` kills child via SIGKILL then `waitpid()` to reap.
- `stream_client_start_chat(client, messages)` — Accepts cJSON messages array, builds full request body, forks a child process via `mfork()`. Child runs `curl_easy_perform()`, writes HTTP stream to pipe, exits. Parent closes write end, reads from pipe via `fdwait()` in coroutine.
- `build_request_body()` — Static helper using cJSON API. Includes: model, messages, temperature, stream=true, tool schemas (if set)
- `stream_client_set_tool_schemas()` — Set tool definition JSON array (deep-copied, included in every subsequent request)
- `next_chunk()` / `next_chunk_nowait()` — Coroutine-based async chunk iteration. `extract_chunk_internal` loops on `c->running`, reads from pipe via `fdwait`. Pipe EOF (= child exit) breaks the loop naturally.
- `stream_client_cancel()` — Sets `running=0` + `kill(child_pid, SIGKILL)` to terminate the child process. Pipe EOF signals completion to the parent.
- `stream_client_wait_done()` — `waitpid()` to reap the child, checks exit status for error reporting.

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
| `llm_runtime_popen()` | **Coroutine**: async popen — forks child, captures stdout+stderr via fdwait, cancellable via SIGKILL |

**Cancellation architecture**:
- `rt->running` is the single source of truth
- `llm_runtime_send()` resets `running=1` at start of each turn
- SIGINT → `llm_runtime_cancel()` → sets `running=0`
- Cancellation checks at every phase of send():
  - Before starting a stream → return
  - Mid-stream → kill child process (SIGKILL), force_finish parser, return
  - During tool execution → remaining tools get `{"error":"User has cancelled"}` result
- Tool functions receive `llm_runtime_t *rt` for cooperative cancellation
- For blocking CLI commands, use `llm_runtime_popen()` instead of `popen()`/`system()`:
  - Forks child via `mfork()`, captures stdout+stderr via pipe
  - Uses `fdwait()` to wait without blocking other coroutines
  - Supports deadline (timeout)
  - Automatically killed (SIGKILL) if the runtime is cancelled

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

---

## Debug Log — mfork migration (2026-05-03)

### Bug 1: `fdwait` FDW_ERR / FDW_IN ordering (FIXED)

**Symptom**: First turn worked perfectly; second turn silently skipped the `finish_reason` chunk, leaving the LLM parser stuck in `IN_ASSISTANT` state. Third turn crashed with *"cannot add message while assistant stream in progress"*.

**Root cause**: When a child process exits, `close(pipe_write_end)` causes the parent's `fdwait()` on the read end to return **`FDW_ERR | FDW_IN`** (hangup + data-available). The original code checked `FDW_ERR` first and `break`-ed immediately — before the `FDW_IN` handler had a chance to `read()` the remaining data (finish_reason chunk + `[DONE]`) from the kernel pipe buffer. `stream_client_wait_done()` then closed the pipe, losing that data permanently.

Turn 1 worked by **timing luck**: the parent had already drained all data from the pipe before the child exited. Turn 2 had different timing and hit the race consistently.

**Fix**: Reorder — always drain `FDW_IN` first, then only `break` on `FDW_ERR` if `FDW_IN` was NOT also set:
```c
// BEFORE (buggy):
if (ev & FDW_ERR) { break; }         // breaks before reading
if (ev & FDW_IN) { read... }         // never reached

// AFTER (fixed):
if (ev & FDW_IN) { read... }         // always drain pipe first
if ((ev & FDW_ERR) && !(ev & FDW_IN)) { break; }  // real error only
```

**Lesson**: POSIX pipes signal EOF via `FDW_IN` + possibly `FDW_ERR`. Always prioritize draining data before acting on error flags. The libmill docs hint at this: *"If an error happens while there are still bytes to be received from the socket combination of FDW_ERR and FDW_IN may be returned."*

---

### Bug 2: `llm_runtime_popen` always returns -1 (FIXED)

**Symptom**: Every shell command invoked via `llm_runtime_popen()` returned -1 with `"command failed or timed out"`, even for trivial commands like `echo hello`.

**Root cause**: The same `FDW_ERR`-without-`FDW_IN` pattern as Bug 1, but with a different manifestation. When a short-lived shell command finishes quickly:

1. `fdwait` → `FDW_IN` → `read()` → data (stdout+stderr) ✓
2. `fdwait` → `FDW_IN` → `read()` → more data ✓
3. `fdwait` → **`FDW_ERR` only** (no `FDW_IN`) — pipe closed by child exit

The code treated `FDW_ERR`-without-`FDW_IN` as a hard error and `break`-ed immediately. The `finished` flag stayed 0, so the post-loop cleanup called `kill(pid, SIGKILL)` on the already-exited child (harmless but pointless) and returned -1. The last batch of data — or at minimum the pipe EOF — was never observed.

**Debugging**: Wrote a standalone `mfork`+`fdwait` test that traced every `fdwait` return value:
```
fdwait returned: 0x1 (IN=1 ERR=0)  → read "hello world\n"
fdwait returned: 0x1 (IN=1 ERR=0)  → read "stderr test\n"
fdwait returned: 0x4 (IN=0 ERR=1)  → BROKE without reading EOF
```
Confirmed that the kernel delivers the final pipe-close as a pure hangup (`FDW_ERR`) with no readability flag.

**Fix**: After `FDW_ERR`-only, try `read()` one more time before giving up:
```c
if ((ev & FDW_ERR) && !(ev & FDW_IN)) {
    ssize_t n = read(pipefd[0], buf, sizeof(buf));
    if (n > 0)      { /* accumulate residual data */ }
    else if (n == 0) { finished = 1; }   // ← EOF caught here
    else            { break; }           // real error
}
```
The bonus `read()` returns 0 (EOF) when the pipe is fully drained, setting `finished = 1`. Verified with a command containing `sleep 0.1` (slow exit) and a bare `echo` (instant exit) — both now work.

**Lesson**: `FDW_ERR`-only on a pipe read end after drain = child exited. Always try `read()` one more time before concluding error.

---

### Defensive fix: `[DONE]` re-check after consuming `"data: "` prefix (FIXED)

**Context**: `extract_next_chunk()` has a top-level check for `[DONE]` and `data: [DONE]` that catches the common case. However, the multi-line JSON fallback path has a code branch that consumes `"data: "` (6 bytes) when an SSE event contains non-JSON content, then returns 0 — forcing an unnecessary `fdwait` round-trip in `extract_chunk_internal`. This path could theoretically be hit if a non-standard SSE event with a `"data:"` prefix arrives before `[DONE]`.

**Fix**: After consuming the `"data: "` prefix, immediately check if the remaining buffer starts with `[DONE]`. If so, extract it right away without the extra `fdwait` cycle:

```c
stream_buffer_consume(buf, 6);
if (buf->len >= 6 && strncmp(buf->data, "[DONE]", 6) == 0) {
    chunk->is_done = 1;
    chunk->is_valid = 1;
    stream_buffer_consume(buf, 6);
    while (buf->len > 0 && (buf->data[0] == '\n' || buf->data[0] == '\r'))
        stream_buffer_consume(buf, 1);
    return 1;
}
return 0;
```

---

### Potential issue: Byte counting across fork

After `mfork()`, `c->total_bytes` in the child process is a separate copy. The child's write callback increments its own `total_bytes`, but the parent never sees those increments. **Mitigated**: the parent now counts bytes on `read()` — `c->total_bytes += n` — giving an accurate count from the parent's perspective. The child's copy is irrelevant.

### Potential issue: Log interleaving across fork

Both parent and child share the same `c->log_fp` file descriptor (inherited across `mfork`). Concurrent writes from two processes to the same `FILE*` can interleave at the `stdio` buffer level. In practice this is benign because the child only logs during `curl_easy_perform()` (when the parent is waiting on `fdwait`), and the parent only logs before/after. But `fflush()` in one process does not flush the other process's `stdio` buffer. Acceptable for now; a future improvement could use `write()` directly or separate log files.

### Architecture note: Zombie processes

When `stream_client_free()` or `stream_client_wait_done()` is called, `waitpid()` reaps the child. If the parent process exits (e.g. `_exit(0)` on second SIGINT), any unreaped child is automatically reparented to init (PID 1), which reaps it. So zombies are not a persistent problem — they only exist for the brief window between child exit and parent exit, and the kernel cleans up. No code change needed.

### Pre-existing issue (inherited from pthread version): Pipe buffer drain race

In the original pthread code, `c->curl_running = 0` was set by the curl thread **before** closing the pipe. The main loop condition `while (c->running && (c->curl_running || first_attempt))` would exit as soon as `curl_running` went to 0, even if data was still sitting in the kernel pipe buffer. This was masked because the write callback's `write()` blocked on pipe-full, providing backpressure that forced the main thread to keep reading. The new mfork code avoids this entirely by relying purely on pipe EOF (child closes write end → parent reads until `read()` returns 0).

### Pre-existing quirk: `[DONE]` marker extraction path (improved)

The `[DONE]` marker is recognized via a top-level substring check (`strncmp` for `[DONE]` and `data: [DONE]`). The multi-line JSON fallback path previously consumed the `"data: "` prefix and returned 0 when it encountered non-JSON content — which would waste a round-trip if the consumed prefix revealed a `[DONE]` underneath. **Improved**: the fallback path now immediately re-checks for `[DONE]` after consuming the prefix, avoiding the extra cycle. A future robustness improvement would be to check for `[DONE]` before attempting any JSON parsing at all (right after the leading-whitespace skip).

### Architecture note: curl handle cleanup across fork

After `mfork()`, the parent calls `curl_easy_cleanup(curl)` on its copy of the curl handle while the child runs `curl_easy_perform()` on its own copy. This is safe because:
- `fork` + copy-on-write gives each process an independent copy of the curl handle
- `curl_easy_init()` allocates heap memory but does not open sockets
- The actual TCP connection is created by `curl_easy_perform()` in the child
- `curl_easy_cleanup()` in the parent frees only the parent's copy

The same applies to `curl_slist_free_all(headers)` and `free(body)` — both are safe to call in the parent immediately after fork.
