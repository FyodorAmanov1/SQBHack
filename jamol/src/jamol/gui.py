from __future__ import annotations

import argparse as argparse_mod
import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

from jamol import DEFAULT_SPEAKER_ID
from jamol.api_client import default_api_base, default_api_key
from jamol.audio_io import InputDevice, list_input_devices
from jamol.audio_mode import resolve_audio
from jamol.config import load_apps_yaml, resolve_config_path
from jamol.hotkey import PushToTalkHotkey, is_available as hotkey_available
from jamol.pipeline import handle_transcript
from jamol.stt import capture_pcm, transcribe_pcm_via_api

logger = logging.getLogger(__name__)

# Dark theme (VS Code–like)
_BG = "#1e1e1e"
_FG = "#d4d4d4"
_MUTED = "#858585"
_ENTRY_BG = "#3c3c3c"
_ACCENT = "#0e639c"
_ACCENT_HOT = "#c72c2c"

_DEFAULT_HOTKEY = "f9"
_DEFAULT_PHRASE_LIMIT = 15.0


def _apply_dark_style(root: tk.Tk) -> ttk.Style:
    root.configure(bg=_BG)
    st = ttk.Style()
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure("TFrame", background=_BG)
    st.configure("TLabel", background=_BG, foreground=_FG, font=("Segoe UI", 10))
    st.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#ffffff")
    st.configure("Sub.TLabel", foreground=_MUTED, font=("Segoe UI", 9))
    st.configure("TCheckbutton", background=_BG, foreground=_FG)
    st.configure("TRadiobutton", background=_BG, foreground=_FG)
    st.configure("TButton", font=("Segoe UI", 10))
    st.configure(
        "PTT.TButton",
        font=("Segoe UI", 14, "bold"),
        foreground="#ffffff",
        background=_ACCENT,
    )
    st.configure(
        "PTTHot.TButton",
        font=("Segoe UI", 14, "bold"),
        foreground="#ffffff",
        background=_ACCENT_HOT,
    )
    return st


class _QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue[str]) -> None:
        super().__init__()
        self._q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put(self.format(record))
        except Exception:
            self.handleError(record)


