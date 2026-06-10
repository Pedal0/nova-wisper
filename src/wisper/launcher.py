from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.font as tkfont
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Theme (matches notes.py) ──────────────────────────────────────────────────
_BG        = "#1e1e2e"
_FG        = "#cdd6f4"
_ITEM_BG   = "#313244"
_EDITOR_BG = "#252538"
_STAMP_FG  = "#6c7086"
_DEL_FG    = "#f38ba8"
_SAVE_FG   = "#a6e3a1"
_SEP       = "#45475a"
_EMPTY_FG  = "#585b70"

_DEFAULT_LLM: dict[str, str] = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
}
_LLM_TIMEOUT = 15  # seconds


# ── Pure helpers (testable without UI or network) ─────────────────────────────

def _extract_json(text: str) -> dict | None:
    """
    Extract the first JSON object from a potentially messy LLM response.

    Handles:
    - Markdown code fences: ```json ... ``` or ``` ... ```
    - Leading prose: "Sure, here's what you need: {...}"
    - Trailing content after the object
    - Single-quoted keys/values (Python dict syntax from tiny models)
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    # Try direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Find first {...} block (handles leading/trailing prose)
    m = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
    if m:
        block = m.group(0)
        # Try the block as-is (standard JSON)
        try:
            result = json.loads(block)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        # Single-quote fallback on the block *only* — never on the whole string,
        # which would corrupt prose apostrophes like "Here's" → "Here"s".
        try:
            result = json.loads(block.replace("'", '"'))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None


def _extract_commands(text: str) -> list[dict]:
    """
    Extract one or more {app_name, action} commands from LLM output.

    Handles:
    - JSON array  [{"app_name": "Discord", "action": "open"}, ...]
    - Single dict {"app_name": "Discord", "action": "open"}
    - Markdown fences, prose prefix/suffix, single-quoted dicts
    - Any number of commands in one response
    """
    # Strip markdown code fences first
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    def _parse_item(obj: object) -> dict | None:
        if isinstance(obj, dict) and "app_name" in obj and "action" in obj:
            return obj
        return None

    # 1. Direct parse — handles clean array or single dict
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [r for r in map(_parse_item, parsed) if r]
        item = _parse_item(parsed)
        if item:
            return [item]
    except json.JSONDecodeError:
        pass

    # 2. Find a [...] array anywhere in the text
    m_arr = re.search(r"\[.*?\]", cleaned, re.DOTALL)
    if m_arr:
        try:
            parsed = json.loads(m_arr.group(0))
            if isinstance(parsed, list):
                items = [r for r in map(_parse_item, parsed) if r]
                if items:
                    return items
        except json.JSONDecodeError:
            pass

    # 3. Collect every {...} block — single-command responses and tiny-model output
    commands: list[dict] = []
    for block in re.findall(r"\{[^{}]*\}", cleaned):
        for candidate in (block, block.replace("'", '"')):
            try:
                item = _parse_item(json.loads(candidate))
                if item and item not in commands:
                    commands.append(item)
                    break
            except json.JSONDecodeError:
                pass
    return commands


def _call_llm(text: str, app_names: list[str], llm_cfg: dict) -> list[dict]:
    """
    Single OpenAI-compatible POST to /v1/chat/completions.

    No tool calls — plain text response only, so this works with every model
    and every provider (OpenAI, Ollama, OpenRouter, OpenRouter free tier, etc.).

    Supports chained commands: "nova open Discord and Steam" returns two items.

    Returns list of {"app_name": "...", "action": "open"|"close"} dicts (empty on failure).
    Raises urllib.error.HTTPError / urllib.error.URLError on network failures.
    """
    system_prompt = (
        f"You control desktop applications. "
        f"Available apps: {app_names}. "
        "Based on the voice command, decide which apps to open or close. "
        "Words meaning OPEN: open, launch, start, ouvre, lance, démarre, ouvrir, lancer. "
        "Words meaning CLOSE: close, quit, exit, ferme, quitte, arrête, fermer, quitter. "
        "Reply ONLY with a JSON array — no prose, no markdown, no explanation. "
        "One element per app mentioned. Example: "
        '[{"app_name": "Discord", "action": "open"}, {"app_name": "Steam", "action": "open"}]'
    )

    payload = {
        "model": llm_cfg.get("model", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
    }

    # Accept either the bare base URL (https://openrouter.ai/api/v1) or a full
    # endpoint URL (https://openrouter.ai/api/v1/chat/completions) so the user
    # doesn't have to know the exact format.
    _base = llm_cfg.get("base_url", "").rstrip("/")
    if _base.endswith("/chat/completions"):
        url = _base
    else:
        url = _base + "/chat/completions"

    logger.info("LLM request → %s  model=%s", url, payload["model"])
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm_cfg.get('api_key') or 'none'}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=_LLM_TIMEOUT) as resp:
        data = json.loads(resp.read())

    content = data["choices"][0]["message"].get("content", "") or ""

    # Reasoning models prepend a think-block before the actual answer.
    # Different models use different tag names — strip them all so _extract_json
    # only sees the final answer, not intermediate reasoning that may contain
    # wrong candidate JSON objects.
    # Known formats:  <think>  <thinking>  <thought>  <reasoning>
    cleaned_content = re.sub(
        r"<(?:think|thinking|thought|reasoning)>.*?</(?:think|thinking|thought|reasoning)>",
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()

    commands = _extract_commands(cleaned_content)
    logger.info(
        "LLM response — raw: %r  →  parsed: %r",
        cleaned_content[:300],
        commands,
    )
    return commands


class AppLauncher:
    """
    Voice-triggered app opener/closer + management UI.

    Data stored in launcher.json (next to Nova.exe or at project root in dev):
        {
          "llm": {"base_url": "...", "api_key": "...", "model": "..."},
          "apps": [{"name": "Discord", "path": "C:/..."}, ...]
        }

    Thread contract
    ---------------
    handle() and open_window() are safe to call from any thread.
    All tkinter work is marshalled onto the main thread via schedule_ui
    (which wraps overlay.schedule → root.after(0, func)).
    """

    def __init__(
        self,
        schedule_ui: Callable[[Callable[[], None]], None],
        overlay,           # OverlayHUD — used for flash() feedback messages
        data_path: Path,
    ) -> None:
        self._schedule = schedule_ui
        self._overlay = overlay
        self._path = data_path
        self._data = self._load()
        self._win: tk.Toplevel | None = None
        self._status_var: tk.StringVar | None = None
        self._status_label: tk.Label | None = None
        self._app_list_frame: tk.Frame | None = None
        self._app_canvas: tk.Canvas | None = None

    # ── Storage ───────────────────────────────────────────────────────────────

    @property
    def _llm(self) -> dict:
        return self._data.setdefault("llm", dict(_DEFAULT_LLM))

    @property
    def _apps(self) -> list[dict]:
        return self._data.setdefault("apps", [])

    def _load(self) -> dict:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            logger.exception("Could not load launcher data from %s", self._path)
        return {"llm": dict(_DEFAULT_LLM), "apps": []}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Could not save launcher data to %s", self._path)

    # ── Public API ────────────────────────────────────────────────────────────

    def handle(self, text: str) -> None:
        """
        Thread-safe.  Route a voice command through the LLM and execute the action.

        If the LLM config is missing or no apps are registered, opens the
        settings popup with an explanatory message instead of crashing.
        """
        if not self._llm.get("api_key"):
            self._schedule(
                lambda: self._open_window(
                    status="API key not configured.", ok=False
                )
            )
            return
        if not self._apps:
            self._schedule(
                lambda: self._open_window(
                    status="No apps registered yet. Add some first.", ok=False
                )
            )
            return
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def open_window(self) -> None:
        """Thread-safe: open the settings popup."""
        self._schedule(lambda: self._open_window())

    # ── LLM + action (background thread) ─────────────────────────────────────

    def _run(self, text: str) -> None:
        """Background thread: call the LLM, parse the result, execute the action."""
        # Show what Nova heard while the LLM processes (wave bars + typewriter).
        # Strips the "nova" trigger word so only the intent is shown:
        #   "Nova lance Discord et Steam" → "lance Discord et Steam"
        preview = text.strip().rstrip(".,!?;:")
        if preview.lower().startswith("nova"):
            preview = preview[4:].lstrip(" ,").strip()
        self._overlay.flash(preview, duration_ms=30000)

        try:
            commands = _call_llm(text, [a["name"] for a in self._apps], self._llm)
        except urllib.error.HTTPError as exc:
            # Read the response body — it contains the provider's error message
            # (e.g. "model not found", "invalid API key") which is far more
            # useful than the bare HTTP status string.
            try:
                body = exc.read().decode(errors="replace")
            except Exception:
                body = ""
            logger.error("LLM HTTP %s %s — %s", exc.code, exc.reason, body)
            short = body[:120] if body else exc.reason
            self._overlay.flash(f"LLM {exc.code}: {short}", duration_ms=5000)
            return
        except urllib.error.URLError as exc:
            logger.error("LLM connection error: %s", exc)
            self._overlay.flash(
                f"LLM error: {getattr(exc, 'reason', exc)}", duration_ms=3500
            )
            return
        except Exception as exc:
            logger.exception("Unexpected LLM error")
            self._overlay.flash(f"Error: {exc}", duration_ms=3500)
            return

        if not commands:
            self._overlay.flash("Could not parse LLM response.", duration_ms=3000)
            return

        feedback: list[str] = []
        not_found: list[str] = []

        for cmd in commands:
            app_name = cmd.get("app_name", "")
            action   = cmd.get("action", "")

            app = next(
                (a for a in self._apps if a["name"].lower() == app_name.lower()),
                None,
            )
            if app is None:
                logger.warning("LLM returned an app not in the registry: %r", app_name)
                not_found.append(app_name)
                continue

            verb = "Launching" if action == "open" else "Closing"
            logger.info("%s %s (path: %s)", verb, app["name"], app["path"])
            feedback.append(f"{verb} {app['name']}")

            try:
                if action == "open":
                    os.startfile(app["path"])  # noqa: S606
                elif action == "close":
                    if app.get("exe"):
                        exe_name = app["exe"]
                    else:
                        p = Path(app["path"])
                        exe_name = (p.stem + ".exe") if p.suffix.lower() == ".lnk" else p.name
                    logger.info("taskkill /f /im %s", exe_name)
                    subprocess.run(
                        ["taskkill", "/f", "/im", exe_name],
                        capture_output=True,
                        check=False,
                    )
                else:
                    logger.warning("LLM returned an unknown action: %r", action)
            except Exception as exc:
                logger.exception("Failed to %s %s", action, app["name"])
                feedback.append(f"Failed: {exc}")

        # Show one combined overlay message for all commands
        if not_found:
            feedback.append(f"Not found: {', '.join(not_found)}")
        if feedback:
            duration = 2000 + len(feedback) * 500
            self._overlay.flash(", ".join(feedback) + "...", duration_ms=duration)

    # ── UI (all methods MUST run on the tk main thread) ───────────────────────

    def _open_window(self, status: str = "", ok: bool = True) -> None:
        if self._win is None or not self._win.winfo_exists():
            self._build_window()
        else:
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()

        if status and self._status_var:
            if self._status_label:
                self._status_label.config(fg=_SAVE_FG if ok else _DEL_FG)
            self._status_var.set(status)

    def _build_window(self) -> None:
        win = tk.Toplevel()
        win.title("App Launcher")
        win.geometry("420x560")
        win.minsize(360, 420)
        win.configure(bg=_BG)
        win.wm_attributes("-topmost", True)
        # Closing hides the window so settings are preserved
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        self._win = win

        # ── Header ─────────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=_BG)
        hdr.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(
            hdr,
            text="App Launcher",
            font=tkfont.Font(family="Segoe UI", size=12, weight="bold"),
            bg=_BG, fg=_FG,
        ).pack(side="left")

        tk.Frame(win, bg=_SEP, height=1).pack(fill="x", padx=8, pady=(0, 8))

        # ── LLM Configuration ──────────────────────────────────────────────────
        self._build_llm_section(win)

        tk.Frame(win, bg=_SEP, height=1).pack(fill="x", padx=8, pady=(8, 8))

        # ── Registered apps + add form ─────────────────────────────────────────
        self._build_apps_section(win)

        # ── Status bar ─────────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="")
        self._status_label = tk.Label(
            win,
            textvariable=self._status_var,
            bg=_BG, fg=_STAMP_FG,
            font=tkfont.Font(family="Segoe UI", size=8),
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=12, pady=(4, 8))

    def _build_llm_section(self, parent: tk.Widget) -> None:
        section = tk.Frame(parent, bg=_BG)
        section.pack(fill="x", padx=12)

        tk.Label(
            section, text="LLM Configuration",
            bg=_BG, fg=_STAMP_FG,
            font=tkfont.Font(family="Segoe UI", size=9, weight="bold"),
        ).pack(anchor="w", pady=(0, 6))

        fields: list[tuple[str, str, bool]] = [
            ("Base URL", "base_url", False),
            ("API Key",  "api_key",  True),
            ("Model",    "model",    False),
        ]
        entries: dict[str, tk.Entry] = {}

        for label, key, secret in fields:
            row = tk.Frame(section, bg=_BG)
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=label,
                bg=_BG, fg=_FG,
                font=tkfont.Font(family="Segoe UI", size=9),
                width=9, anchor="w",
            ).pack(side="left")
            entry = tk.Entry(
                row,
                bg=_EDITOR_BG, fg=_FG, insertbackground=_FG,
                relief="flat",
                font=tkfont.Font(family="Segoe UI", size=9),
                show="*" if secret else "",
            )
            entry.insert(0, self._llm.get(key, ""))
            entry.pack(side="left", fill="x", expand=True)
            entries[key] = entry

        def _save_llm() -> None:
            for key, entry in entries.items():
                self._llm[key] = entry.get().strip()
            self._save()
            if self._status_var:
                if self._status_label:
                    self._status_label.config(fg=_SAVE_FG)
                self._status_var.set("LLM settings saved.")

        save_btn = tk.Label(
            section, text="Save",
            bg=_ITEM_BG, fg=_SAVE_FG,
            font=tkfont.Font(family="Segoe UI", size=9),
            cursor="hand2", padx=8, pady=3,
        )
        save_btn.pack(anchor="e", pady=(6, 0))
        save_btn.bind("<Button-1>", lambda _e: _save_llm())

    def _build_apps_section(self, parent: tk.Widget) -> None:
        section = tk.Frame(parent, bg=_BG)
        section.pack(fill="both", expand=True, padx=12)

        tk.Label(
            section, text="Registered Apps",
            bg=_BG, fg=_STAMP_FG,
            font=tkfont.Font(family="Segoe UI", size=9, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        # ── Scrollable app list (fixed height 150px) ────────────────────────────
        list_outer = tk.Frame(section, bg=_BG, height=150)
        list_outer.pack(fill="x")
        list_outer.pack_propagate(False)

        vbar = tk.Scrollbar(list_outer, orient="vertical")
        vbar.pack(side="right", fill="y")

        self._app_canvas = tk.Canvas(
            list_outer, bg=_BG, highlightthickness=0, bd=0,
            yscrollcommand=vbar.set,
        )
        self._app_canvas.pack(side="left", fill="both", expand=True)
        vbar.config(command=self._app_canvas.yview)

        self._app_list_frame = tk.Frame(self._app_canvas, bg=_BG)
        inner_id = self._app_canvas.create_window(
            (0, 0), window=self._app_list_frame, anchor="nw"
        )

        self._app_canvas.bind(
            "<Configure>",
            lambda e: self._app_canvas.itemconfig(inner_id, width=e.width),
        )
        self._app_list_frame.bind(
            "<Configure>",
            lambda e: self._app_canvas.configure(
                scrollregion=self._app_canvas.bbox("all")
            ),
        )

        def _on_wheel(e: tk.Event) -> None:
            self._app_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        self._app_canvas.bind(
            "<Enter>", lambda _e: self._app_canvas.bind_all("<MouseWheel>", _on_wheel)
        )
        self._app_canvas.bind(
            "<Leave>", lambda _e: self._app_canvas.unbind_all("<MouseWheel>")
        )

        self._refresh_app_list()

        # ── Add-app form ────────────────────────────────────────────────────────
        tk.Frame(section, bg=_SEP, height=1).pack(fill="x", pady=(8, 6))

        form = tk.Frame(section, bg=_BG)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        tk.Label(
            form, text="Name",
            bg=_BG, fg=_FG,
            font=tkfont.Font(family="Segoe UI", size=9),
            anchor="w", width=5,
        ).grid(row=0, column=0, sticky="w", pady=2, padx=(0, 6))

        name_var = tk.StringVar()
        name_entry = tk.Entry(
            form, textvariable=name_var,
            bg=_EDITOR_BG, fg=_FG, insertbackground=_FG,
            relief="flat", font=tkfont.Font(family="Segoe UI", size=9),
        )
        name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)

        tk.Label(
            form, text="Path",
            bg=_BG, fg=_FG,
            font=tkfont.Font(family="Segoe UI", size=9),
            anchor="w", width=5,
        ).grid(row=1, column=0, sticky="w", pady=2, padx=(0, 6))

        path_var = tk.StringVar()
        path_entry = tk.Entry(
            form, textvariable=path_var,
            bg=_EDITOR_BG, fg=_FG, insertbackground=_FG,
            relief="flat", font=tkfont.Font(family="Segoe UI", size=9),
        )
        path_entry.grid(row=1, column=1, sticky="ew", pady=2, padx=(0, 4))

        # ── Process field (row 2) ──────────────────────────────────────────────
        tk.Label(
            form, text="Process",
            bg=_BG, fg=_FG,
            font=tkfont.Font(family="Segoe UI", size=9),
            anchor="w", width=5,
        ).grid(row=2, column=0, sticky="w", pady=2, padx=(0, 6))

        exe_var = tk.StringVar()
        exe_entry = tk.Entry(
            form, textvariable=exe_var,
            bg=_EDITOR_BG, fg=_STAMP_FG, insertbackground=_FG,
            relief="flat", font=tkfont.Font(family="Segoe UI", size=9),
        )
        exe_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=2)

        # Hint label under the process field
        tk.Label(
            form,
            text="Process name for taskkill (e.g. chrome.exe). Leave blank to auto-detect.",
            bg=_BG, fg=_EMPTY_FG,
            font=tkfont.Font(family="Segoe UI", size=7),
            anchor="w", wraplength=300, justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 2))

        def _browse() -> None:
            path = fd.askopenfilename(
                parent=self._win,
                title="Select application",
                filetypes=[("Application", "*.exe *.lnk"), ("All files", "*.*")],
            )
            if path:
                path_var.set(path)
                # Auto-fill process name for .exe — leave blank for .lnk so
                # the user knows they need to fill it in.
                if path.lower().endswith(".exe") and not exe_var.get().strip():
                    exe_var.set(Path(path).name)

        browse_btn = tk.Label(
            form, text="...",
            bg=_ITEM_BG, fg=_FG,
            font=tkfont.Font(family="Segoe UI", size=9),
            cursor="hand2", padx=6, pady=2,
        )
        browse_btn.grid(row=1, column=2, pady=2)
        browse_btn.bind("<Button-1>", lambda _e: _browse())

        def _add() -> None:
            name = name_var.get().strip()
            path = path_var.get().strip()
            if not name or not path:
                if self._status_var and self._status_label:
                    self._status_label.config(fg=_DEL_FG)
                    self._status_var.set("Name and path are required.")
                return
            entry: dict = {"name": name, "path": path}
            exe = exe_var.get().strip()
            if exe:
                entry["exe"] = exe
            self._apps.append(entry)
            self._save()
            name_var.set("")
            path_var.set("")
            exe_var.set("")
            self._refresh_app_list()
            if self._status_var and self._status_label:
                self._status_label.config(fg=_SAVE_FG)
                self._status_var.set(f"Added: {name}")

        # Tab / Enter navigation in the add form
        name_entry.bind("<Return>", lambda _e: path_entry.focus_set())
        path_entry.bind("<Return>", lambda _e: exe_entry.focus_set())
        exe_entry.bind("<Return>", lambda _e: _add())

        add_btn = tk.Label(
            section, text="Add App",
            bg=_ITEM_BG, fg=_SAVE_FG,
            font=tkfont.Font(family="Segoe UI", size=9),
            cursor="hand2", padx=8, pady=3,
        )
        add_btn.pack(anchor="e", pady=(6, 0))
        add_btn.bind("<Button-1>", lambda _e: _add())

    def _refresh_app_list(self) -> None:
        frame = self._app_list_frame
        if frame is None:
            return
        for widget in frame.winfo_children():
            widget.destroy()

        if not self._apps:
            tk.Label(
                frame,
                text='No apps yet. Add one below.\nSay "nova open Discord" to launch.',
                bg=_BG, fg=_EMPTY_FG,
                font=tkfont.Font(family="Segoe UI", size=9),
                justify="center",
            ).pack(pady=12)
            return

        for app in self._apps:
            row = tk.Frame(frame, bg=_ITEM_BG, padx=8, pady=4)
            row.pack(fill="x", pady=2, padx=2)
            row.columnconfigure(0, weight=1)

            tk.Label(
                row, text=app.get("name", ""),
                bg=_ITEM_BG, fg=_FG,
                font=tkfont.Font(family="Segoe UI", size=9, weight="bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w")

            subtitle = app.get("path", "")
            if app.get("exe"):
                subtitle += f"  •  {app['exe']}"
            tk.Label(
                row, text=subtitle,
                bg=_ITEM_BG, fg=_STAMP_FG,
                font=tkfont.Font(family="Segoe UI", size=8),
                anchor="w",
            ).grid(row=1, column=0, sticky="w")

            del_lbl = tk.Label(
                row, text="✕",
                bg=_ITEM_BG, fg=_DEL_FG,
                font=tkfont.Font(family="Segoe UI", size=9),
                cursor="hand2",
            )
            del_lbl.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
            del_lbl.bind(
                "<Button-1>",
                lambda _e, name=app["name"]: self._remove_app(name),
            )

    def _remove_app(self, name: str) -> None:
        self._data["apps"] = [a for a in self._apps if a["name"] != name]
        self._save()
        self._refresh_app_list()
        if self._status_var and self._status_label:
            self._status_label.config(fg=_STAMP_FG)
            self._status_var.set(f"Removed: {name}")
