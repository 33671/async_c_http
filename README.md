# cop — async AI agent in C

A coroutine-based AI coding agent written in C. Uses **libmill** coroutines,
**libcurl** in forked child processes, and **SQLite** for persistent
conversation history. All data stored under `~/.cop/`.

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
                 LLM API Server
```

- **libcurl** in `mfork()`-ed child processes for blocking HTTP I/O
- **pipe** transfers SSE stream from child to parent coroutine
- **fdwait()** enables async waiting in libmill's event loop
- **Cancellation**: `kill(pid, SIGKILL)` terminates child instantly

## Features

| Feature | Description |
|---------|-------------|
| Streaming SSE | Real-time token-by-token output with reasoning/content distinction |
| Tool execution | shell, read, write, edit — with user approval and cancellation |
| Multi-turn | Automatic conversation history with tool-call loops |
| Session history | SQLite persistence in `~/.cop/history.sql` |
| Model switching | `/set_model` at runtime, config from `~/.cop/models.json` |
| CWD-scoped sessions | Sessions filtered by working directory, `/delete all` per directory |
| Tab completion | Slash commands and @filename completion |
| Input history | Persistent isocline history in `~/.cop/.history` |

## Quick Start

### 1. Configure models

Create `~/.cop/models.json`:

```json
{
  "providers": {
    "deepseek": {
      "baseUrl": "https://api.deepseek.com",
      "apiKey": "sk-your-key",
      "models": [
        {"id": "deepseek-v4-pro",   "contextWindow": 1000000},
        {"id": "deepseek-v4-flash", "contextWindow": 1000000}
      ]
    }
  }
}
```

### 2. Build

```bash
mkdir build && cd build
cmake .. && make -j$(nproc)
```

### 3. Run

```bash
./build/cop [--model <id>] [--log <path>]
```

### 4. REPL commands

| Command | Action |
|---------|--------|
| `<text>` | Send message, stream response |
| `/model` | List models grouped by provider (`*` = current) |
| `/set_model <id>` | Switch model at runtime |
| `/sessions` | List CWD sessions with message count and last user message |
| `/load <id>` | Load a session (prints last 50 messages) |
| `/delete <id>` | Delete a session |
| `/delete all` | Delete all sessions in current directory |
| `Ctrl+C` | Cancel current turn (twice to exit) |
| `Tab` | Complete `/` commands and `@` filenames |

## Project Structure

```
cop/
├── cop.c                   Main entry point (120 lines)
├── cop_ui.c/h              Terminal UI: REPL, completion, streaming display
├── llm_runtime.c/h         High-level orchestration
├── openai_stream_client.c/h  Async SSE streaming client
├── openai_sse_parser.c/h   SSE event & chunk parser
├── llm_parser.c/h          Multi-turn conversation state machine
├── tool_call_parser.c/h    Streaming tool-call accumulator
├── tool_functions.c/h      Built-in tools (shell, read, write, edit, sleep)
├── history_db.c/h          SQLite conversation storage
├── models_config.c/h       models.json parser
├── utils.c/h               .env loader (legacy)
├── sqlite/sqlite3.c/h      SQLite3 amalgamation
├── cjson/                  cJSON (bundled)
├── isocline/               Terminal input: multiline, history, completion (bundled)
├── libmill/                Coroutine library (bundled)
├── CMakeLists.txt
├── AGENT.md                Detailed development log
└── test_server.py          SSE test server
```

## Data Files (`~/.cop/`)

| File | Purpose |
|------|---------|
| `models.json` | Provider/model configuration |
| `history.sql` | Session and message persistence |
| `cop_YYYYMMDD_HHMMSS.log` | Per-session HTTP request logs |
| `.history` | isocline input line history |

## Architecture Details

### SSE Stream → Chunks → Parser → Runtime

```
Child (curl) → pipe → extract_next_chunk() → StreamChunk
    → llm_parser_feed_chunk() → content / reasoning / tool_calls
    → execute_tool_calls() → tool_fn(rt, args)
    → loop back to send another request if tools were called
```

### Cancellation

- `llm_runtime_cancel()` sets `running=0`
- Mid-stream: kills child process via SIGKILL, force-finishes parser
- Mid-tool: remaining tools get `{"error":"User has cancelled"}`
- `force_finish()` always sets a valid `content` field to prevent API 400 errors

### History DB Schema

```sql
sessions(id, cwd, name, created_at)
messages(id, session_id, msg_index, role, content,
         reasoning_content, tool_call_id, tool_calls, created_at)
```

Sessions are created lazily on first message. CWD scoping means
different project directories have independent session lists.

## Dependencies

| Library | Source | Purpose |
|---------|--------|---------|
| libmill | bundled | Coroutines / async I/O |
| libcurl | system | HTTP client |
| SQLite3 | `sqlite/` amalgamation | Conversation history |
| cJSON | bundled | JSON parsing |
| isocline | bundled | Terminal input, history, completion |
