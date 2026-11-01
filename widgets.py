import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

import downloader

# ---------- tema ----------

BG = "#121212"
SIDEBAR = "#000000"
SURFACE = "#1c1c1c"
HOVER = "#262626"
FIELD = "#2a2a2a"
BAR = "#0b0b0b"
TEXT = "#ffffff"
SUBTEXT = "#b3b3b3"
MUTED = "#727272"
ACCENT = "#8b5cf6"
ACCENT_LIGHT = "#b49bff"
HEART = ACCENT_LIGHT
DONE = "#34d399"
DANGER = "#f87171"

FONT = "Segoe UI"
ICON_FONT = "Segoe UI Symbol"

TILE_COLORS = ["#5b3fd1", "#c2410c", "#0f766e", "#b91c1c", "#1d4ed8", "#a16207", "#be185d", "#4d7c0f"]


def font(size=10, weight="normal"):
    return (FONT, size, weight)


def icon_font(size=12):
    return (ICON_FONT, size)


def fmt_time(seconds):
    seconds = int(max(seconds or 0, 0))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes}:{secs:02}"


def shorten(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def mix(color_a, color_b, amount):
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def tile_color(key):
    return TILE_COLORS[sum(map(ord, key)) % len(TILE_COLORS)]


def setup_style(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Dark.Vertical.TScrollbar",
        background="#3a3a3a", troughcolor=BG, bordercolor=BG,
        lightcolor="#3a3a3a", darkcolor="#3a3a3a", arrowcolor=BG, gripcount=0, width=10,
    )
    style.map("Dark.Vertical.TScrollbar", background=[("active", "#555555")])
    style.layout("Dark.Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})
    ])


def round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def bind_tree(widget, sequence, handler):
    """Bir bileşene ve tüm alt bileşenlerine aynı olayı bağla."""
    widget.bind(sequence, handler, add="+")
    for child in widget.winfo_children():
        bind_tree(child, sequence, handler)


def paint_tree(widget, bg):
    try:
        widget.config(bg=bg)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        paint_tree(child, bg)


def bind_hover(frame, callback):
    """Fare çerçevenin (veya alt bileşenlerinin) üzerine gelince/ayrılınca callback(True/False)."""
    state = {"inside": False}

    def enter(event):
        if not state["inside"]:
            state["inside"] = True
            callback(True)

    def check():
        try:
            x, y = frame.winfo_pointerxy()
            widget = frame.winfo_containing(x, y)
            path = str(frame)
            inside = widget is not None and (str(widget) == path or str(widget).startswith(path + "."))
            if not inside and state["inside"]:
                state["inside"] = False
                callback(False)
        except (tk.TclError, KeyError):
            pass

    def leave(event):
        try:
            frame.after(15, check)
        except tk.TclError:
            pass

    bind_tree(frame, "<Enter>", enter)
    bind_tree(frame, "<Leave>", leave)


def rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


# ---------- yumuşak kenarlı ikonlar ----------
# Tk şekilleri kenar yumuşatmasız çizer; ikonları PIL ile 4 kat büyük çizip küçültüyoruz.

SUPERSAMPLE = 4
_icon_cache = {}


def _round_line(draw, points, width):
    draw.line(points, fill=255, width=width, joint="curve")
    r = width / 2
    for x, y in points:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=255)


