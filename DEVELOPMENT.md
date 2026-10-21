# RealTimeVoice

Real-time Uzbek voice chat: browser microphone → **FastAPI** WebSocket → **faster-whisper** (STT) → **LLM** (OpenAI-compatible or Ollama) → **OmniVoice** (TTS) → streamed PCM back to the browser.

## Repository layout

- `backend/` — FastAPI, WebSocket `/ws/voice`, REST `POST /stt`, `POST /llm`, `POST /tts`
- `frontend/` — Next.js (App Router) client with mic capture and playback
- `docker/` — Caddyfile used by [docker-compose.yml](docker-compose.yml) (one public entry on **80/443**, no **`:3000`** or **`:8000`** in the browser)

## Docker on the server

**New to this?** Follow **[deploy/QUICK-START.md](deploy/QUICK-START.md)** (short checklist: `.env` → one line in `docker/Caddyfile` → `docker compose up`).

Use the included **Caddy** service (default **HTTP** on port **80** via [`docker/Caddyfile`](docker/Caddyfile) — edit the first line to your **domain** for **HTTPS**). The **browser uses one origin**; paths like `/stt` and `/ws/voice` go to FastAPI, everything else to Next.

1. Copy and edit the root [`.env.example`](.env.example) → **`.env`** (same folder as `docker-compose.yml` — **not** `frontend/.env`). Set **`PUBLIC_ORIGIN`** and **`WS_URL`** to match what users will type. For a **real domain with HTTPS**, change the first line of [`docker/Caddyfile`](docker/Caddyfile) from **`:80 {`** to **`aytingchi.uz {`** (your domain) and use **`https` / `wss`** in `.env` — then `docker compose up -d` again.
2. Configure **`backend/.env`** (Ollama, TTS, etc.) as in [Backend setup](#backend-setup) below.
3. From the **repo root**: `docker compose build` then `docker compose up -d`.
4. Open **`PUBLIC_ORIGIN`** in a browser (no **`:3000`** / **`:8000`**).

**Optional:** uncomment **`backend.ports`** in `docker-compose.yml` to expose `8000` on the host for debugging. Full host setup (firewall, DNS) is in [deploy/SERVER-SETUP.md](deploy/SERVER-SETUP.md). **HTTPS with Certbot** vs Caddy’s built-in Let’s Encrypt: [deploy/https-certbot-and-caddy.md](deploy/https-certbot-and-caddy.md).

## Prerequisites

- **Python 3.10–3.12** recommended (PyTorch and `omnivoice` may not support very new Python versions yet).
- **Node.js 20+** and npm.
- **GPU** optional but strongly recommended for OmniVoice and faster-whisper; CPU works but first responses are slower.
- Hugging Face access for downloading `k2-fsa/OmniVoice` (set `HF_TOKEN` if the model is gated or for higher rate limits).

### Pre-download large models (optional)

Weights are stored in the Hugging Face cache (Windows default: `%USERPROFILE%\.cache\huggingface\hub`). If you download a repo once, **uvicorn will not download it again** on that machine.

**OmniVoice TTS** (the multi‑GB `model.safetensors` you see):

```powershell
cd backend
.\.venv\Scripts\pip install huggingface_hub
.\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice')"
```

Or, if the `hf` CLI is on your PATH after installing `huggingface_hub`:

```powershell
hf download k2-fsa/OmniVoice
```

Use the same `HF_TOKEN` / account as in production if the repo requires it (`$env:HF_TOKEN="hf_..."` in PowerShell).

**faster-whisper STT** (defaults use `STT_MODEL_SIZE=small`, weights from `Systran/faster-whisper-small`; for `base` use `Systran/faster-whisper-base`):

```powershell
.\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-base')"
```

You can run these on another PC with good bandwidth, then **copy the `hub` folder** (or the whole `.cache\huggingface` tree) to the same path on your dev machine.

### Uzbek-specific STT (recommended)

Vanilla Whisper — even `large-v3` — is weak on Uzbek and frequently outputs garbled transliterations on clean speech. Use an Uzbek-fine-tuned checkpoint instead: set `STT_MODEL_SIZE` to a Hugging Face repo id and the backend will download and convert it to CTranslate2 on first startup (cached under `backend/models/whisper_ct2/`). Known good options:

| `STT_MODEL_SIZE`                     | Size   | Notes                                       |
| ------------------------------------ | ------ | ------------------------------------------- |
| `islomov/rubaistt_v2_medium`         | Medium | ~17% WER / 5.5% CER, Tashkent-dialect focus |
| `akbaralihah/uzbek-stt`              | Medium | ~16.7% WER, trained on ~1.6k h Uzbek audio  |
| `OvozifyLabs/whisper-small-uz-v1`    | Small  | UZ + EN + RU code-switch friendly           |

Example `backend/.env`:

```env
STT_MODEL_SIZE=islomov/rubaistt_v2_medium
STT_CT2_QUANTIZATION=float16   # int8_float16 on CPU for smaller RAM use
STT_DEVICE=auto
```

The first startup downloads ~1.5 GB and writes the CT2 weights to `backend/models/whisper_ct2/islomov__rubaistt_v2_medium/`. After that, loading is as fast as stock faster-whisper. Jamol picks up the new model automatically because it calls the same `/ws/voice` endpoint.

### Real-time TTS (recommended for chat)

OmniVoice is a flow-matching + internal-Whisper voice-clone system. On datacenter GPUs it synthesizes in ~1 s; on consumer laptop GPUs it takes **10–80 s** per utterance and is simply not usable for real-time conversation. The backend ships with a second TTS backend — **Microsoft Edge neural TTS** — that is free, needs no GPU, and returns 24 kHz audio from the cloud in ~1 s with two native Uzbek voices (`uz-UZ-MadinaNeural`, `uz-UZ-SardorNeural`).

Switch in `backend/.env`:

```env
TTS_BACKEND=edge                    # omnivoice | edge
TTS_EDGE_VOICE=uz-UZ-MadinaNeural   # or uz-UZ-SardorNeural
```

Trade-offs:

| Backend | Time to first audio (laptop) | Voice clone | Uzbek quality | Cost | Offline |
| --- | --- | --- | --- | --- | --- |
| `omnivoice` | 10–80 s | Yes (your own clip) | Good, depends on clone | Free | Yes |
| `edge` | **~1 s** | No (2 preset voices) | Excellent (Microsoft neural) | Free | No |

With `TTS_BACKEND=edge`, startup is faster too: the OmniVoice weights and its internal Whisper are skipped. `POST /tts`, `WS /ws/voice` and `GET /voices` all switch automatically — Jamol and the web client don't need changes.

## Backend setup

1. Create a virtual environment and install PyTorch **for your platform** from [PyTorch Get Started](https://pytorch.org/get-started/locally/) (match CUDA if you use GPU).

2. Install the rest:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `pip install omnivoice` fails, install PyTorch first, then retry.

**NVIDIA GPU:** the default `torch` from PyPI is often CPU-only. After installing requirements, confirm GPU with `.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"`. If it prints `False`, reinstall CUDA wheels (example for CUDA 12.6): `pip install --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu126`. You do not need the full NVIDIA CUDA Toolkit for inference; the driver plus these wheels is enough.

3. Copy environment file and edit:

```powershell
copy .env.example .env
```

Set `OPENAI_API_KEY` when using `LLM_PROVIDER=openai`, or run Ollama locally and set `LLM_PROVIDER=ollama`, `OLLAMA_HOST`, and `OLLAMA_MODEL`.

For GPU TTS, set for example `TTS_DEVICE_MAP=cuda:0` and `TTS_DTYPE=float16`. On CPU use `TTS_DEVICE_MAP=cpu` and `TTS_DTYPE=float32`.

**Uzbek STT:** `STT_MODEL_SIZE=small` (or `medium`) is much more accurate than `base` for Uzbek Latin; pair with `STT_BEAM_SIZE=6–8` on GPU. Tune `STT_INITIAL_PROMPT` / `STT_HOTWORDS` in `.env` with vocabulary you actually say. Restart the API after changing STT env vars (model swap reloads on process start).

**Voice clones (`myVoice/`):** put reference WAV/FLAC/OGG files under `myVoice/` at the repo root (or set `TTS_VOICES_SCAN_DIR`). On startup the API scans that folder and exposes `GET /voices` (optional `?refresh=1` after adding files). The main page and TTS tool let you pick a speaker; labels come from each file’s name (nested folders show as `folder — stem`). Optional `same-name.txt` next to a clip supplies `ref_text` for better clone quality.

4. Run the API (from the `backend` folder so `app` imports work):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If you skip activation, call the venv’s Python explicitly (this avoids “`uvicorn` is not recognized” on Windows):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The first startup downloads Whisper and OmniVoice weights; it can take several minutes.

**If you see `No module named uvicorn`:** install dependencies into this venv (from `backend`):

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

Then run `python -m uvicorn …` again. After a successful install, `uvicorn.exe` also appears under `.venv\Scripts\`; if `uvicorn` is still “not recognized”, keep using `python -m uvicorn`.

## Frontend setup

```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

`npm run dev` starts Next on **port 80** (default HTTP), so you can open the app at **`http://server.uz`** with **no `:3000` in the URL** — after you point the name at your machine (see below). The API is still on **port 8000**; set in **`.env.local`**, e.g. `NEXT_PUBLIC_API_URL=http://server.uz:8000`.

**Name `server.uz` to this PC (or your server IP):** add a line to the hosts file, e.g. on Windows: `C:\Windows\System32\drivers\etc\hosts` — `127.0.0.1 server.uz` (or your LAN IP for other devices on the same network). Use a real DNS A record in production.

**Port 80 (privileged):** on **Windows**, an **elevated** PowerShell may be required; on **Linux/macOS** you may need `sudo` to bind to port 80. If that fails, use `npm run dev:3000` and open [http://localhost:3000](http://localhost:3000) or [http://server.uz:3000](http://server.uz:3000) instead. For **production** without `:3000`, use `npm run start:80` (same port‑80 caveats) or place **Caddy** / **nginx** on 80/443 and reverse‑proxy to a higher Node port.

### Production: `aytingchi.uz` without `:3000`

**Preferred:** use **[Docker on the server](#docker-on-the-server)** so **Caddy** in `docker-compose.yml` serves **80/443** and you do not publish **3000** or **8000** to the public.

If the site is showing **`http://aytingchi.uz:3000`**, the Next process is still bound to **port 3000** and the browser is talking to it **directly**. Browsers do not hide the port: you have to **listen on 80/443** for HTTP/HTTPS, or use a **reverse proxy**.

**Manual setup (VPS with DNS on `aytingchi.uz`):**

1. Keep Next on **localhost only** (typical: `PORT=3000` / `next start` or `npm run start` on `127.0.0.1:3000`).
2. Run **Caddy** or **nginx** on the server on **:80** and **:443**, with `server_name aytingchi.uz`, and **`proxy_pass` / `reverse_proxy` to `http://127.0.0.1:3000`**.
3. Point the domain’s **A record** to the server’s public IP; open the firewall for **80** and **443** (not 3000, if the proxy is the only public entry).

**Step‑by‑step server instructions (DNS, firewall, build, Caddy, systemd):** [deploy/SERVER-SETUP.md](deploy/SERVER-SETUP.md)

**Config snippets** in this repo:

- [deploy/caddy-aytingchi.uz](deploy/caddy-aytingchi.uz) — Caddy (automatic HTTPS is straightforward).
- [deploy/nginx-aytingchi.uz.conf](deploy/nginx-aytingchi.uz.conf) — Nginx (use Certbot for TLS).

After that, users open **`https://aytingchi.uz`** with **no** `:3000` in the URL.

**Frontend → FastAPI in production:** the UI still must know where the API is. `lib/apiBase.ts` will use **`NEXT_PUBLIC_API_URL`** in `.env.production` on the build server, e.g. `https://aytingchi.uz:8000` if the API is public on 8000, or put the API behind the same host (e.g. subdomain `api.aytingchi.uz` → 8000) and set `NEXT_PUBLIC_API_URL=https://api.aytingchi.uz` before `npm run build`.

Ensure `NEXT_PUBLIC_WS_URL` points to your backend (default `ws://127.0.0.1:8000/ws/voice` when not set) or to `ws://server.uz:8000/ws/voice` when you use a hostname. If the backend has **`API_SHARED_SECRET`** set, set **`NEXT_PUBLIC_WS_API_KEY`** in the frontend to the same value so the client appends **`?token=…`** on the WebSocket URL and sends **`X-API-Key`** on REST calls from the tools pages.

### Uzbek tools (frontend)

- **`/vositalar`** — hub with links to ovozli suhbat (`/`), matn suhbati (`/vositalar/matn`), nutqdan matn (`/vositalar/stt`), matndan ovoz (`/vositalar/tts`).
- Matn, STT, and TTS pages call **`POST /llm`**, **`POST /stt`**, and **`POST /tts`** on the FastAPI host. Set **`NEXT_PUBLIC_API_URL`** (e.g. `http://127.0.0.1:8000`) if the API is not the same origin/port as inferred from **`NEXT_PUBLIC_WS_URL`**.

## Usage

1. Wait until the UI shows the server as connected.
2. Tap the **microphone** to start listening, speak in Uzbek, tap again to send (or **Bekor qilish** to discard without sending).
3. The transcript and assistant reply appear as text; the assistant reply is played automatically as audio.
4. **Sozlamalar** opens chat options (saved in the browser): interrupt TTS when starting a new recording, auto-scroll, pipeline chip, and low-latency capture hint. Stopping the mic no longer stops playback, so you can hear the reply while the UI returns to “connected”.
5. **Vositalar** opens the tools hub for matn, STT-only, and TTS-only flows in Uzbek.

## WebSocket protocol (summary)

Full contract: [docs/ws-protocol.md](docs/ws-protocol.md).

- Client sends JSON `{"type":"hello","sampleRate":16000,"encoding":"pcm_s16le"}` after connect. **`hello` clears server-side LLM history** for that connection (same as a fresh reconnect).
- While recording, client sends **binary** frames of mono **Int16 PCM** at 16 kHz (from the AudioWorklet).
- Client sends JSON `{"type":"end_utterance"}` to run STT → LLM (with prior turns) → TTS. A second `end_utterance` while a run is active may receive `error` with code **`PIPELINE_BUSY`**.
- Client may send `{"type":"reset_history"}` to clear LLM history without reconnecting (the UI **Tozalash** button sends this when the socket is open).
- Server sends JSON `status`, `transcript`, `reply_text`, `audio_meta`, `error`, and **binary** PCM Int16 chunks at 24 kHz after `audio_meta`.

## REST debugging

- `POST /stt` — multipart file field `file` (WAV/FLAC/…)
- `POST /llm` — JSON `{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."}]}`
- `POST /tts` — JSON `{"text":"..."}` → `audio/wav`

When **`API_SHARED_SECRET`** is set, these routes expect **`X-API-Key: <secret>`** or **`Authorization: Bearer <secret>`**.

## Production checklist

- Set **`FRONTEND_ORIGIN`** to your real site origin (no `*` in CORS for production).
- Optionally set **`API_SHARED_SECRET`** and configure the frontend **`NEXT_PUBLIC_WS_API_KEY`** plus REST clients with the same secret.
- Adjust **`LLM_HISTORY_MAX_MESSAGES`** (default 24) for how much prior dialogue each voice connection retains.
- **`get_settings()`** is cached with **`@lru_cache`**; changing `.env` requires a **process restart** for values to reload.

## Notes

- **Latency (end‑to‑end voice turn):** the slowest stage is usually **OmniVoice on CPU**. Use a **GPU** (`TTS_DEVICE_MAP=cuda:0`, `TTS_DTYPE=float16` when VRAM allows), lower **`TTS_NUM_STEPS`** (e.g. 8–12), and a smaller Whisper size (**`STT_MODEL_SIZE=base` / `tiny`**) for faster STT. STT defaults aim at **Uzbek accuracy**: **`STT_MODEL_SIZE=small`**, **`STT_BEAM_SIZE=5`**, forced **`STT_LANGUAGE=uz`**, **`task=transcribe`**, and a built-in Uzbek Latin **`STT_INITIAL_PROMPT`** (set it to an empty value in `.env` to disable). For the fastest CPU path, try **`STT_MODEL_SIZE=base`** and **`STT_BEAM_SIZE=1`**. Cap reply length with **`OLLAMA_NUM_PREDICT`** / **`OPENAI_MAX_TOKENS`** so the LLM finishes sooner for short voice answers.
- **STT tuning (Uzbek):** Keep **`STT_LANGUAGE=uz`** so Whisper does not guess another language. If transcripts still look “translated” or wrong, confirm you are not overriding the prompt with English-only text. **`STT_INITIAL_PROMPT`** should stay in **Uzbek Latin** (letters like **o‘**, **g‘**, **sh**, **ch**) for spelling bias. **`STT_VAD_FILTER`** and **`STT_VAD_PARAMETERS_JSON`** help if silence trimming cuts words. **`STT_TEMPERATURE`**, **`STT_COMPRESSION_RATIO_THRESHOLD`**, and **`STT_LOG_PROB_THRESHOLD`** apply only when set in `.env`. **`STT_CONDITION_ON_PREVIOUS_TEXT=false`** can reduce repetition on long clips. **`medium`** / **`large-v3`** improve quality further if VRAM and load time are acceptable.
- OmniVoice generates a full utterance per request; the backend streams it in small PCM chunks for responsive playback.
- **Voice clone:** set **`TTS_REF_AUDIO_PATH`** to a short WAV of your voice (paths can be absolute, or relative to the **repo root** or **`backend/`** working directory—spaces in filenames are fine if the value is quoted in `.env`). Set **`TTS_REF_TEXT`** to the **exact** words spoken in that clip for better timbre match. Restart the server after changing `.env` (`get_settings` is cached).
- Whisper returns a **final** transcript per utterance (no live partial word stream in this version).
- If downloads from Hugging Face fail, try a mirror, for example: `set HF_ENDPOINT=https://hf-mirror.com` (Windows cmd: `set`, PowerShell: `$env:HF_ENDPOINT=...`).
