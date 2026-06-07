from __future__ import annotations

import json
import logging
import tkinter as tk
import tkinter.font as tkfont
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Theme (dark, cohesive with the overlay) ──────────────────────────────────
_BG       = "#1e1e2e"
_FG       = "#cdd6f4"
_NOTE_BG  = "#313244"
_EDITOR_BG= "#252538"
_STAMP_FG = "#6c7086"
_DEL_FG   = "#f38ba8"
_SAVE_FG  = "#a6e3a1"   # green — primary action
_SEP      = "#45475a"
_EMPTY_FG = "#585b70"


def _action_label(
    parent: tk.Widget,
    text: str,
    fg: str,
    command: Callable[[], None],
) -> tk.Label:
    """Small clickable label with a hover highlight."""
    lbl = tk.Label(
        parent,
        text=text,
        bg=_NOTE_BG,
        fg=fg,
        font=tkfont.Font(family="Segoe UI", size=8),
        cursor="hand2",
    )
    lbl.bind("<Button-1>", lambda _e: command())
    lbl.bind("<Enter>", lambda _e: lbl.config(fg=_FG))
    lbl.bind("<Leave>", lambda _e: lbl.config(fg=fg))
    return lbl


class NoteManager:
    """
    Voice-captured note storage (JSON) with a Toplevel notepad UI.

    Thread contract
    ---------------
    ``on_note()`` and ``open_window()`` are safe to call from any thread.
    All tkinter work is marshalled onto the main thread via the
    ``schedule_ui`` callable supplied at construction.
    """

    def __init__(
        self,
        schedule_ui: Callable[[Callable[[], None]], None],
        data_path: Path,
    ) -> None:
        self._schedule = schedule_ui
        self._path = data_path
        self._notes: list[dict] = self._load()
        self._win: tk.Toplevel | None = None
        self._scroll_frame: tk.Frame | None = None
        self._canvas_widget: tk.Canvas | None = None

    # ── Storage ───────────────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:
            logger.exception("Could not load notes from %s", self._path)
        return []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._notes, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Could not save notes to %s", self._path)

    # ── Public API ────────────────────────────────────────────────────────────

    def on_note(self, text: str | None) -> None:
        """Thread-safe.  text=None → just open notepad.  text=str → save + open."""
        if text:
            entry = {
                "id": str(uuid.uuid4()),
                "text": text.strip(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._notes.append(entry)
            self._save()
            logger.info("Note saved: %r", text)
        self._schedule(self._open_or_refresh)

    def open_window(self) -> None:
        """Thread-safe: open or bring the notepad to the front."""
        self._schedule(self._open_or_refresh)

    # ── UI (all methods below MUST run on the tk main thread) ─────────────────

    def _open_or_refresh(self) -> None:
        if self._win is None or not self._win.winfo_exists():
            self._build_window()
        else:
            self._refresh_list()
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()

    def _build_window(self) -> None:
        win = tk.Toplevel()
        win.title("Nova Notes")
        win.geometry("360x460")
        win.minsize(280, 200)
        win.configure(bg=_BG)
        win.wm_attributes("-topmost", True)
        # Close button hides the window; notes are preserved.
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        self._win = win

        # Header
        hdr = tk.Frame(win, bg=_BG)
        hdr.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(
            hdr,
            text="Nova Notes",
            font=tkfont.Font(family="Segoe UI", size=12, weight="bold"),
            bg=_BG,
            fg=_FG,
        ).pack(side="left")

        # Separator line
        tk.Frame(win, bg=_SEP, height=1).pack(fill="x", padx=8, pady=(0, 6))

        # Scrollable note list
        outer = tk.Frame(win, bg=_BG)
        outer.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        vbar = tk.Scrollbar(outer, orient="vertical")
        vbar.pack(side="right", fill="y")

        canvas = tk.Canvas(
            outer, bg=_BG, highlightthickness=0, bd=0, yscrollcommand=vbar.set
        )
        canvas.pack(side="left", fill="both", expand=True)
        vbar.config(command=canvas.yview)
        self._canvas_widget = canvas

        inner = tk.Frame(canvas, bg=_BG)
        self._scroll_frame = inner
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Keep inner frame as wide as the canvas
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        # Mousewheel: only active while cursor is over the list
        def _on_wheel(e: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        self._refresh_list()

    def _refresh_list(self) -> None:
        sf = self._scroll_frame
        if sf is None:
            return
        for widget in sf.winfo_children():
            widget.destroy()

        if not self._notes:
            tk.Label(
                sf,
                text='No notes yet.\nSay  "nova note <text>"  to capture an idea.',
                bg=_BG,
                fg=_EMPTY_FG,
                font=tkfont.Font(family="Segoe UI", size=9),
                justify="center",
            ).pack(pady=30)
            return

        # Newest first
        for entry in reversed(self._notes):
            self._note_row(entry)

        # Scroll to top so the newest note is visible
        if self._canvas_widget:
            self._canvas_widget.yview_moveto(0)

    # ── Note card (read mode) ─────────────────────────────────────────────────

    def _note_row(self, entry: dict) -> None:
        note_id = entry.get("id", "")
        text = entry.get("text", "")
        created_at = entry.get("created_at", "")

        try:
            stamp = datetime.fromisoformat(created_at).strftime("%d/%m/%Y  %H:%M")
        except (ValueError, TypeError):
            stamp = created_at

        card = tk.Frame(self._scroll_frame, bg=_NOTE_BG, padx=10, pady=6)
        card.pack(fill="x", padx=6, pady=3)
        card.columnconfigure(0, weight=1)

        self._render_read_mode(card, note_id, text, stamp)

    def _render_read_mode(
        self, card: tk.Frame, note_id: str, text: str, stamp: str
    ) -> None:
        # Top row: timestamp | Copy | Edit | ✕
        meta = tk.Frame(card, bg=_NOTE_BG)
        meta.grid(row=0, column=0, sticky="ew")
        meta.columnconfigure(0, weight=1)

        tk.Label(
            meta,
            text=stamp,
            bg=_NOTE_BG,
            fg=_STAMP_FG,
            font=tkfont.Font(family="Segoe UI", size=8),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        copy_lbl = _action_label(
            meta, "Copy", _STAMP_FG, lambda: self._copy(text)
        )
        copy_lbl.grid(row=0, column=1, sticky="e", padx=(6, 0))

        edit_lbl = _action_label(
            meta, "Edit", _STAMP_FG,
            lambda: self._start_edit(card, note_id, text, stamp),
        )
        edit_lbl.grid(row=0, column=2, sticky="e", padx=(6, 0))

        del_lbl = _action_label(
            meta, "✕", _DEL_FG, lambda: self._delete(note_id)
        )
        del_lbl.grid(row=0, column=3, sticky="e", padx=(6, 0))

        # Note body
        tk.Label(
            card,
            text=text,
            bg=_NOTE_BG,
            fg=_FG,
            font=tkfont.Font(family="Segoe UI", size=10),
            anchor="w",
            justify="left",
            wraplength=290,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

    # ── Note card (edit mode) ─────────────────────────────────────────────────

    def _start_edit(
        self, card: tk.Frame, note_id: str, current_text: str, stamp: str
    ) -> None:
        # Swap the card contents to edit mode without rebuilding the whole list.
        for widget in card.winfo_children():
            widget.destroy()

        # Timestamp row (read-only in edit mode)
        meta = tk.Frame(card, bg=_NOTE_BG)
        meta.grid(row=0, column=0, sticky="ew")
        meta.columnconfigure(0, weight=1)
        tk.Label(
            meta,
            text=stamp,
            bg=_NOTE_BG,
            fg=_STAMP_FG,
            font=tkfont.Font(family="Segoe UI", size=8),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # Text editor
        editor = tk.Text(
            card,
            height=3,
            wrap="word",
            bg=_EDITOR_BG,
            fg=_FG,
            insertbackground=_FG,
            selectbackground=_SEP,
            font=tkfont.Font(family="Segoe UI", size=10),
            relief="flat",
            padx=4,
            pady=4,
        )
        editor.insert("1.0", current_text)
        editor.mark_set("insert", "end")
        editor.grid(row=1, column=0, sticky="ew", pady=(4, 4))
        editor.focus_set()

        # Save / Cancel row
        btn_row = tk.Frame(card, bg=_NOTE_BG)
        btn_row.grid(row=2, column=0, sticky="e")

        def _do_save() -> None:
            new_text = editor.get("1.0", "end-1c").strip()
            if new_text:
                self._save_edit(note_id, new_text)
            else:
                self._refresh_list()  # empty → cancel

        # Keyboard shortcuts: Ctrl+Enter to save, Escape to cancel
        editor.bind("<Control-Return>", lambda _e: _do_save())
        editor.bind("<Escape>", lambda _e: self._refresh_list())

        save_lbl = _action_label(btn_row, "Save", _SAVE_FG, _do_save)
        save_lbl.grid(row=0, column=0, padx=(0, 6))

        cancel_lbl = _action_label(btn_row, "Cancel", _STAMP_FG, self._refresh_list)
        cancel_lbl.grid(row=0, column=1)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _copy(self, text: str) -> None:
        if self._win and self._win.winfo_exists():
            self._win.clipboard_clear()
            self._win.clipboard_append(text)
            logger.debug("Note copied to clipboard")

    def _save_edit(self, note_id: str, new_text: str) -> None:
        for note in self._notes:
            if note.get("id") == note_id:
                note["text"] = new_text
                note["edited_at"] = datetime.now().isoformat(timespec="seconds")
                break
        self._save()
        logger.info("Note edited: %r", new_text)
        self._refresh_list()

    def _delete(self, note_id: str) -> None:
        self._notes = [n for n in self._notes if n.get("id") != note_id]
        self._save()
        self._refresh_list()