def _heart(draw, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    r = w * 0.27
    for cx in (x0 + w * 0.28, x0 + w * 0.72):
        cy = y0 + h * 0.36
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    draw.polygon([(x0 + w * 0.03, y0 + h * 0.46), (x1 - w * 0.03, y0 + h * 0.46), (x0 + w * 0.5, y0 + h * 0.92)], fill=255)


def draw_icon(kind, size, color, scale=1.0):
    n = size * SUPERSAMPLE
    shape = Image.new("L", (n, n), 0)
    cut = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(shape)
    c = ImageDraw.Draw(cut)
    pad = n * (1 - scale) / 2
    box = (pad, pad, n - pad - 1, n - pad - 1)
    stroke = max(round(n / 11), SUPERSAMPLE)
    cx = cy = n / 2

    if kind.endswith("_circle"):
        d.ellipse(box, fill=255)
        u = (n - 2 * pad) * 0.16
        if kind == "play_circle":
            c.polygon([(cx - u * 0.75, cy - u * 1.2), (cx - u * 0.75, cy + u * 1.2), (cx + u * 1.35, cy)], fill=255)
        elif kind == "pause_circle":
            w = u * 0.62
            for left in (cx - u * 0.95, cx + u * 0.95 - w):
                c.rounded_rectangle((left, cy - u * 1.15, left + w, cy + u * 1.15), radius=w / 3, fill=255)
        else:
            r = u * 0.28
            for dx in (-u, 0, u):
                c.ellipse((cx + dx - r, cy - r, cx + dx + r, cy + r), fill=255)

    elif kind in ("heart", "heart_outline"):
        inset = n * 0.06
        _heart(d, (inset, inset * 1.4, n - inset, n - inset * 0.6))
        if kind == "heart_outline":
            # Kalbin içini, kenardan eşit kalınlıkta aşındırıp oyuyoruz
            cut = shape.filter(ImageFilter.MinFilter(stroke * 2 + 1))

    elif kind in ("download", "downloaded", "downloading") or kind.startswith("progress:"):
        inset = n * 0.06 + stroke / 2
        circle = (inset, inset, n - inset, n - inset)
        if kind == "downloaded":
            d.ellipse((n * 0.06, n * 0.06, n * 0.94, n * 0.94), fill=255)
        elif kind == "downloading":
            d.arc(circle, start=-70, end=200, fill=255, width=stroke)
        elif kind.startswith("progress:"):
            # indirme ilerlemesi: soluk halka + saat yönünde dolan yay
            fraction = int(kind[9:]) / 100
            d.ellipse(circle, outline=80, width=stroke)
            if fraction > 0:
                d.arc(circle, start=-90, end=-90 + 360 * fraction, fill=255, width=stroke)
        else:
            d.ellipse(circle, outline=255, width=stroke)
        arrow = c if kind == "downloaded" else d
        top, bottom, wing = n * 0.29, n * 0.69, n * 0.15
        _round_line(arrow, [(cx, top), (cx, bottom)], stroke)
        _round_line(arrow, [(cx - wing, bottom - wing), (cx, bottom), (cx + wing, bottom - wing)], stroke)

    elif kind == "dot":
        d.ellipse(box, fill=255)

    # görev çubuğu önizleme butonları (beyaz, yalın simgeler)
    elif kind == "tb_play":
        d.polygon([(n * 0.3, n * 0.18), (n * 0.3, n * 0.82), (n * 0.82, n * 0.5)], fill=255)
    elif kind == "tb_pause":
        for left in (0.24, 0.58):
            d.rounded_rectangle((n * left, n * 0.18, n * (left + 0.18), n * 0.82), radius=n * 0.04, fill=255)
    elif kind == "tb_next":
        d.polygon([(n * 0.2, n * 0.2), (n * 0.2, n * 0.8), (n * 0.66, n * 0.5)], fill=255)
        d.rectangle((n * 0.68, n * 0.2, n * 0.8, n * 0.8), fill=255)
    elif kind == "tb_prev":
        d.polygon([(n * 0.8, n * 0.2), (n * 0.8, n * 0.8), (n * 0.34, n * 0.5)], fill=255)
        d.rectangle((n * 0.2, n * 0.2, n * 0.32, n * 0.8), fill=255)
    elif kind.startswith("glyph:"):
        # Segoe UI Symbol'den tek karakterlik simge (ör. 🔀 🔁 🔂)
        from PIL import ImageFont
        try:
            glyph_font = ImageFont.truetype("seguisym.ttf", int(n * 0.78))
            d.text((n / 2, n / 2), kind[6:], font=glyph_font, fill=255, anchor="mm")
        except OSError:
            pass

    alpha = ImageChops.subtract(shape, cut)
    image = Image.new("RGBA", (n, n), rgb(color) + (0,))
    image.putalpha(alpha)
    return image.resize((size, size), Image.LANCZOS)


def icon(kind, size, color=TEXT, scale=1.0):
    key = (kind, size, color, scale)
    if key not in _icon_cache:
        _icon_cache[key] = ImageTk.PhotoImage(draw_icon(kind, size, color, scale))
    return _icon_cache[key]


def progress_icon(fraction, size, color):
    """İndirme halkası; None ise sırada bekliyor (boş halka). %4'lük adımlarla önbelleğe alınır."""
    step = 0 if fraction is None else min(100, max(4, round(fraction * 25) * 4))
    return icon(f"progress:{step}", size, color)


def pill_image(width, height, fill=None, outline=None):
    key = ("pill", width, height, fill, outline)
    if key not in _icon_cache:
        s = SUPERSAMPLE
        image = Image.new("RGBA", (width * s, height * s), (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle(
            (0, 0, width * s - 1, height * s - 1), radius=height * s / 2,
            fill=rgb(fill) + (255,) if fill else None,
            outline=rgb(outline) + (255,) if outline else None, width=s,
        )
        _icon_cache[key] = ImageTk.PhotoImage(image.resize((width, height), Image.LANCZOS))
    return _icon_cache[key]


LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")


def load_logo(height):
    """assets/logo.png'yi verilen yüksekliğe küçültür; dosya yoksa None."""
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
    except OSError:
        return None
    width = round(logo.width * height / logo.height)
    return ImageTk.PhotoImage(logo.resize((width, height), Image.LANCZOS))


ICON_PATH = os.path.join(os.path.dirname(LOGO_PATH), "icon.ico")
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_icon_images(sizes=ICON_SIZES):
    """Uygulama ikonu: logonun 'S' harfi, koyu yuvarlatılmış kare üzerinde (PIL Image listesi)."""
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
    except OSError:
        return []
    letter = logo.crop((0, 0, round(logo.width * 0.185), logo.height))
    letter = letter.crop(letter.getbbox())
    images = []
    for size in sizes:
        s = size * SUPERSAMPLE
        canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.22, fill=rgb("#120a1f") + (255,))
        inner = s * 0.72
        scale = min(inner / letter.width, inner / letter.height)
        glyph = letter.resize((round(letter.width * scale), round(letter.height * scale)), Image.LANCZOS)
        canvas.alpha_composite(glyph, ((s - glyph.width) // 2, (s - glyph.height) // 2))
        images.append(canvas.resize((size, size), Image.LANCZOS))
    return images


def tinted_icon_file(accent, folder):
    """Kişiselleştir'deki vurgu rengine boyanmış uygulama ikonu (.ico); renk başına bir kez üretilir."""
    path = os.path.join(folder, "app_%s.ico" % accent[1:].lower())
    if os.path.exists(path):
        return path
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
    except OSError:
        return None
    letter = logo.crop((0, 0, round(logo.width * 0.185), logo.height))
    letter = letter.crop(letter.getbbox())
    a = rgb(accent)
    mix = lambda c, t, k: tuple(round(x + (y - x) * k) for x, y in zip(c, t))
    stops = ((0.0, mix(a, (255, 255, 255), 0.2)), (0.38, a), (1.0, mix(a, (0, 0, 0), 0.58)))  # arayüzdeki logo ile aynı geçiş
    paint = Image.new("RGBA", letter.size)
    draw = ImageDraw.Draw(paint)
    for y in range(letter.height):
        f = y / max(1, letter.height - 1)
        (f0, c0), (f1, c1) = (stops[0], stops[1]) if f <= stops[1][0] else (stops[1], stops[2])
        draw.line((0, y, letter.width, y), fill=mix(c0, c1, (f - f0) / (f1 - f0)) + (255,))
    paint.putalpha(letter.getchannel("A"))
    back = mix((10, 10, 12), a, 0.12) + (255,)
    images = []
    for size in ICON_SIZES:
        s = size * SUPERSAMPLE
        canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.22, fill=back)
        inner = s * 0.72
        scale = min(inner / paint.width, inner / paint.height)
        glyph = paint.resize((round(paint.width * scale), round(paint.height * scale)), Image.LANCZOS)
        canvas.alpha_composite(glyph, ((s - glyph.width) // 2, (s - glyph.height) // 2))
        images.append(canvas.resize((size, size), Image.LANCZOS))
    os.makedirs(folder, exist_ok=True)
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in ICON_SIZES], append_images=images[:-1])
    return path


def ensure_icon_file():
    """Windows görev çubuğu .ico ister; yoksa logodan üret. Yolunu (veya None) döner."""
    if not os.path.exists(ICON_PATH):
        images = app_icon_images()
        if not images:
            return None
        images[-1].save(ICON_PATH, format="ICO", sizes=[(s, s) for s in ICON_SIZES], append_images=images[:-1])
    return ICON_PATH


def ensure_thumbbar_icons():
    """Görev çubuğu önizlemesindeki önceki / çal / duraklat / sonraki butonlarının .ico dosyaları."""
    specs = {
        "tb_prev": ("tb_prev", TEXT), "tb_play": ("tb_play", TEXT), "tb_pause": ("tb_pause", TEXT),
        "tb_next": ("tb_next", TEXT),
        "tb_shuffle": ("glyph:🔀", TEXT), "tb_shuffle_on": ("glyph:🔀", ACCENT_LIGHT),
        "tb_repeat": ("glyph:🔁", TEXT), "tb_repeat_on": ("glyph:🔁", ACCENT_LIGHT),
        "tb_repeat_one": ("glyph:🔂", ACCENT_LIGHT),
    }
    paths = {}
    for name, (kind, color) in specs.items():
        path = os.path.join(os.path.dirname(LOGO_PATH), name + ".ico")
        if not os.path.exists(path):
            sizes = (16, 20, 24, 32, 48)
            images = [draw_icon(kind, size, color) for size in sizes]
            images[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[:-1])
        paths[name] = path
    return paths


def app_icons():
    return [ImageTk.PhotoImage(image) for image in app_icon_images((16, 32, 48, 64, 256))]


def make_tile(size, color, symbol):
    """Renk geçişli kare kapak + ortada beyaz simge (PIL Image döner)."""
    from PIL import ImageFont

    image = Image.new("RGB", (2, 2))
    image.putdata([rgb(mix(color, "#ffffff", 0.2)), rgb(color), rgb(color), rgb(mix(color, "#000000", 0.45))])
    image = image.resize((size, size), Image.BILINEAR)
    try:
        symbol_font = ImageFont.truetype("seguisym.ttf", int(size * 0.4))
        ImageDraw.Draw(image).text((size / 2, size / 2), symbol, font=symbol_font,
                                   fill=(255, 255, 255), anchor="mm")
    except OSError:
        pass
    return image


# ---------- butonlar ----------

class IconButton(tk.Label):
    def __init__(self, master, text, command=None, size=13, fg=SUBTEXT, hover=TEXT,
                 bg=None, padx=6, pady=2, use_icon_font=True, weight="normal"):
        super().__init__(
            master, text=text, fg=fg, bg=bg or master["bg"], cursor="hand2", padx=padx, pady=pady,
            font=icon_font(size) if use_icon_font else font(size, weight),
        )
        self.fg = fg
        self.hover = hover
        self.command = command
        self.bind("<Enter>", lambda e: self.config(fg=self.hover))
        self.bind("<Leave>", lambda e: self.config(fg=self.fg))
        self.bind("<Button-1>", self._click)
        self.bind("<Double-Button-1>", lambda e: "break")

    def _click(self, event):
        if self.command:
            self.command()
        return "break"

    def set_colors(self, fg, hover=None):
        self.fg = fg
        self.hover = hover or fg
        self.config(fg=fg)


class ImageButton(tk.Label):
    """Resimli buton; fare üstüne gelince hover resmine geçer."""

    def __init__(self, master, image, hover_image=None, command=None, bg=None, padx=5, pady=2):
        super().__init__(master, image=image, bg=bg or master["bg"], bd=0, cursor="hand2", padx=padx, pady=pady)
        self.images = (image, hover_image or image)
        self.inside = False
        self.command = command
        self.bind("<Enter>", lambda e: self._set_inside(True))
        self.bind("<Leave>", lambda e: self._set_inside(False))
        self.bind("<Button-1>", self._click)
        self.bind("<Double-Button-1>", lambda e: "break")

    def _set_inside(self, value):
        self.inside = value
        self.config(image=self.images[1 if value else 0])

    def _click(self, event):
        if self.command:
            self.command()
        return "break"

    def set_images(self, image, hover_image=None):
        self.images = (image, hover_image or image)
        self.config(image=self.images[1 if self.inside else 0])


class PillButton(tk.Label):
    def __init__(self, master, text, command, fill=TEXT, fg=BG, hover_fill=None,
                 outline=None, size=10, padx=18, height=34):
        text_font = tkfont.Font(family=FONT, size=size, weight="bold")
        width = text_font.measure(text) + padx * 2
        self.normal = pill_image(width, height, fill, outline)
        if fill:
            self.hover = pill_image(width, height, hover_fill or mix(fill, "#ffffff", 0.15), outline)
        else:
            self.hover = pill_image(width, height, None, TEXT)
        super().__init__(master, image=self.normal, text=text, compound="center", font=text_font,
                         fg=fg, bg=master["bg"], bd=0, padx=0, pady=0, cursor="hand2")
        self.font_ref = text_font
        self.command = command
        self.bind("<Enter>", lambda e: self.config(image=self.hover))
        self.bind("<Leave>", lambda e: self.config(image=self.normal))
        self.bind("<Button-1>", lambda e: self.command())


class PlayButton(tk.Label):
    """Yuvarlak çal / duraklat butonu."""

    def __init__(self, master, size, command, fill=ACCENT):
        super().__init__(master, bg=master["bg"], bd=0, cursor="hand2")
        self.size = size
        self.fill = fill
        self.command = command
        self.mode = "play"
        self.hover = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: self.command())
        self.draw()

    def _set_hover(self, value):
        self.hover = value
        self.draw()

    def set_mode(self, mode):
        if mode != self.mode:
            self.mode = mode
            self.draw()

    def draw(self):
        color = mix(self.fill, "#ffffff", 0.15) if self.hover else self.fill
        scale = 1.0 if self.hover else 0.94
        self.config(image=icon(self.mode + "_circle", self.size, color, scale))


class Slider(tk.Canvas):
    """İlerleme ve ses çubuğu. live=True ise sürüklerken de komut çağrılır."""

    def __init__(self, master, width=200, command=None, value=0.0, live=False, on_drag=None, bg=None):
        super().__init__(master, width=width, height=16, bg=bg or master["bg"],
                         highlightthickness=0, cursor="hand2")
        self.value = value
        self.command = command
        self.live = live
        self.on_drag = on_drag
        self.dragging = False
        self.hover = False
        self.enabled = True
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)

    def _set_hover(self, value):
        self.hover = value
        self.draw()

    def _fraction(self, event):
        width = max(self.winfo_width() - 12, 1)
        return min(max((event.x - 6) / width, 0.0), 1.0)

    def _press(self, event):
        if not self.enabled:
            return
        self.dragging = True
        self._move(event)

    def _move(self, event):
        if not self.dragging:
            return
        self.value = self._fraction(event)
        self.draw()
        if self.on_drag:
            self.on_drag(self.value)
        if self.live and self.command:
            self.command(self.value)

    def _release(self, event):
        if not self.dragging:
            return
        self.dragging = False
        self.draw()
        if self.command:
            self.command(self.value)

    def set(self, value):
        if not self.dragging:
            self.value = min(max(value, 0.0), 1.0)
            self.draw()

    def draw(self):
        self.delete("all")
        width = self.winfo_width()
        y = self.winfo_height() / 2
        x0, x1 = 6, max(width - 6, 7)
        xv = x0 + (x1 - x0) * self.value
        active = (self.hover or self.dragging) and self.enabled
        self.create_line(x0, y, x1, y, fill="#4d4d4d", width=4, capstyle="round")
        if self.value > 0:
            self.create_line(x0, y, xv, y, fill=ACCENT if active else "#e6e6e6", width=4, capstyle="round")
        if active:
            self.create_image(xv, y, image=icon("dot", 13))


def _flame_palette():
    """Yoğunluk (0-255) -> RGBA: koyu mor -> mor -> lila -> beyaz-sıcak."""
    stops = [(0, (59, 7, 100, 0)), (60, (88, 28, 175, 110)), (125, (139, 92, 246, 205)),
             (195, (196, 181, 253, 245)), (255, (250, 245, 255, 255))]
    palette = []
    for value in range(256):
        for (v0, c0), (v1, c1) in zip(stops, stops[1:]):
            if v0 <= value <= v1:
                t = (value - v0) / (v1 - v0)
                palette.extend(round(a + (b - a) * t) for a, b in zip(c0, c1))
                break
    return palette


class FlameSlider(Slider):
    """İlerleme çubuğu: dinlenen kısım çalarken lila/mor alevlerle yanar, uçta daha parlak."""

    HEIGHT = 24
    LINE_Y = 16       # çubuğun dikey konumu (alevler bunun üstünde yükselir)
    FLAME_MAX = 13    # alevlerin çıkabileceği en büyük yükseklik
    FRAME_MS = 50

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.config(height=self.HEIGHT)
        self.palette = _flame_palette()
        self.phase = 0.0
        self.burning = False
        self.flame_photo = None
        self.after(self.FRAME_MS, self._animate)

    def set_burning(self, burning):
        if burning != self.burning:
            self.burning = burning
            self.draw()

    def _animate(self):
        if self.burning:
            self.phase += self.FRAME_MS / 1000
            self.draw()
        try:
            self.after(self.FRAME_MS, self._animate)
        except tk.TclError:
            pass

    def _flame_image(self, width):
        import math
        import random
        columns = max(width // 2, 1)       # yarım çözünürlükte hesapla, sonra genişlet
        height = self.HEIGHT
        t = self.phase
        line = self.LINE_Y
        pixels = bytearray(columns * height)
        for c in range(columns):
            x = c * 2
            wave = (0.5 + 0.22 * math.sin(x * 0.07 + t * 5.0) + 0.16 * math.sin(x * 0.19 - t * 7.3)
                    + 0.12 * math.sin(x * 0.031 + t * 2.1))
            if self.burning:
                wave += random.uniform(-0.08, 0.08)
            else:
                wave *= 0.55  # duraklatılınca alevler söner, kor kalır
            head = math.exp(-(width - x) / 45)  # ucun hemen gerisi daha harlı
            flame = max(0.0, wave) * (1 + 0.8 * head) * self.FLAME_MAX
            glow = 0.82 + 0.18 * head
            for y in range(height):
                above = line - y
                if -2 <= above <= 2:
                    value = glow * (1 - 0.1 * abs(above))
                elif above > 2 and flame > 0:
                    value = max(0.0, 1 - (above - 2) / flame) ** 1.4 * glow
                else:
                    continue
                pixels[y * columns + c] = min(255, int(value * 255))
        image = Image.frombytes("P", (columns, height), bytes(pixels))
        image.putpalette(self.palette, rawmode="RGBA")
        return image.convert("RGBA").resize((width, height), Image.BILINEAR)

    def draw(self):
        self.delete("all")
        width = self.winfo_width()
        x0, x1 = 6, max(width - 6, 7)
        y = self.LINE_Y
        xv = x0 + (x1 - x0) * self.value
        self.create_line(x0, y, x1, y, fill="#3d3d3d", width=4, capstyle="round")
        played = int(xv - x0)
        if played > 1:
            self.flame_photo = ImageTk.PhotoImage(self._flame_image(played))
            self.create_image(x0, 0, image=self.flame_photo, anchor="nw")
        if (self.hover or self.dragging) and self.enabled:
            self.create_image(xv, y, image=icon("dot", 13))


class ScrollFrame(tk.Frame):
    """İçeriği dikey kaydırılabilen alan. Fare tekerleği uygulama genelinde yönlendirilir."""

    def __init__(self, master, bg=BG):
        super().__init__(master, bg=bg)
        self._scroll_owner = self
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=24)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                 style="Dark.Vertical.TScrollbar")
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._update_bar)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.on_scroll = None    # kaydırınca çağrılır (ör. uzun listenin devamını yüklemek için)
        self._target = None      # yumuşak kaydırmanın gitmek istediği piksel
        self._animating = False
        self._repaint_job = None

    def _update_bar(self, first, last):
        # İçerik sığıyorsa kaydırma çubuğunu gizle
        self.bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.canvas)
        if self.on_scroll:
            self.on_scroll(float(last))
        # Kaydırma durunca alanı baştan çizdir (hızlı kaydırmada kalan izleri temizler)
        if self._repaint_job:
            self.after_cancel(self._repaint_job)
        self._repaint_job = self.after(60, self._repaint)

    def _repaint(self):
        """Tk, kaydırılan kartları ayrı pencereler olarak taşır; Windows hızlı kaydırmada bunları
        yeniden çizmeye yetişemeyince görüntü bozulur. Tüm alt pencereleri zorla yeniden çizdir."""
        self._repaint_job = None
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = self.canvas.winfo_id()
            # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW
            ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100)
        except (tk.TclError, OSError, AttributeError):
            pass

    def scroll(self, units):
        """Fare tekerleği: tek seferde zıplamak yerine birkaç karede yumuşakça kay."""
        if self.canvas.yview() == (0.0, 1.0):
            return
        total = max(self.inner.winfo_height(), 1)
        limit = max(total - self.canvas.winfo_height(), 0)
        current = self.canvas.yview()[0] * total
        start = self._target if self._animating and self._target is not None else current
        self._target = min(max(start + units * 30, 0), limit)
        if not self._animating:
            self._animating = True
            self._step()

    def _step(self):
        try:
            total = max(self.inner.winfo_height(), 1)
            current = self.canvas.yview()[0] * total
            remaining = self._target - current
            if abs(remaining) < 1.5:
                self.canvas.yview_moveto(self._target / total)
                self._animating = False
                return
            self.canvas.yview_moveto((current + remaining * 0.35) / total)
            # Bir sonraki adıma geçmeden taşınan kartlar çizilsin; yoksa üst üste binip iz bırakıyor
            self.canvas.update_idletasks()
            self.after(16, self._step)
        except tk.TclError:
            self._animating = False

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self._animating = False
        self.canvas.yview_moveto(0)


