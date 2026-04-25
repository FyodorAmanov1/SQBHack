"""Jamol: Windows voice assistant with allowlisted actions."""

__version__ = "0.1.0"

# Default TTS speaker id sent to the backend. Matches ``uz-UZ-SardorNeural``
# (Microsoft's Uzbek male neural voice) when the backend runs ``TTS_BACKEND=edge``.
# If the backend is on OmniVoice, the id is harmless — it doesn't match any
# local reference-clip and the backend falls back to ``tts_ref_audio_path``.
# Override via ``--speaker-id`` CLI flag or the ``JAMOL_SPEAKER_ID`` env var.
DEFAULT_SPEAKER_ID = "uz-UZ-SardorNeural"
