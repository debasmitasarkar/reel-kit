"""Shared Reel builder (style rules in STYLE.md).

A Reel is: face part (hook) -> voice-over explainer -> face part (close) -> end card.
Parts are lists of speech *blocks* (start, end) taken from `inspect_take.py`, which splits a take at
its pauses. Between blocks we keep a natural pause (<= MAX_PAUSE), cut in the middle of the silence
with soft fades, so no word is clipped. A face block can be `covered` by a full-screen card while her
voice carries on: that's how prompter glances are hidden. Overlays stay out of the face box.
"""
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import reelkit as k  # noqa: E402
from reelkit import CORAL, FPS, H, INK, MINT, PAPER, PINE, PINE_DEEP, SAGE, W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "media/raw"
OUT = ROOT / "media/out"
MODEL = Path.home() / "whisper-models/ggml-small.en.bin"
MEMO = RAW / "voice_memo.m4a"
MUSIC = RAW / "music/track.mp3"
MUSIC_DROP = 12.0
MAX_PAUSE = 0.45
PAD = 0.2
FACE_CX = 490  # her face (Vision) sits x 200-770, y 990-1500 of 1080x1920 in my clips; change for your framing
ZOOMS = (1.2, 1.26)  # bottom-anchored, gentle: lifts the face to mid-frame without magnifying glances
CAP_Y = 1500  # face-part caption baseline, just under her chin
GREY = (84, 96, 92)
AMBER = (255, 209, 102)

WORK = OUT / "work"


def setup(name):
    global WORK
    WORK = OUT / f"work_{name}"
    WORK.mkdir(parents=True, exist_ok=True)


def run(cmd, **kw):
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, **kw)


def duration(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(p)], capture_output=True, text=True).stdout)


def render(frame_fn, n, out, audio=None):
    """Encode n frames from frame_fn(t seconds) -> PIL image, optionally muxed with an audio file."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-"]
    if audio:
        cmd += ["-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-ar", "48000", "-shortest"]
    cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", str(out)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        ff.stdin.write(frame_fn(i / FPS).tobytes())
    ff.stdin.close()
    if ff.wait():
        sys.exit(f"render failed: {out}")
    return out


def lufs(path):
    o = subprocess.run(["ffmpeg", "-nostats", "-v", "info", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", o)[-1])


def level_voice(path, target=-16.0):
    """Bring a part's voice to a fixed loudness so hook, VO and close match."""
    gain = target - lufs(path)
    out = path.with_name(path.stem + "_lvl.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af",
         f"highpass=f=80,volume={gain:.2f}dB,acompressor=threshold=-22dB:ratio=2.5:attack=5:release=120:makeup=1,"
         "alimiter=limit=0.89:level=false", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)])
    return out


# ---------- cutting ----------

def keep_ranges(blocks):
    """Blocks -> source ranges to keep, plus each block's (start, end) in the output timeline.

    Consecutive blocks with a pause <= MAX_PAUSE stay one continuous range (her own rhythm). Longer
    pauses, or a jump to another take, are cut in the silence with up to PAD of room on each side.
    """
    ranges = []
    cur_a, cur_b = blocks[0][0] - PAD, blocks[0][1]
    for a, b in blocks[1:]:
        gap = a - cur_b
        if 0 <= gap <= MAX_PAUSE:
            cur_b = b
            continue
        room = min(PAD, gap / 2) if gap > 0 else PAD
        ranges.append((max(0.0, cur_a), cur_b + room))
        cur_a, cur_b = a - room, b
    ranges.append((max(0.0, cur_a), cur_b + PAD))
    spans, offsets, out_t = [], [], 0.0
    for a, b in ranges:
        offsets.append((a, b, out_t))
        out_t += b - a
    for a, b in blocks:
        ra, rb, o = next(x for x in offsets if x[0] - 1e-6 <= a <= x[1])
        spans.append((o + a - ra, o + b - ra))
    return ranges, spans


