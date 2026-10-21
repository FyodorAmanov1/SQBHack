# Aytingchi · Uzbek Voice Assistant

**A conversational interface that connects spoken Uzbek to a configurable language model and streams the response back as speech.**

Aytingchi is a bank-staff assistant prototype developed for the SQB hackathon. It combines a Next.js interface with a FastAPI speech backend, providing an end-to-end place to explore microphone capture, transcription, model responses and voice playback.

## Conversation flow

```text
Browser microphone → WebSocket → speech recognition → language model
                                                   → speech synthesis → browser audio
```

The same backend also exposes individual speech-to-text, language-model and text-to-speech endpoints, allowing each stage to be explored separately.

## What the repository provides

- **Voice conversation:** browser capture/playback and a streaming `/ws/voice` connection.
- **Speech recognition:** faster-whisper with configurable model selection and conversion support.
- **Language models:** an OpenAI-compatible provider path or local Ollama configuration.
- **Speech synthesis:** selectable OmniVoice or Edge TTS paths, including Uzbek voice options.
- **Web interface:** conversation and individual STT, text-chat and TTS tools, plus bank-workflow interface components.
- **Application packaging:** Docker Compose and a Caddy reverse-proxy configuration.

## Run the application

The project has separate frontend and backend dependencies. Start with the [development guide](DEVELOPMENT.md), which includes environment examples, Python installation, frontend commands, model preparation and troubleshooting.

For the packaged application, follow [deploy/QUICK-START.md](deploy/QUICK-START.md). From the repository root, after configuring the documented environment files:

```bash
docker compose build
docker compose up -d
```

Model weights and runtime dependencies are downloaded separately. Available memory, accelerator support, model choice and network access affect startup time and response latency; the repository does not provide a hardware-independent latency benchmark.

## Architecture and useful references

| Location | Role |
|---|---|
| [backend](backend/) | FastAPI application and speech/model services |
| [frontend](frontend/) | Next.js user interface and browser audio handling |
| [docker-compose.yml](docker-compose.yml) | Multi-service application definition |
| [deploy](deploy/) | Application hosting and configuration guides |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Detailed setup and troubleshooting |

The supported WebSocket message shapes and service behavior should be read alongside the backend source before connecting another client.

## Prototype boundaries

The project demonstrates an assistant interface and speech integration. Bank-workflow screens and generated answers do not establish access to a bank's production systems, verified customer records or an approved financial decision process. Recognition and generated responses need task-specific evaluation before operational use.

## Team

Initiated by **Jurabek Isoqov**, with **Fyodor Amanov** and **Jamshid Nurmukhammadov** as contributors. Preserve contributor attribution and the notices of the external models and services used by your configuration.
