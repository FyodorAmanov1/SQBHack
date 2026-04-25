# WebSocket `/ws/voice` protocol

Binary frames are mono **Int16 PCM**, **16 kHz**, little-endian (`pcm_s16le`) after `hello`.

## Client → server (JSON text)

| `type` | Body | Notes |
|--------|------|--------|
| `hello` | `sampleRate` (default 16000), `encoding` (`pcm_s16le`) | Required once per connection. Clears server **LLM history** for this socket. |
| `end_utterance` | — | Runs STT → LLM (with history) → TTS. If a run is already in progress, server may respond with `PIPELINE_BUSY`. |
| `cancel` | — | Clears buffered PCM; does not clear LLM history. |
| `reset_history` | — | Clears server LLM history only (align with UI “clear chat”). |

## Server → client (JSON text)

| `type` | Fields |
|--------|--------|
| `status` | `stage` (`idle` \| `stt` \| `llm` \| `tts`), `detail` (human text) |
| `transcript` | `text`, `final` |
| `reply_text` | `text` |
| `audio_meta` | `sampleRate` (24000), `encoding` (`pcm_s16le`) |
| `error` | `code`, `message` |

Common `error.code` values: `PROTOCOL`, `BAD_JSON`, `EMPTY_AUDIO`, `AUDIO_TOO_LARGE`, `PIPELINE_BUSY`, `PIPELINE_FAILED`, `UNKNOWN_TYPE`.

## Server → client (binary)

After `audio_meta`, one or more **Int16 PCM** chunks at **24 kHz** for the assistant reply audio.

## Optional auth

When `API_SHARED_SECRET` is set on the server, open the socket with query parameter **`?token=<same secret>`** (see also `NEXT_PUBLIC_WS_API_KEY` on the frontend for dev).