def crop(z):
    w, h = int(W / z) // 2 * 2, int(H / z) // 2 * 2
    x = max(0, min(W - w, FACE_CX - w // 2))
    return f"scale={W}:{H}:flags=lanczos,crop={w}:{h}:{x}:{H - h},scale={W}:{H}:flags=lanczos"


def cut_face(src, blocks, name):
    ranges, spans = keep_ranges(blocks)
    parts = []
    for i, (a, b) in enumerate(ranges):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,{crop(ZOOMS[i % 2])},"
                     f"eq=brightness=0.03:contrast=1.05:saturation=1.06[v{i}];"
                     f"[0:a:0]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.08,"
                     f"afade=t=out:st={b - a - 0.1:.3f}:d=0.1[a{i}];")
    graph = "".join(parts) + "".join(f"[v{i}][a{i}]" for i in range(len(ranges))) + \
        f"concat=n={len(ranges)}:v=1:a=1[v][a]"
    out = WORK / f"{name}_cut.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
         "-r", str(FPS), "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", str(out)])
    return out, ranges, spans


def cut_audio(src, blocks, name):
    ranges, spans = keep_ranges(blocks)
    parts = "".join(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.06,"
                    f"afade=t=out:st={b - a - 0.08:.3f}:d=0.08[s{i}];" for i, (a, b) in enumerate(ranges))
    graph = parts + "".join(f"[s{i}]" for i in range(len(ranges))) + \
        f"concat=n={len(ranges)}:v=0:a=1,highpass=f=80," \
        "acompressor=threshold=-20dB:ratio=3:attack=5:release=80,aresample=48000[a]"
    out = WORK / f"{name}.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", graph, "-map", "[a]", "-ac", "1",
         str(out)])
    return out, spans


# ---------- words ----------

NUMS = dict(zip("1234567", "one two three four five six seven".split()))


def _norm(w):
    w = re.sub(r"[^a-z0-9]", "", w.lower())
    return NUMS.get(w, w)  # whisper writes "Day 1", "3"


