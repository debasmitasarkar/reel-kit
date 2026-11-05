"""Shared v3 Reel style: NexGen palette, type pairing, captions, chips, cards, person cutouts, SFX.

Look: pine background with a faint hand-drawn
grid, Bricolage Grotesque for body, one Instrument Serif italic accent word per screen, small captions
on a translucent pill with only the current word underlined, a "Flutter + AI" series chip.
Safe zone for anything that matters: x 60-990, y 240-1480 (Reels/Shorts UI covers the rest).
"""
import array
import functools
import math
import random
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SANS = str(ROOT / "assets/fonts/BricolageGrotesque.ttf")
SERIF_IT = str(ROOT / "assets/fonts/InstrumentSerif-Italic.ttf")

W, H, FPS = 1080, 1920, 30
PINE_DEEP = (20, 63, 55)
PINE = (30, 91, 79)
INK = (16, 34, 30)
PAPER = (238, 242, 239)
MINT = (216, 255, 240)
MINT_D = (126, 232, 196)  # mint that still reads on light backgrounds' dark text, used for underlines
SAGE = (127, 179, 163)
CORAL = (255, 122, 107)
GRID = (33, 80, 70)


@functools.lru_cache(maxsize=None)
def sans(size, weight=800, opsz=96):
    f = ImageFont.truetype(SANS, max(8, int(size)))
    f.set_variation_by_axes([min(96, max(12, opsz)), weight, 100])
    return f


@functools.lru_cache(maxsize=None)
def serif(size):
    return ImageFont.truetype(SERIF_IT, max(8, int(size)))


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def back(t):
    """Ease-out with a small overshoot, for pop-ins. Exactly 0 before start."""
    if t <= 0:
        return 0.0
    t = min(1.0, t)
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


# ---------- backgrounds ----------

@functools.lru_cache(maxsize=1)
def _grid_bg():
    """Pine with a faint, slightly wobbly hand-drawn grid (static, built once)."""
    img = Image.new("RGB", (W, H), PINE_DEEP)
    d = ImageDraw.Draw(img)
    for y in range(0, H, 8):
        k = y / H * 0.6
        d.rectangle((0, y, W, y + 8), fill=tuple(int(INK[i] * k + PINE_DEEP[i] * (1 - k)) for i in range(3)))
    rnd = random.Random(7)
    step = 135
    for x0 in range(-20, W + step, step):
        ph, amp = rnd.uniform(0, 6.28), rnd.uniform(3, 7)
        pts = [(x0 + amp * math.sin(y / 260 + ph), y) for y in range(0, H + 40, 40)]
        d.line(pts, fill=GRID, width=3, joint="curve")
    for y0 in range(60, H + step, step):
        ph, amp = rnd.uniform(0, 6.28), rnd.uniform(3, 7)
        pts = [(x, y0 + amp * math.sin(x / 240 + ph)) for x in range(0, W + 40, 40)]
        d.line(pts, fill=GRID, width=3, joint="curve")
    return img


def grid_bg():
    return _grid_bg().copy()


# ---------- small components ----------

def chip(d, x, y, text, fg=INK, bg=MINT, size=34, number=None):
    """Rounded label; with number, a dark square badge in front (step chip)."""
    f = sans(size, 700, 24)
    tw = d.textlength(text, font=f)
    h = size + 30
    if number is not None:
        d.rounded_rectangle((x, y, x + h, y + h), radius=12, fill=INK)
        d.text((x + h / 2, y + h / 2 + 1), str(number), font=sans(size, 800, 24), fill=MINT, anchor="mm")
        x += h + 12
    d.rounded_rectangle((x, y, x + tw + 44, y + h), radius=h // 2, fill=bg)
    d.text((x + 22, y + h / 2 + 1), text, font=f, fill=fg, anchor="lm")
    return x + tw + 44


def window(d, box, title, fill=PAPER):
    """Desktop-app window card with traffic-light dots (the 'Notes window' prop)."""
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=28, fill=fill)
    d.rounded_rectangle((x0, y0, x1, y0 + 74), radius=28, fill=(222, 229, 225))
    d.rectangle((x0, y0 + 46, x1, y0 + 74), fill=(222, 229, 225))
    for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        d.ellipse((x0 + 30 + i * 36, y0 + 26, x0 + 52 + i * 36, y0 + 48), fill=c)
    d.text(((x0 + x1) / 2, y0 + 38), title, font=sans(30, 600, 14), fill=(96, 110, 104), anchor="mm")


