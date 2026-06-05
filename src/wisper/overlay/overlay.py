from __future__ import annotations

import ctypes
import logging
import math
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

logger = logging.getLogger(__name__)

_CHROMA = "#010102"
_CHROMA_RGB = (1, 1, 2)
_TEXT_COLOR = "#d0e4ff"
_WAVE_LO = (0x4A, 0x6E, 0xF5)
_WAVE_HI = (0x90, 0xB8, 0xFF)
_BAR_W, _BAR_G, _BAR_N = 3, 3, 5
_PAD, _RADIUS = 5, 29
_TICK_MS = 16
_FADE_SPEED = 0.048           # ~21 ticks = 336ms (morph duration)
_ANIM_FRAMES = 28             # pre-generated frames: drop → pill
_BAR_FREQS  = [1.00, 1.35, 0.75, 1.60, 0.90]
_BAR_PHASES = [0.00, 0.52, 1.15, 1.87, 2.44]


def _screen_bottom_center(width: int, height: int) -> tuple[int, int]:
    try:
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        return (sw - width) // 2, sh - height - 80
    except Exception:
        return 800, 960


def _lerp_color(lo: tuple[int, int, int], hi: tuple[int, int, int], t: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(lo[0] + t * (hi[0] - lo[0])),
        int(lo[1] + t * (hi[1] - lo[1])),
        int(lo[2] + t * (hi[2] - lo[2])),
    )