def _heard(media, name, a, b):
    """Whisper word segments for media[a:b], times shifted to the media timeline."""
    wav = WORK / f"{name}_16k.wav"
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(media), "-ar", "16000",
         "-ac", "1", "-af", "apad=pad_dur=0.6", str(wav)])
    run(["whisper-cli", "-m", str(MODEL), "-f", str(wav), "-ml", "1", "-sow", "-ojf", "-of", str(WORK / name),
         "-np"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    segs = [s for s in json.load(open(WORK / f"{name}.json"))["transcription"] if s["text"].strip()]
    # whisper starts a word at the beginning of the silence before it; move it to where the sound starts
    log = subprocess.run(["ffmpeg", "-v", "info", "-i", str(wav), "-af", "silencedetect=n=-40dB:d=0.3", "-f", "null",
                          "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL).stderr
    quiet = list(zip([float(x) * 1000 for x in re.findall(r"silence_start: ([-0-9.]+)", log)],
                     [float(x) * 1000 for x in re.findall(r"silence_end: ([0-9.]+)", log)]))
    for s in segs:
        o = s["offsets"]
        for q0, q1 in quiet:
            if q0 - 50 <= o["from"] < q1 - 80:
                o["from"] = int(q1 - 60)
                o["to"] = max(o["to"], o["from"] + 200)
        s["offsets"] = {"from": min(o["from"] + a * 1000, b * 1000), "to": min(o["to"] + a * 1000, b * 1000)}
    return segs


def word_times(media, name, text, spans):
    """Start/end per caption token: whisper word timings aligned to the script, gaps interpolated.

    Each speech block (span) is transcribed on its own: one long pass drifts seconds late after a
    stumble (Sat VO "FF... MPEG" pushed "music" past the end of the clip).
    """
    tokens = text.split()
    total = duration(media)
    segs = []
    for i, (a, b) in enumerate(spans):
        segs += _heard(media, name, max(0.0, a - 0.1), min(total, b + 0.1))
    heard = [_norm(s["text"]) for s in segs]
    times = [None] * len(tokens)
    sm = difflib.SequenceMatcher(None, [_norm(t) for t in tokens], heard, autojunk=False)
    for blk in sm.get_matching_blocks():
        for j in range(blk.size):
            s = segs[blk.b + j]["offsets"]
            times[blk.a + j] = (s["from"] / 1000, s["to"] / 1000)
    matched = sum(t is not None for t in times)
    if matched < 0.6 * len(tokens):
        sys.exit(f"{name}: only {matched}/{len(tokens)} words aligned; heard {[s['text'] for s in segs]}")
    known = [(i, t) for i, t in enumerate(times) if t]
    for i, t in enumerate(times):
        if t is None:
            prev = max((p for p in known if p[0] < i), default=(-1, (0.0, 0.0)), key=lambda p: p[0])
            nxt = min((p for p in known if p[0] > i), default=(len(tokens), (total, total)), key=lambda p: p[0])
            f = (i - prev[0]) / (nxt[0] - prev[0])
            st = prev[1][1] + (nxt[1][0] - prev[1][1]) * f
            times[i] = (st, st + 0.2)
    # whisper's word starts drift inside pauses; keep them monotonic
    for i in range(1, len(times)):
        if times[i][0] < times[i - 1][0]:
            times[i] = (times[i - 1][0] + 0.05, max(times[i][1], times[i - 1][0] + 0.1))
    print(f"{name}: {matched}/{len(tokens)} words aligned")
    return tokens, times


class Words:
    """Token lookup: w.at("Day", 2) = start time of the third "Day"."""

    def __init__(self, tokens, times, spans=()):
        self.tokens, self.times, self.spans = tokens, times, spans  # spans: each speech block's (start, end)

    def at(self, word, n=0):
        idx = [i for i, x in enumerate(self.tokens) if _norm(x) == _norm(word)]
        if n >= len(idx):
            sys.exit(f"word {word!r} #{n} not in {self.tokens}")
        return self.times[idx[n]][0]


def chunk_events(tokens, times, total):
    """One or two words per caption, each word appearing as she says it."""
    groups, cur = [], []
    for i, tok in enumerate(tokens):
        if cur and len(" ".join(tokens[j] for j in cur)) + len(tok) > 12:
            groups.append(cur)
            cur = []
        cur.append(i)
        if len(cur) == 2 or tok.endswith((".", "?", ",", "!", ":", "…")):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    ev = []
    for gi, g in enumerate(groups):
        nxt = times[groups[gi + 1][0]][0] if gi + 1 < len(groups) else total
        g_end = min(nxt, max(times[g[-1]][1], times[g[-1]][0] + 0.3) + 0.5)  # don't hang over a long pause
        shown = [tokens[j] for j in g]
        for n, j in enumerate(g):
            ev.append((times[j][0], times[g[n + 1]][0] if n + 1 < len(g) else g_end, shown, n))
    return ev


def chunk_layer(words, hi, y, size=104):
    """Chunky white caption with an ink outline; words after `hi` are not drawn yet (no layout jump)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = k.sans(fit(d, " ".join(words), 800, size, 940), 800)
    space = d.textlength(" ", font=f)
    widths = [d.textlength(x, font=f) for x in words]
    x0 = (W - sum(widths) - space * (len(words) - 1)) / 2
    for stroke in (max(8, f.size // 8), 0):
        x = x0
        for i, word in enumerate(words[:hi + 1]):
            d.text((x, y), word, font=f, fill=(255, 255, 255, 255), anchor="ls", stroke_width=stroke,
                   stroke_fill=(*INK, 255))
            x += widths[i] + space
    return img


class Captions:
    def __init__(self, tokens, times, total, y):
        self.events = chunk_events(tokens, times, total)
        self.y, self.cache = y, {}

    def paste(self, img, t):
        ev = next((e for e in self.events if e[0] <= t < e[1]), None)
        if ev:
            key = (tuple(ev[2]), ev[3])
            if key not in self.cache:
                self.cache[key] = chunk_layer(ev[2], ev[3], self.y)
            img.paste(self.cache[key], (0, 0), self.cache[key])


# ---------- drawing helpers ----------

def fit(d, text, weight, size, max_w):
    while d.textlength(text, font=k.sans(size, weight)) > max_w:
        size -= 4
    return size


def fade(layer, a):
    if a < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return layer


def float_chip(img, text, x, y, p, fg=INK, bg=MINT, size=40):
    if p <= 0:
        return
    s = min(1.05, p)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = k.sans(int(size * s), 700, 24)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((x - tw / 2 - 30, y - size * 0.95 * s, x + tw / 2 + 30, y + size * 0.95 * s), radius=38,
                        fill=bg)
    d.text((x, y + 2), text, font=f, fill=fg, anchor="mm")
    img.paste(layer, (0, 0), layer)


def pill(d, cx, cy, text, size, fg=INK, bg=MINT):
    f = k.sans(size, 800)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((cx - tw / 2 - 40, cy - size * 0.85, cx + tw / 2 + 40, cy + size * 0.85), radius=60, fill=bg)
    d.text((cx, cy + 2), text, font=f, fill=fg, anchor="mm")


def phone(d, x0, y0, w, h):
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=70, fill=INK)
    d.rounded_rectangle((x0 + 18, y0 + 18, x0 + w - 18, y0 + h - 18), radius=54, fill=PAPER)
    d.rounded_rectangle((x0 + w / 2 - 70, y0 + 34, x0 + w / 2 + 70, y0 + 66), radius=16, fill=INK)


def icon(d, cx, cy, kind):
    if kind == "check":
        d.line([(cx - 26, cy + 2), (cx - 6, cy + 22), (cx + 28, cy - 22)], fill=INK, width=12, joint="curve")
    elif kind == "cross":
        d.line([(cx - 22, cy - 22), (cx + 22, cy + 22)], fill=INK, width=12)
        d.line([(cx - 22, cy + 22), (cx + 22, cy - 22)], fill=INK, width=12)
    else:
        d.text((cx, cy + 4), kind, font=k.sans(64, 800, 48), fill=INK, anchor="mm")


def row(d, y, kind, icon_bg, label, p, size=88, sub=None):
    """Icon square + label, slides in from the left as p goes 0 -> 1."""
    if p <= 0:
        return
    x = 120 - 40 * (1 - k.ease(p))
    d.rounded_rectangle((x, y - 60, x + 120, y + 60), radius=30, fill=icon_bg)
    icon(d, x + 60, y, kind)
    f = k.sans(int(fit(d, label, 800, size, 720) * min(1.04, p)), 800)
    d.text((x + 160, y + (2 if sub else 22)), label, font=f, fill=PAPER, anchor="ls")
    if sub:
        d.text((x + 162, y + 52), sub, font=k.sans(36, 500, 24), fill=SAGE, anchor="ls")


def step_header(img, title, no, label, n, done, p=1.0):
    """List-Reel header that stays up: title box, numbered step chip, segmented progress bar.
    y 176-406. done = segments filled (float); p = pop-in of the step chip."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = k.sans(42, 700, 24)
    tw = d.textlength(title, font=f)
    d.rounded_rectangle((W / 2 - tw / 2 - 28, 176, W / 2 + tw / 2 + 28, 248), radius=20, fill=(*PAPER, 255))
    d.text((W / 2, 213), title, font=f, fill=(*INK, 255), anchor="mm")
    if label and p > 0:
        f2 = k.sans(fit(d, label, 800, 58, 640), 800)
        fn = k.sans(46, 800, 48)
        lw, bw = d.textlength(label, font=f2), d.textlength(no, font=fn) + 48
        x0 = W / 2 - (bw + 14 + lw + 56) / 2
        y = 268 + int(24 * (1 - k.ease(p)))
        d.rounded_rectangle((x0, y, x0 + bw, y + 96), radius=24, fill=(*CORAL, 255))
        d.text((x0 + bw / 2, y + 49), no, font=fn, fill=(*INK, 255), anchor="mm")
        d.rounded_rectangle((x0 + bw + 14, y, x0 + bw + 14 + lw + 56, y + 96), radius=28, fill=(*PAPER, 255))
        d.text((x0 + bw + 42, y + 49), label, font=f2, fill=(*INK, 255), anchor="lm")
    gap, xa, xb = 10, 120, 960
    sw = (xb - xa - gap * (n - 1)) / n
    for i in range(n):
        x = xa + i * (sw + gap)
        d.rounded_rectangle((x, 392, x + sw, 406), radius=7, fill=(150, 165, 160, 255))
        part = max(0.0, min(1.0, done - i))
        if part > 0.05:
            d.rounded_rectangle((x, 392, x + sw * part, 406), radius=7, fill=(*CORAL, 255))
    img.paste(layer, (0, 0), layer)


def whip(img, t, dur=0.17):
    if t >= dur:
        return img
    p = k.ease(t / dur)
    moved = Image.new("RGB", (W, H), PINE_DEEP)
    moved.paste(img, (int(W * 0.45 * (1 - p)), 0))
    return moved.filter(ImageFilter.BoxBlur(int(18 * (1 - p))))


def big_card(lines, sub=None):
    """Full-screen statement card factory: lines = [(text, color)], sub small grey line."""
    def draw(t):
        img = k.grid_bg()
        d = ImageDraw.Draw(img)
        p = min(1.04, k.back(t / 0.35))
        y = 820 - 70 * (len(lines) - 1)
        for i, (text, col) in enumerate(lines):
            size = fit(d, text, 800, 150 if len(lines) < 3 else 110, 940)
            if col == "pill":
                pill(d, W // 2, y, text, int(size * 0.8 * p))
            else:
                d.text((W // 2, y), text, font=k.sans(int(size * p), 800), fill=col, anchor="mm")
            y += int(size * 1.15)
        if sub and t > 0.3:
            d.text((W // 2, y + 30), sub, font=k.sans(40, 500, 24), fill=SAGE, anchor="mm")
        return whip(img, t, 0.15)
    return draw


def question_card(lines, hint="Tell me in the comments", answers=()):
    """Question sticker; `answers` type themselves into the field one after another (keeps the card moving)."""
    def draw(t):
        img = k.grid_bg()
        text = hint
        if answers and t > 0.9:
            i, lt = divmod(t - 0.9, 1.5)
            a = answers[int(i) % len(answers)]
            text = a[:int(lt * 22) + 1] + ("|" if lt % 0.5 < 0.3 else "")
        k.question_sticker(img, 560, lines, text, 1.22 * min(1.04, k.back(t / 0.4)))
        return whip(img, t, 0.15)
    return draw


# ---------- face parts ----------

def title_layer(y1, line1, s1, line2, s2):
    """Both title lines, drawn BEHIND her: line 1 above her head, the key line on a mint label that her
    head overlaps from below (y1 comes from head_tops, so about a third of the middle letters is hidden)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if s1 > 0:
        d.text((W // 2, y1), line1, font=k.sans(int(fit(d, line1, 800, 130, 980) * s1), 800), fill=(*INK, 255),
               anchor="ms")
    if s2 > 0:
        f = k.sans(int(fit(d, line2, 800, 150, 900) * s2), 800)
        x0, y0, x1, y2 = d.textbbox((W // 2, y1 + 175), line2, font=f, anchor="ms")
        d.rounded_rectangle((x0 - 34, y0 - 22, x1 + 34, y2 + 26), radius=30, fill=(*MINT, 255))
        d.text((W // 2, y1 + 175), line2, font=f, fill=(*INK, 255), anchor="ms")
    return img


def head_tops(masks, bounds):
    """Top of her head (y) per cut range: median over the range of the mask's top row in the middle columns.
    The punch-in alternates per range, so her head sits ~75 px higher on every other cut."""
    tops = []
    for a, b in bounds:
        ys = []
        for i in range(int(a * FPS), min(int(b * FPS), len(masks)), 3):
            bb = Image.open(masks[i]).convert("L").crop((300, 0, 780, H)).point(lambda v: 255 if v > 128 else 0).getbbox()
            if bb:
                ys.append(bb[1])
        tops.append(sorted(ys)[len(ys) // 2] if ys else 540)
    return tops


def frames_of(video, name):
    d = WORK / f"{name}_frames"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps={FPS}", str(d / "%04d.png")])
    return d, sorted(d.glob("*.png"))


def encode(frame_fn, n, audio_src, out):
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(audio_src), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "17",
         "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-shortest", str(out)],
        stdin=subprocess.PIPE)
    for i in range(n):
        ff.stdin.write(frame_fn(i).tobytes())
    ff.stdin.close()
    if ff.wait():
        sys.exit(f"encode failed: {out}")
    return out


def face_part(name, src, blocks, text, title=None, title_until=None, chips=(), covers=None, sfx=(),
              overlay=None):
    """Talking-head part.

    title: (line1, line2), both behind her head (line2 on a mint label her head overlaps); until word title_until.
    chips: [(text, word, n, y, fg, bg)] pop in at that word and stay, over the curtain (y < 600).
    covers: {block index, (first, last) or ("t", src_start, src_end): card_fn(t)} full-screen card (voice continues).
    sfx: [(word, n, kind)] or [(block index, seconds after its start, kind)].
    overlay: fn(img, t, words) for anything extra (e.g. a name tag), drawn before captions.
    """
    clip, ranges, spans = cut_face(src, blocks, name)
    tokens, times = word_times(clip, name, text, spans)
    w = Words(tokens, times, spans)
    caps = Captions(tokens, times, duration(clip), CAP_Y)
    fdir, frames = frames_of(clip, name)
    covers = covers or {}
    cover_spans = []
    def out_time(src_t):  # source seconds -> seconds in the cut clip
        o = 0.0
        for a, b in ranges:
            if a <= src_t <= b:
                return o + src_t - a
            o += b - a
        sys.exit(f"{name}: cover time {src_t} is not inside a kept range {ranges}")

    for key, fn in covers.items():  # key: block index, (first, last) block indices, or ("t", src_start, src_end)
        if isinstance(key, tuple) and key[0] == "t":
            cover_spans.append((out_time(key[1]), out_time(key[2]), fn))
            continue
        i0, i1 = key if isinstance(key, tuple) else (key, key)
        cover_spans.append((spans[i0][0] - 0.05, spans[i1 + 1][0] - 0.05 if i1 + 1 < len(spans) else 1e9, fn))
    masks, tops, bounds, smooth = None, [], [], k.MaskSmoother()
    t_title_end = w.at(*title_until) if title and title_until else 1e9
    if title:
        mdir = WORK / f"{name}_masks"
        k.segment(fdir, mdir)
        masks = sorted(mdir.glob("*.png"))
        o = 0.0
        for a, b in ranges:
            bounds.append((o, o + b - a))
            o += b - a
        tops = head_tops(masks, bounds)
    chip_times = [(c[0], w.at(c[1], c[2]), c[3], c[4], c[5]) for c in chips]

    def frame(i):
        t = i / FPS
        for a, b, fn in cover_spans:
            if a <= t < b:
                out = fn(t - a)
                caps.paste(out, t)
                return out
        base = Image.open(frames[min(i, len(frames) - 1)]).convert("RGB")
        out = base.copy()
        if title and t < t_title_end + 0.2:
            a = 1.0 - k.ease((t - t_title_end) / 0.2) if t > t_title_end else 1.0
            mask = smooth(Image.open(masks[min(i, len(masks) - 1)]))
            y1 = next((tp for (ra, rb), tp in zip(bounds, tops) if ra <= t < rb), tops[-1]) - 140
            layer = fade(title_layer(y1, title[0], min(1.04, k.back(t / 0.35)), title[1],
                                     min(1.04, k.back((t - 0.25) / 0.4))), a)
            out.paste(layer, (0, 0), layer)
            out.paste(base, (0, 0), mask)
        for text, ct, y, fg, bg in chip_times:
            float_chip(out, text, W // 2, y, k.back((t - ct + 0.1) / 0.35), fg=fg, bg=bg)
        if overlay:
            overlay(out, t, w)
        caps.paste(out, t)
        return out

    out = encode(frame, len(frames), clip, WORK / f"{name}.mp4")
    events = [((w.spans[wd][0] + n) if isinstance(wd, int) else w.at(wd, n), kind) for wd, n, kind in sfx]
    events += [(a + 0.02, "whoosh") for a, _, _ in cover_spans]
    if title:
        events += [(0.02, "pop"), (0.25, "pop")]
    return out, events


def explainer_part(name, blocks, text, scene_fn, sfx=(), header=None):
    """Voice-over over drawn scenes. scene_fn(img, d, t, w) draws the current scene."""
    vo, spans = cut_audio(MEMO, blocks, name)
    tokens, times = word_times(vo, name, text, spans)
    w = Words(tokens, times, spans)
    total = duration(vo) + 0.15
    caps = Captions(tokens, times, total, 1490)

    def frame(t):
        img = k.grid_bg()
        d = ImageDraw.Draw(img)
        if header:
            k.chip(d, 90, 250, header)
        scene_fn(img, d, t, w)
        caps.paste(img, t)
        return whip(img, t)

    out = render(frame, int(total * FPS), WORK / f"{name}.mp4", vo)
    return out, [(0.0, "pop")] + [(w.at(wd, n), kind) for wd, n, kind in sfx]


# ---------- end card and assembly ----------

def end_card(tease):
    def draw(t):
        img = k.grid_bg()
        d = ImageDraw.Draw(img)
        k.chip(d, 90, 250, "NexGen AI Labs")
        p1, p2, p3, p4 = (k.back((t - s) / 0.4) for s in (0.0, 0.3, 0.6, 1.1))
        if p1 > 0:
            d.text((W // 2, 640), "AI in your app,", font=k.sans(int(96 * min(1.04, p1)), 800), fill=PAPER,
                   anchor="ms")
            d.text((W // 2, 770), "built properly.", font=k.sans(int(96 * min(1.04, p1)), 800), fill=MINT,
                   anchor="ms")
        if p2 > 0:
            pill(d, W // 2, 935, "nexgenailab.com", int(70 * min(1.04, p2)))
        if p3 > 0:
            d.text((W // 2, 1080), "link in bio", font=k.sans(42, 600, 24), fill=MINT, anchor="mm")
        if p4 > 0 and tease:
            d.text((W // 2, 1330), tease[0], font=k.sans(40, 500, 24), fill=SAGE, anchor="mm")
            d.text((W // 2, 1400), tease[1], font=k.sans(int(fit(d, tease[1], 800, 54, 940) * min(1.04, p4)), 800),
                   fill=PAPER, anchor="mm")
        return img
    return draw


def assemble(parts_sfx, tease, out_name, card_len=2.6):
    card = render(end_card(tease), int(card_len * FPS), WORK / "endcard_v.mp4")
    card_a = WORK / "endcard.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(card), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-shortest", "-c:v", "copy", "-c:a", "aac", str(card_a)])
    parts = [level_voice(p) for p, _ in parts_sfx] + [card_a]
    durs = [duration(p) for p in parts]
    total = sum(durs)
    starts = [sum(durs[:i]) for i in range(len(parts))]
    n = len(parts)
    events = [(starts[i] + t, s) for i, (_, ev) in enumerate(parts_sfx) for t, s in ev]
    events += [(starts[-1] + t, "pop") for t in (0.0, 0.3, 1.1)] + [(starts[i] - 0.16, "whoosh") for i in range(1, n)]
    stem = k.sfx_stem(events, total, WORK / "sfx.wav")
    music_start = max(0.0, MUSIC_DROP - durs[0])
    norm = "aformat=sample_rates=48000:channel_layouts=stereo"
    graph = (
        "".join(f"[{i}:v]setsar=1,fps={FPS}[v{i}];[{i}:a]{norm}[a{i}];" for i in range(n))
        + "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][voice];"
        f"[{n}:a]atrim={music_start:.2f}:{music_start + total:.2f},asetpts=PTS-STARTPTS,{norm},"
        f"volume='if(lt(t,{starts[-1]:.2f}),0.028,0.1)':eval=frame,"
        f"afade=t=in:d=0.6,afade=t=out:st={total - 0.8:.2f}:d=0.8[bed];"
        f"[{n + 1}:a]{norm}[fx];"
        "[voice][bed][fx]amix=inputs=3:duration=first:normalize=0[a]"
    )
    mixed = WORK / "mixed.mov"
    run(["ffmpeg", "-v", "error", "-y", *sum((["-i", str(p)] for p in parts), []), "-i", str(MUSIC),
         "-i", str(stem), "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
         "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(mixed)])
    gain = -14.0 - lufs(mixed)
    final = OUT / f"{out_name}.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(mixed), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=false",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(final)])
    print(final, f"{duration(final):.1f}s", "parts", [round(x, 2) for x in durs])
    return final
