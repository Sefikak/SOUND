"""Kurulum sihirbazının görsellerini assets/ içindeki logo ve ikondan üretir.

wizard.bmp / wizard@2x.bmp: soldaki uzun panel (karşılama ve bitiş sayfaları)
small.bmp / small@2x.bmp: sağ üstteki küçük ikon (diğer sayfalar)
Çalıştır: python installer/make_images.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")
BG = (18, 18, 18)
ACCENT = (139, 92, 246)


def icon(size):
    image = Image.open(os.path.join(ASSETS, "icon.ico"))
    image.size = max(image.ico.sizes())
    return image.convert("RGBA").resize((size, size), Image.LANCZOS)


def wizard(scale):
    w, h = 164 * scale, 314 * scale
    image = Image.new("RGB", (w, h), BG)
    # yukarıdan aşağı koyulaşan mor parıltı
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-w * 0.6, -h * 0.15, w * 1.6, h * 0.62), fill=ACCENT + (120,))
    glow = glow.filter(ImageFilter.GaussianBlur(40 * scale))
    image.paste(glow, (0, 0), glow)
    ico = icon(96 * scale)
    image.paste(ico, ((w - ico.width) // 2, 70 * scale), ico)
    logo = Image.open(os.path.join(ASSETS, "logo.png")).convert("RGBA")
    lw = 128 * scale
    logo = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
    image.paste(logo, ((w - lw) // 2, 186 * scale), logo)
    return image


def small(scale):
    s = 55 * scale
    image = Image.new("RGB", (s, s), BG)
    ico = icon(s - 6 * scale)
    image.paste(ico, (3 * scale, 3 * scale), ico)
    return image


for scale, suffix in ((1, ""), (2, "@2x")):
    wizard(scale).save(os.path.join(HERE, f"wizard{suffix}.bmp"))
    small(scale).save(os.path.join(HERE, f"small{suffix}.bmp"))
print("tamam")
