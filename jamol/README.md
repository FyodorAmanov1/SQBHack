# Jamol

Windows assistant: speak a **configured** phrase → **allowlisted** actions (e.g. open Notepad).  
**STT uses the same `/ws/voice` WebSocket the browser uses** (opt-in `stt_only` mode so no LLM/TTS runs server-side), and TTS still calls `POST /tts`. When the RealTimeVoice server isn't reachable, Jamol falls back to `POST /stt` then to embedded in-process models. Jamol only adds command execution.

## Prerequisites

1. **Run the FastAPI backend** (loads Whisper + OmniVoice once, same as the browser client):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

2. **Install Jamol** (from repo root; this pulls `httpx`, `sounddevice`, `soundfile`, etc.):

```powershell
pip install -e "./jamol[dev]"
```

If you see `No module named 'sounddevice'`, your environment is stale — run `pip install sounddevice` or reinstall: `pip install -e "./jamol" --upgrade`.

3. Optional: if the API uses `API_SHARED_SECRET`, set `JAMOL_API_KEY` or pass `--api-key`.

## Configuration

Copy `jamol/config/apps.example.yaml` to `jamol/config/apps.yaml` and edit allowed apps/phrases. Set `JAMOL_CONFIG` to point at a custom YAML path if needed.

## Run (GUI)

```powershell
python -m jamol --gui
```

Click **Apply / test connection** (checks `GET /health`), then **hold the big button** (or press **F9** anywhere on Windows) and speak. Recording stops automatically when you release, or when WebRTC VAD detects silence — whichever comes first. Pick a mic from the **Device** dropdown and a TTS speaker from the **TTS speaker** list (populated from `GET /voices`).

```powershell
jamol-gui
```

### Keyboard shortcuts

- **Hold mouse button** on the big "Hold to speak" button → record while held.
- **Hold Space** while the window is focused → same as above.
- **Hold F9** (global, works outside the Jamol window) → same as above. Change the key in the GUI field labelled "Hotkey" and click **Rearm hotkey**.

### CLI flags relevant to capture

- `--mic-device N` pins a specific input device (index from `sounddevice.query_devices()`).
- `--no-vad` disables silence auto-stop; falls back to the fixed `--phrase-time-limit` duration.
- `--hotkey KEY` sets the GUI global PTT key (single key, default `f9`).

## Run (terminal)

```powershell
python -m jamol
```

## Fallback: embedded audio (no HTTP)

Same in-process code as `backend/app/services` (heavy deps, same `.env` as uvicorn):

```powershell
pip install -e "./jamol[backend]"
python -m jamol --embedded-audio --gui
```

## Legacy STT only

`--engine google` or `--engine whisper` uses the old Jamol microphone paths; TTS still prefers the API when the server is up.

## Safety

Only YAML-listed actions run; no arbitrary shell commands.

## STT transport

By default Jamol streams captured PCM to `ws://<api>/ws/voice?token=<key>` with a `hello` message containing `"stt_only": true`. The server runs Whisper and emits a single `transcript` message — it does **not** call the LLM or TTS on this session. This matches the browser client's network path (same codec, same buffering, same `voice_ws.py` handler), so transcription accuracy is identical to the web app.

If the WebSocket connection fails, Jamol logs a warning and retries the same capture via `POST /stt` so an offline WS stack still works.