def hand_circle(d, cx, cy, rx, ry, p, color, width=8):
    """Marker-style ellipse drawn progressively (p 0..1), slightly off-round and overshooting its start."""
    if p <= 0:
        return
    n = int(64 * min(1.0, p) * 1.12)
    pts = []
    for i in range(n + 1):
        a = -2.4 + i / 64 * 2 * math.pi
        wob = 1 + 0.04 * math.sin(a * 3 + 1)
        pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a) - 6 * i / 64))
    if len(pts) > 1:
        d.line(pts, fill=color, width=width, joint="curve")


def sparkle(d, x, y, r, color):
    d.polygon([(x, y - r), (x + r * 0.22, y - r * 0.22), (x + r, y), (x + r * 0.22, y + r * 0.22),
               (x, y + r), (x - r * 0.22, y + r * 0.22), (x - r, y), (x - r * 0.22, y - r * 0.22)], fill=color)


def notification(img, y, app, title, body, icon_text="</>"):
    """iOS-style banner pasted onto img at top y."""
    card = Image.new("RGBA", (900, 170), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, 899, 169), radius=40, fill=(246, 248, 247, 245))
    d.rounded_rectangle((28, 35, 128, 135), radius=24, fill=PINE)
    d.text((78, 86), icon_text, font=sans(40, 800, 24), fill=MINT, anchor="mm")
    d.text((156, 52), app.upper(), font=sans(26, 600, 14), fill=(120, 130, 126), anchor="ls")
    d.text((870, 52), "now", font=sans(26, 500, 14), fill=(120, 130, 126), anchor="rs")
    d.text((156, 100), title, font=sans(42, 800, 48), fill=INK, anchor="ls")
    d.text((156, 145), body, font=sans(32, 500, 14), fill=(84, 96, 92), anchor="ls")
    img.paste(card, (90, int(y)), card)