# ---------- diyaloglar ----------

def _dialog(root, title):
    dialog = tk.Toplevel(root)
    dialog.withdraw()
    dialog.title(title)
    dialog.configure(bg=SURFACE)
    dialog.resizable(False, False)
    dialog.transient(root)
    return dialog


def _show_modal(root, dialog):
    dialog.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - dialog.winfo_reqwidth()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - dialog.winfo_reqheight()) // 3
    dialog.geometry(f"+{x}+{y}")
    dialog.deiconify()
    dialog.grab_set()
    root.wait_window(dialog)


def ask_text(root, title, prompt, initial=""):
    dialog = _dialog(root, title)
    result = {"value": None}

    body = tk.Frame(dialog, bg=SURFACE, padx=24, pady=20)
    body.pack(fill="both")
    tk.Label(body, text=prompt, font=font(13, "bold"), fg=TEXT, bg=SURFACE).pack(anchor="w")

    box = tk.Frame(body, bg=FIELD, padx=10, pady=8)
    box.pack(fill="x", pady=(14, 18))
    entry = tk.Entry(box, font=font(11), bg=FIELD, fg=TEXT, insertbackground=TEXT,
                     relief="flat", width=34)
    entry.pack(fill="x")
    entry.insert(0, initial)
    entry.select_range(0, "end")

    def accept(event=None):
        text = entry.get().strip()
        if text:
            result["value"] = text
            dialog.destroy()

    buttons = tk.Frame(body, bg=SURFACE)
    buttons.pack(fill="x")
    PillButton(buttons, "Kaydet", accept, fill=ACCENT, fg=TEXT, hover_fill=ACCENT_LIGHT).pack(side="right")
    IconButton(buttons, "İptal", dialog.destroy, size=10, use_icon_font=False,
               weight="bold", padx=14).pack(side="right", padx=8)

    entry.bind("<Return>", accept)
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    entry.focus_set()
    _show_modal(root, dialog)
    return result["value"]