def run_gui(args: Any) -> int:
    cfg_path = resolve_config_path(getattr(args, "config", None))
    apps = load_apps_yaml(cfg_path)

    root = tk.Tk()
    root.title("Jamol — RealTimeVoice commands")
    root.minsize(620, 640)
    root.geometry("760x700")
    _apply_dark_style(root)

    log_q: queue.Queue[str] = queue.Queue()
    log_handler = _QueueLogHandler(log_q)
    log_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    root_logger.setLevel(getattr(logging, getattr(args, "log_level", "INFO"), "INFO"))

    ctx: dict[str, Any] = {
        "api": None,
        "embedded": None,
        "voices": [],
        "_ids": [],
    }

    # Recording session state (owned by GUI thread; worker uses stop_event/result_q).
    rec_state: dict[str, Any] = {
        "stop_event": None,
        "thread": None,
        "busy": False,
    }
    rec_result_q: queue.Queue[tuple[str | None, str | None]] = queue.Queue()

    # ---- Top section: connection + mic -----------------------------------
    main = ttk.Frame(root, padding=16)
    main.pack(fill=tk.BOTH, expand=True)

    ttk.Label(main, text="Jamol", style="Title.TLabel").pack(anchor=tk.W)
    ttk.Label(
        main,
        text="Hold the button (or press F9) to speak. Silence auto-stops the recording.",
        style="Sub.TLabel",
        wraplength=680,
    ).pack(anchor=tk.W, pady=(0, 12))

    # --- Connection card ---
    card = ttk.Frame(main)
    card.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(card, text="Audio source", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

    embedded_var = tk.BooleanVar(value=bool(getattr(args, "embedded_audio", False)))

    def on_embed_toggle() -> None:
        st = tk.NORMAL if not embedded_var.get() else tk.DISABLED
        api_url_entry.configure(state=st)
        api_key_entry.configure(state=st)

    emb_row = ttk.Frame(card)
    emb_row.pack(fill=tk.X, pady=(6, 4))
    ttk.Checkbutton(
        emb_row,
        text="Embedded (in-process models, no server)",
        variable=embedded_var,
        command=on_embed_toggle,
    ).pack(anchor=tk.W)

    url_row = ttk.Frame(card)
    url_row.pack(fill=tk.X, pady=2)
    ttk.Label(url_row, text="API URL", width=10).pack(side=tk.LEFT)
    api_url_var = tk.StringVar(value=getattr(args, "api_base", None) or default_api_base())
    api_url_entry = ttk.Entry(url_row, textvariable=api_url_var, width=56)
    api_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    key_row = ttk.Frame(card)
    key_row.pack(fill=tk.X, pady=2)
    ttk.Label(key_row, text="API key", width=10).pack(side=tk.LEFT)
    api_key_var = tk.StringVar(value=getattr(args, "api_key", None) or (default_api_key() or ""))
    api_key_entry = ttk.Entry(key_row, textvariable=api_key_var, width=56, show="•")
    api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    btn_row = ttk.Frame(card)
    btn_row.pack(fill=tk.X, pady=(8, 0))
    conn_lbl = ttk.Label(btn_row, text="● …", font=("Segoe UI", 9))
    conn_lbl.pack(side=tk.LEFT)

    # --- Mic / capture card ---
    mic_card = ttk.Frame(main)
    mic_card.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(mic_card, text="Microphone", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

    devices: list[InputDevice] = list_input_devices()
    device_labels = [d.label for d in devices] or ["(no input devices found)"]

    mic_row = ttk.Frame(mic_card)
    mic_row.pack(fill=tk.X, pady=(6, 2))
    ttk.Label(mic_row, text="Device", width=10).pack(side=tk.LEFT)
    mic_combo = ttk.Combobox(mic_row, values=device_labels, state="readonly", width=56)
    if devices:
        default_idx = next(
            (i for i, d in enumerate(devices) if d.is_default), 0
        )
        mic_combo.current(default_idx)
    else:
        mic_combo.configure(state=tk.DISABLED)
    mic_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def on_refresh_mics() -> None:
        nonlocal devices, device_labels
        devices = list_input_devices()
        device_labels = [d.label for d in devices] or ["(no input devices found)"]
        mic_combo["values"] = device_labels
        if devices:
            default_idx = next((i for i, d in enumerate(devices) if d.is_default), 0)
            mic_combo.current(default_idx)
            mic_combo.configure(state="readonly")
        else:
            mic_combo.configure(state=tk.DISABLED)

    ttk.Button(mic_row, text="↻", width=3, command=on_refresh_mics).pack(side=tk.LEFT, padx=(6, 0))

    def selected_device_index() -> int | None:
        if not devices:
            return None
        i = mic_combo.current()
        if 0 <= i < len(devices):
            return devices[i].index
        return None

    opts_row = ttk.Frame(mic_card)
    opts_row.pack(fill=tk.X, pady=(4, 0))

    vad_var = tk.BooleanVar(value=not bool(getattr(args, "no_vad", False)))
    ttk.Checkbutton(
        opts_row,
        text="Auto-stop on silence (VAD)",
        variable=vad_var,
    ).pack(side=tk.LEFT)

    ttk.Label(opts_row, text="   Max sec", style="Sub.TLabel").pack(side=tk.LEFT)
    max_sec_var = tk.StringVar(value=str(int(getattr(args, "phrase_time_limit", _DEFAULT_PHRASE_LIMIT))))
    ttk.Entry(opts_row, textvariable=max_sec_var, width=5).pack(side=tk.LEFT, padx=(4, 10))

    ttk.Label(opts_row, text="Hotkey", style="Sub.TLabel").pack(side=tk.LEFT)
    hotkey_var = tk.StringVar(value=getattr(args, "hotkey", None) or _DEFAULT_HOTKEY)
    ttk.Entry(opts_row, textvariable=hotkey_var, width=8).pack(side=tk.LEFT, padx=(4, 0))

    # --- Speaker + TTS ---
    sp_row = ttk.Frame(main)
    sp_row.pack(fill=tk.X, pady=(4, 8))
    ttk.Label(sp_row, text="TTS speaker").pack(side=tk.LEFT)
    speaker_combo = ttk.Combobox(sp_row, width=52, state="readonly")
    speaker_combo.pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)

    def current_speaker_id() -> str | None:
        if ctx["api"] is None:
            return None
        ids = ctx.get("_ids") or []
        i = speaker_combo.current()
        if 0 <= i < len(ids):
            return ids[i]
        return None

    tts_var = tk.BooleanVar(value=not getattr(args, "no_tts", False))
    ttk.Checkbutton(main, text="Speak confirmations (POST /tts)", variable=tts_var).pack(
        anchor=tk.W, pady=(0, 8)
    )

    # --- Status + log ---
    status_var = tk.StringVar(value="Ready.")

    log_frame = ttk.Frame(main)
    log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
    ttk.Label(log_frame, text="Log", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
    log_box = scrolledtext.ScrolledText(
        log_frame,
        height=12,
        wrap="word",
        bg=_ENTRY_BG,
        fg=_FG,
        insertbackground=_FG,
        font=("Consolas", 9),
        relief=tk.FLAT,
    )
    log_box.pack(fill=tk.BOTH, expand=True)

    def append_log(line: str) -> None:
        log_box.insert(tk.END, line + "\n")
        log_box.see(tk.END)

    def drain_log_queue() -> None:
        try:
            while True:
                append_log(log_q.get_nowait())
        except queue.Empty:
            pass
        root.after(200, drain_log_queue)

    # --- Recording pipeline (runs on a worker thread) ---
    def _run_recording_worker(
        stop_event: threading.Event,
        device_idx: int | None,
        vad_enabled: bool,
        max_seconds: float,
        api_client: Any,
        embedded: Any,
        speaker_id: str | None,
        tts_enabled: bool,
    ) -> None:
        try:
            pcm, sr = capture_pcm(
                max_seconds=max_seconds,
                stop_event=stop_event,
                device=device_idx,
                vad_enabled=vad_enabled,
            )
            if not pcm:
                rec_result_q.put((None, None))
                return

            if api_client is not None:
                text = transcribe_pcm_via_api(pcm, sr, api_client=api_client)
            elif embedded is not None:
                from jamol.backend_rtv import transcribe_pcm_embedded

                text = transcribe_pcm_embedded(pcm, sr, embedded)
            else:
                rec_result_q.put((None, "No STT source configured."))
                return

            # handle_transcript may call TTS; do it on the worker to avoid blocking UI.
            if text:
                handle_transcript(
                    text,
                    apps,
                    tts_enabled=tts_enabled,
                    api_client=api_client,
                    speaker_id=speaker_id,
                    backend_settings=embedded,
                )
            rec_result_q.put((text, None))
        except Exception as e:  # noqa: BLE001
            logger.exception("Recording worker failed")
            rec_result_q.put((None, str(e)))

    def _poll_rec_result() -> None:
        try:
            text, err = rec_result_q.get_nowait()
        except queue.Empty:
            root.after(80, _poll_rec_result)
            return
        rec_state["busy"] = False
        ptt_btn.configure(style="PTT.TButton", text=f"Hold to speak  ({hotkey_var.get().upper()})")
        if err:
            status_var.set("Error.")
            append_log(f"Error: {err}")
            messagebox.showerror("Jamol", err, parent=root)
        elif not text:
            status_var.set("No speech detected.")
            append_log("(empty transcript)")
        else:
            status_var.set("Done.")
            append_log(f"Transcript: {text}")

    def _start_recording_if_ready() -> None:
        if rec_state["busy"]:
            return
        if ctx["api"] is None and ctx["embedded"] is None:
            messagebox.showinfo(
                "Jamol",
                "Click 'Apply / test connection' first (or enable Embedded with models installed).",
                parent=root,
            )
            return
        try:
            max_sec = float(max_sec_var.get().strip() or _DEFAULT_PHRASE_LIMIT)
        except ValueError:
            max_sec = _DEFAULT_PHRASE_LIMIT

        stop_event = threading.Event()
        rec_state["stop_event"] = stop_event
        rec_state["busy"] = True
        ptt_btn.configure(style="PTTHot.TButton", text="● Recording… release to stop")
        status_var.set("Recording… speak now.")

        worker = threading.Thread(
            target=_run_recording_worker,
            args=(
                stop_event,
                selected_device_index(),
                vad_var.get(),
                max_sec,
                ctx["api"],
                ctx["embedded"],
                current_speaker_id(),
                tts_var.get(),
            ),
            daemon=True,
        )
        rec_state["thread"] = worker
        worker.start()
        root.after(80, _poll_rec_result)

    def _stop_recording() -> None:
        ev = rec_state.get("stop_event")
        if ev is not None:
            ev.set()

    # --- Big PTT button with press/release semantics ---
    row_big = ttk.Frame(main)
    row_big.pack(fill=tk.X, pady=(0, 8))
    ptt_btn = ttk.Button(
        row_big,
        text=f"Hold to speak  ({_DEFAULT_HOTKEY.upper()})",
        style="PTT.TButton",
    )
    ptt_btn.pack(fill=tk.X, ipady=14)

    ptt_btn.bind("<ButtonPress-1>", lambda _e: _start_recording_if_ready())
    ptt_btn.bind("<ButtonRelease-1>", lambda _e: _stop_recording())
    root.bind("<KeyPress-space>", lambda _e: _start_recording_if_ready())
    root.bind("<KeyRelease-space>", lambda _e: _stop_recording())

    # --- Typed fallback ---
    typed_var = tk.StringVar()

    def run_typed() -> None:
        phrase = typed_var.get().strip()
        if not phrase:
            messagebox.showinfo("Jamol", "Enter a command phrase.", parent=root)
            return
        append_log(f"Typed: {phrase}")
        try:
            handle_transcript(
                phrase,
                apps,
                tts_enabled=tts_var.get(),
                api_client=ctx["api"],
                speaker_id=current_speaker_id(),
                backend_settings=ctx["embedded"],
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Typed command failed")
            messagebox.showerror("Jamol", str(e), parent=root)

    row_type = ttk.Frame(main)
    row_type.pack(fill=tk.X, pady=4)
    ttk.Label(row_type, text="Or type").pack(side=tk.LEFT)
    te = ttk.Entry(row_type, textvariable=typed_var)
    te.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
    ttk.Button(row_type, text="Run", command=run_typed).pack(side=tk.RIGHT)

    foot = ttk.Frame(main)
    foot.pack(fill=tk.X)
    ttk.Label(foot, textvariable=status_var, font=("Segoe UI", 9)).pack(side=tk.LEFT)
    ttk.Label(
        foot,
        text=f"Commands: {cfg_path}",
        style="Sub.TLabel",
    ).pack(side=tk.RIGHT)

    # --- Global hotkey wiring ---
    hotkey_holder: dict[str, PushToTalkHotkey | None] = {"h": None}

    def _hk_press() -> None:
        root.after(0, _start_recording_if_ready)

    def _hk_release() -> None:
        root.after(0, _stop_recording)

    def rearm_hotkey() -> None:
        if hotkey_holder["h"] is not None:
            hotkey_holder["h"].stop()
            hotkey_holder["h"] = None
        key = (hotkey_var.get() or "").strip() or _DEFAULT_HOTKEY
        ptt_btn.configure(text=f"Hold to speak  ({key.upper()})")
        if not hotkey_available():
            append_log("Global hotkey disabled: 'keyboard' package not installed.")
            return
        hk = PushToTalkHotkey(key, on_press=_hk_press, on_release=_hk_release)
        if hk.start():
            hotkey_holder["h"] = hk
            append_log(f"Global hotkey armed: {key.upper()} (hold to talk)")
        else:
            append_log(f"Could not arm global hotkey {key!r}.")

    def on_hotkey_entry_commit(_e: Any = None) -> None:
        rearm_hotkey()

    hotkey_var.trace_add("write", lambda *_: None)  # placeholder; rearm via button/FocusOut
    root.bind_all("<FocusOut>", lambda e: None)  # no-op, kept for future per-widget use

    # --- Connect / test ---
    def refresh_ctx() -> None:
        ns = argparse_mod.Namespace(
            engine=getattr(args, "engine", "backend"),
            embedded_audio=bool(embedded_var.get()),
            api_base=api_url_var.get().strip() or default_api_base(),
            api_key=(api_key_var.get().strip() or None) or default_api_key(),
        )
        a, e = resolve_audio(ns)
        ctx["api"] = a
        ctx["embedded"] = e
        ctx["voices"] = []
        ctx["_ids"] = []
        if a is not None:
            conn_lbl.config(text="● Connected (HTTP)", foreground="#3fb950")
            try:
                ctx["voices"] = a.list_voices()
                ids = [str(v.get("id", "")) for v in ctx["voices"]]
                labels = [str(v.get("label", v.get("id", ""))) for v in ctx["voices"]]
                speaker_combo["values"] = labels
                if ids:
                    # Prefer the user's override (--speaker-id / JAMOL_SPEAKER_ID),
                    # falling back to the Jamol default (Sardor — male Edge voice).
                    preferred = (
                        getattr(args, "speaker_id", None)
                        or DEFAULT_SPEAKER_ID
                    )
                    try:
                        preferred_idx = ids.index(preferred)
                    except ValueError:
                        preferred_idx = 0
                    speaker_combo.current(preferred_idx)
                ctx["_ids"] = ids
            except Exception as ex:  # noqa: BLE001
                append_log(f"Voices: {ex}")
        elif e is not None:
            conn_lbl.config(text="● Embedded STT/TTS", foreground="#dcdcaa")
        else:
            conn_lbl.config(text="● Not connected", foreground="#f85149")
            speaker_combo["values"] = []

    def do_apply() -> None:
        refresh_ctx()
        if ctx["api"] is None and ctx["embedded"] is None:
            messagebox.showwarning(
                "Jamol",
                "Could not reach the API and embedded models are not available.\n"
                "Start: cd backend && uvicorn app.main:app\n"
                "Or enable Embedded and install jamol[backend].",
                parent=root,
            )
        else:
            append_log("Connection updated.")
        rearm_hotkey()

    ttk.Button(btn_row, text="Apply / test connection", command=do_apply).pack(
        side=tk.RIGHT, padx=(8, 0)
    )
    ttk.Button(btn_row, text="Rearm hotkey", command=rearm_hotkey).pack(
        side=tk.RIGHT
    )

    on_embed_toggle()

    append_log("Click 'Apply / test connection', then hold the button (or press F9) to speak.")
    drain_log_queue()

    refresh_ctx()
    rearm_hotkey()
    if ctx["api"] is not None or ctx["embedded"] is not None:
        append_log("Ready (audio context loaded).")
    else:
        append_log("Warning: fix connection before using the microphone.")

    def _on_close() -> None:
        _stop_recording()
        if hotkey_holder["h"] is not None:
            hotkey_holder["h"].stop()
            hotkey_holder["h"] = None
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()
    root_logger.removeHandler(log_handler)
    return 0