def question_sticker(img, y, question_lines, hint, scale=1.0):
    """Instagram-style question sticker (avatar on top, question, answer field)."""
    if scale <= 0:
        return
    w, h = 820, 140 + 66 * len(question_lines) + 120
    card = Image.new("RGBA", (w, h + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 60, w - 1, h + 59), radius=44, fill=(255, 255, 255, 250))
    d.ellipse((w / 2 - 60, 0, w / 2 + 60, 120), fill=PINE, outline=(255, 255, 255), width=8)
    d.text((w / 2, 62), "DS", font=sans(44, 800, 48), fill=MINT, anchor="mm")
    for i, line in enumerate(question_lines):
        d.text((w / 2, 190 + i * 66), line, font=sans(50, 700, 48), fill=INK, anchor="mm")
    fy = 190 + 66 * len(question_lines) + 10
    d.rounded_rectangle((60, fy, w - 60, fy + 92), radius=24, fill=(238, 241, 239))
    d.text((w / 2, fy + 47), hint, font=sans(36, 500, 14), fill=(132, 142, 138), anchor="mm")
    if scale != 1.0:
        card = card.resize((max(1, int(w * scale)), max(1, int((h + 60) * scale))), Image.BICUBIC)
    img.paste(card, (W // 2 - card.width // 2, int(y + (h + 60) * (1 - scale) / 2)), card)


# ---------- captions ----------

def caption_layer(words, hi, y=1420, size=58):
    """Transparent frame with one caption group on a translucent pill; current word underlined in mint."""
    words = [w for w in words if w != "_"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not words:
        return img
    d = ImageDraw.Draw(img)
    f = sans(size, 650, 48)
    space = d.textlength(" ", font=f)
    widths = [d.textlength(w, font=f) for w in words]
    total = sum(widths) + space * (len(words) - 1)
    x = (W - total) / 2
    d.rounded_rectangle((x - 30, y - size - 22, x + total + 30, y + 30), radius=26, fill=(16, 34, 30, 150))
    for i, w in enumerate(words):
        d.text((x, y), w, font=f, fill=(255, 255, 255, 255), anchor="ls")
        if i == hi:
            d.rounded_rectangle((x - 2, y + 9, x + widths[i] + 2, y + 17), radius=4, fill=(*MINT_D, 255))
        x += widths[i] + space
    return img


# ---------- person cutout ----------

def segment(frames_dir, masks_dir):
    """Apple Vision person masks (tools/video/segment.swift), cached per directory."""
    frames = sorted(Path(frames_dir).glob("*.png"))
    masks = sorted(Path(masks_dir).glob("*.png")) if Path(masks_dir).exists() else []
    if len(masks) != len(frames):
        subprocess.run(["swift", str(ROOT / "tools/video/segment.swift"), str(frames_dir), str(masks_dir)], check=True)


class MaskSmoother:
    """Feathers each mask and blends it with the previous one so hair edges do not flicker."""

    def __init__(self):
        self.prev = None

    def __call__(self, mask):
        m = mask.convert("L").filter(ImageFilter.GaussianBlur(1.6))
        if self.prev is not None:
            m = Image.blend(self.prev, m, 0.6)
        self.prev = m
        return m


def coverage(mask, box):
    """Fraction of box covered by the person mask."""
    region = mask.crop(tuple(int(v) for v in box)).convert("L")
    hist = region.histogram()
    n = sum(hist)
    return sum(c for v, c in enumerate(hist) if v >= 128) / n if n else 0.0


# ---------- sound effects (stdlib synthesis, 48 kHz mono) ----------

SR = 48000


def _pop():
    n = int(0.09 * SR)
    out, ph = [], 0.0
    for i in range(n):
        t = i / SR
        f = 300 + 600 * math.exp(-t * 45)
        ph += 2 * math.pi * f / SR
        out.append(math.sin(ph) * math.exp(-t / 0.024))
    return out


def _tick():
    rnd = random.Random(3)
    n = int(0.018 * SR)
    return [(0.6 * math.sin(2 * math.pi * 2600 * i / SR) * math.exp(-i / SR / 0.0035)
             + 0.5 * (rnd.random() * 2 - 1) * math.exp(-i / SR / 0.0015)) for i in range(n)]


def _whoosh(dur=0.32):
    rnd = random.Random(11)
    n = int(dur * SR)
    out, lp, lp2 = [], 0.0, 0.0
    for i in range(n):
        p = i / n
        a = 0.04 + 0.30 * math.sin(math.pi * p) ** 2  # cutoff sweeps up then down
        x = rnd.random() * 2 - 1
        lp += a * (x - lp)
        lp2 += 0.02 * (lp - lp2)  # remove rumble
        out.append((lp - lp2) * math.sin(math.pi * p) ** 1.5)
    return out


def _ding():
    n = int(0.45 * SR)
    return [(math.sin(2 * math.pi * 1568 * i / SR) + 0.6 * math.sin(2 * math.pi * 2093 * i / SR))
            * math.exp(-i / SR / 0.11) * min(1.0, i / 120) for i in range(n)]


def _norm(x):
    m = max(abs(v) for v in x) or 1.0
    return [v / m for v in x]


SFX = {"pop": _norm(_pop()), "tick": _norm(_tick()), "whoosh": _norm(_whoosh()), "ding": _norm(_ding())}
# Peak gains, ~10-15 dB under the voice peaks.
SFX_GAIN = {"pop": 0.085, "tick": 0.07, "whoosh": 0.075, "ding": 0.06}


def sfx_stem(events, total, out):
    """events: [(seconds, kind)] -> mono 16-bit wav of length total."""
    buf = [0.0] * int(total * SR + SR)
    for t, kind in events:
        s, g = SFX[kind], SFX_GAIN[kind]
        start = max(0, int(t * SR))
        for i, v in enumerate(s):
            if start + i < len(buf):
                buf[start + i] += v * g
    pcm = array.array("h", (max(-32767, min(32767, int(v * 32767))) for v in buf[: int(total * SR)]))
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out