def ask_yes_no(root, title, message, confirm_text="Sil"):
    dialog = _dialog(root, title)
    result = {"value": False}

    body = tk.Frame(dialog, bg=SURFACE, padx=24, pady=20)
    body.pack(fill="both")
    tk.Label(body, text=title, font=font(13, "bold"), fg=TEXT, bg=SURFACE).pack(anchor="w")
    tk.Label(body, text=message, font=font(10), fg=SUBTEXT, bg=SURFACE, wraplength=340,
             justify="left").pack(anchor="w", pady=(8, 18))

    def accept():
        result["value"] = True
        dialog.destroy()

    buttons = tk.Frame(body, bg=SURFACE)
    buttons.pack(fill="x")
    PillButton(buttons, confirm_text, accept, fill=DANGER, fg=BG, hover_fill="#fca5a5").pack(side="right")
    IconButton(buttons, "Vazgeç", dialog.destroy, size=10, use_icon_font=False,
               weight="bold", padx=14).pack(side="right", padx=8)
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.bind("<Return>", lambda e: accept())
    _show_modal(root, dialog)
    return result["value"]


# ---------- kapak resimleri ----------

class ImageCache:
    """Kapakları arka planda indirir/küçültür, ana iş parçacığında PhotoImage'a çevirir."""

    def __init__(self, executor, ui_call):
        self.executor = executor
        self.ui_call = ui_call
        self.images = {}
        self.colors = {}
        self.waiting = {}
        self.placeholders = {}

    def placeholder(self, size):
        if size not in self.placeholders:
            self.placeholders[size] = ImageTk.PhotoImage(Image.new("RGB", (size, size), "#2a2a2a"))
        return self.placeholders[size]

    def get(self, track, size, callback):
        key = (track["id"], size)
        if key in self.images:
            return self.images[key]
        callbacks = self.waiting.get(key)
        if callbacks is None:
            self.waiting[key] = [callback]
            self.executor.submit(self._load, dict(track), size, key)
        else:
            callbacks.append(callback)
        return self.placeholder(size)

    def color(self, track_id):
        return self.colors.get(track_id)

    def _load(self, track, size, key):
        try:
            path = downloader.fetch_thumbnail(track)
            image = Image.open(path).convert("RGB")
            w, h = image.size
            s = min(w, h)
            image = image.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
            r, g, b = image.resize((1, 1), Image.BOX).getpixel((0, 0))
            color = f"#{r:02x}{g:02x}{b:02x}"
            image = image.resize((size, size), Image.LANCZOS)
        except Exception:
            image, color = None, None
        self.ui_call(lambda: self._done(key, image, color))

    def _done(self, key, image, color):
        callbacks = self.waiting.pop(key, [])
        if image is None:
            return
        photo = ImageTk.PhotoImage(image)
        self.images[key] = photo
        self.colors[key[0]] = color
        for callback in callbacks:
            try:
                callback(photo)
            except tk.TclError:
                pass  # bileşen bu arada kapanmış