def _pill_body(w: int, h: int, shape_w: int, shape_h: int, radius: int) -> Image.Image:
    """Generates the gradient body + rounded mask for a shape (w×h canvas)."""
    cx = w // 2
    x1 = cx - shape_w // 2
    x2 = cx + shape_w // 2
    y1 = (h - shape_h) // 2
    y2 = y1 + shape_h

    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # Vertical gradient #252538 → #171728
    grad = Image.new("RGBA", (shape_w, shape_h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for yy in range(shape_h):
        tv = yy / max(shape_h - 1, 1)
        rv = int(0x25 * (1 - tv) + 0x17 * tv)
        bv = int(0x38 * (1 - tv) + 0x28 * tv)
        gd.line([(0, yy), (shape_w, yy)], fill=(rv, rv, bv, 255))

    mask = Image.new("L", (shape_w, shape_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, shape_w - 1, shape_h - 1], radius=radius, fill=255
    )
    grad.putalpha(mask)
    base.paste(grad, (x1, y1), grad)

    # White border + top highlight
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle(
        [x1, y1, x2 - 1, y2 - 1], radius=radius, outline=(255, 255, 255, 36), width=1
    )
    od.line([(x1 + radius, y1 + 1), (x2 - radius, y1 + 1)], fill=(255, 255, 255, 56))
    base.alpha_composite(ov)

    return base


def _composite(img: Image.Image, w: int, h: int) -> ImageTk.PhotoImage:
    """Composites RGBA onto chroma background → transparent pixels = #010102."""
    bg = Image.new("RGBA", (w, h), (*_CHROMA_RGB, 255))
    return ImageTk.PhotoImage(Image.alpha_composite(bg, img).convert("RGB"))


def _make_morph_frames(w: int, h: int) -> list[ImageTk.PhotoImage]:
    """
    Pre-generates _ANIM_FRAMES images:
      frame 0   = small drop (near-circle, centered)
      frame N-1 = full pill

    The shape starts as a slightly elongated vertical oval (water drop),
    then widens into a pill via smoothstep easing.
    """
    ph = h - 2 * _PAD          # final pill height
    pw = w - 2 * _PAD          # final pill width
    drop_w = int(ph * 0.82)    # initial width: slightly narrower = drop shape

    frames: list[ImageTk.PhotoImage] = []
    for i in range(_ANIM_FRAMES):
        t = i / max(_ANIM_FRAMES - 1, 1)
        # Smoothstep: eases in and out
        ts = t * t * (3 - 2 * t)

        shape_w = int(drop_w + ts * (pw - drop_w))
        shape_h = ph
        r = min(shape_w // 2, shape_h // 2, int(_RADIUS * ts + shape_w // 2 * (1 - ts)))
        r = max(1, r)

        img = _pill_body(w, h, shape_w, shape_h, r)
        frames.append(_composite(img, w, h))

    return frames


class OverlayHUD:
    """
    Glass pill anchored at bottom-center.
    Appear animation: drop rises from below → morphs into pill (PIL frames).
    Transparency via wm_attributes('-transparentcolor') + GDI chroma key.
    """

    def __init__(self, width: int = 310, height: int = 58) -> None:
        self._width = width
        self._height = height
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._morph_frames: list[ImageTk.PhotoImage] = []
        self._pill_img_id: int = 0
        self._bars: list[int] = []
        self._text_id: int = 0
        self._visible = False
        self._current_text = ""
        self._type_after: str | None = None
        self._fade_raw = 0.0
        self._tick_count = 0
        self._base_x = 0
        self._base_y = 0
        self._wave_x = 0
        self._font: tkfont.Font | None = None
        self._text_max_w = 0  # max available text width (px)

    def create_window(self) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.wm_attributes("-topmost", True)
        self._root.wm_attributes("-transparentcolor", _CHROMA)
        self._root.wm_attributes("-alpha", 0.0)
        self._root.configure(bg=_CHROMA)

        self._base_x, self._base_y = _screen_bottom_center(self._width, self._height)
        self._root.geometry(f"{self._width}x{self._height}+{self._base_x}+{self._base_y}")

        self._canvas = tk.Canvas(
            self._root,
            width=self._width,
            height=self._height,
            bg=_CHROMA,
            highlightthickness=0,
        )
        self._canvas.pack()
        self._root.bind_all("<Escape>", lambda _e: self._root.destroy())

        # Pre-generate frames (drop → pill)
        self._morph_frames = _make_morph_frames(self._width, self._height)
        self._build_pill()
        self._root.after(_TICK_MS, self._tick)

    def _build_pill(self) -> None:
        assert self._canvas is not None
        c = self._canvas
        c.delete("all")

        # Initial image = frame 0 (drop)
        self._pill_img_id = c.create_image(0, 0, anchor="nw", image=self._morph_frames[0])

        # Waveform bars
        cy = self._height // 2
        self._wave_x = _PAD + 14
        self._bars = []
        for i in range(_BAR_N):
            bx = self._wave_x + i * (_BAR_W + _BAR_G)
            bid = c.create_rectangle(
                bx, cy - 3, bx + _BAR_W, cy + 3,
                fill=_lerp_color(_WAVE_LO, _WAVE_HI, 0.5),
                outline="",
                state="hidden",
            )
            self._bars.append(bid)

        # Text
        text_x = self._wave_x + _BAR_N * (_BAR_W + _BAR_G) + 10
        self._font = tkfont.Font(family="Segoe UI", size=10)
        self._text_max_w = self._width - text_x - _PAD - 8
        self._text_id = c.create_text(
            text_x, cy,
            text="",
            fill=_TEXT_COLOR,
            font=self._font,
            anchor="w",
            state="hidden",
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Blocks on the tkinter mainloop."""
        if self._root:
            self._root.mainloop()

    def show(self) -> None:
        self._visible = True
        if self._root:
            self._root.after(0, self._on_show)

    def hide(self) -> None:
        self._visible = False

    def update(self, text: str) -> None:
        if self._root and self._visible:
            self._root.after(0, self._start_type, text)

    def close(self) -> None:
        if self._root:
            self._root.after(0, self._root.destroy)

    def _on_show(self) -> None:
        if self._root is None or self._canvas is None:
            return
        self._canvas.itemconfig(self._text_id, text="", state="hidden")
        for bid in self._bars:
            self._canvas.itemconfig(bid, state="hidden")
        self._current_text = ""
        self._root.deiconify()

    # ── Main loop 60 fps ─────────────────────────────────────────────────────

    def _tick(self) -> None:
        if self._root is None:
            return

        target = 1.0 if self._visible else 0.0
        delta = target - self._fade_raw
        if abs(delta) > 0.001:
            self._fade_raw += math.copysign(min(abs(delta), _FADE_SPEED), delta)
            self._fade_raw = max(0.0, min(1.0, self._fade_raw))

        t = self._fade_raw

        if t > 0.001:
            # Morph frame: drop (0) → full pill (N-1)
            fi = int(min(t, 0.9999) * _ANIM_FRAMES)
            self._canvas.itemconfig(self._pill_img_id, image=self._morph_frames[fi])  # type: ignore[union-attr]

            # Alpha: fast in, fast out
            alpha = 1.0 - (1.0 - t) ** 2 if self._visible else t ** 2

            # Rise: drop lifts from 40px below, ease-out
            y_rise = int(40 * (1.0 - t) ** 1.6)

            self._root.wm_attributes("-alpha", alpha)
            self._root.geometry(
                f"{self._width}x{self._height}+{self._base_x}+{self._base_y + y_rise}"
            )

            # Bars and text visible only once pill is formed (t > 85%)
            formed = t > 0.85
            state = "normal" if formed else "hidden"
            if self._canvas:
                self._canvas.itemconfig(self._text_id, state=state)
                for bid in self._bars:
                    self._canvas.itemconfig(bid, state=state)
            if formed:
                self._update_bars()

        elif not self._visible:
            self._root.withdraw()
            self._current_text = ""
            if self._canvas:
                self._canvas.itemconfig(self._text_id, text="", state="hidden")
                for bid in self._bars:
                    self._canvas.itemconfig(bid, state="hidden")

        self._tick_count += 1
        self._root.after(_TICK_MS, self._tick)

    def _update_bars(self) -> None:
        if self._canvas is None:
            return
        t = self._tick_count * _TICK_MS / 1000.0
        cy = self._height // 2
        for i, bid in enumerate(self._bars):
            h = 2 + int(6 * (
                0.6 * (0.5 + 0.5 * math.sin(t * _BAR_FREQS[i] * 5.0 + _BAR_PHASES[i])) +
                0.4 * abs(math.sin(t * _BAR_FREQS[i] * 2.3 + _BAR_PHASES[i] * 0.7))
            ))
            bx = self._wave_x + i * (_BAR_W + _BAR_G)
            self._canvas.coords(bid, bx, cy - h, bx + _BAR_W, cy + h)
            self._canvas.itemconfig(bid, fill=_lerp_color(_WAVE_LO, _WAVE_HI, h / 8.0))

    # ── Typewriter ───────────────────────────────────────────────────────────

    def _start_type(self, text: str) -> None:
        if self._type_after and self._root:
            self._root.after_cancel(self._type_after)
            self._type_after = None
        full = text or ""
        cur = self._current_text or ""

        if full == cur:
            return  # nothing to do

        if cur.startswith(full):
            # ASR shortened the text (correction) truncate without retyping
            self._current_text = full
            if self._canvas:
                self._canvas.itemconfig(self._text_id, text=self._visible_text(full))
            return

        # Common prefix: avoids restarting from scratch on minor corrections
        common = 0
        for a, b in zip(cur, full):
            if a == b:
                common += 1
            else:
                break

        self._current_text = full[:common]
        if common == 0 and self._canvas:
            self._canvas.itemconfig(self._text_id, text="")
        self._type_char(full, common)

    def _type_char(self, full: str, i: int) -> None:
        if not self._visible or self._root is None or self._canvas is None:
            return
        self._current_text = full[:i]
        self._canvas.itemconfig(self._text_id, text=self._visible_text(self._current_text))
        if i < len(full):
            self._type_after = self._root.after(26, self._type_char, full, i + 1)

    def _visible_text(self, text: str) -> str:
        """Truncates from the start with '…' if text exceeds available width."""
        if not self._font or not text:
            return text
        if self._font.measure(text) <= self._text_max_w:
            return text
        t = text
        while t and self._font.measure("…" + t) > self._text_max_w:
            t = t[1:]
        return "…" + t
