"""Print what's in a stretch of a face clip, to pick cut points: words (whisper, with absolute times),
pauses (silencedetect -40 dB) and prompter glances (gaze.swift, eyes down >= 0.4 s).

    python3 tools/video/inspect_take.py media/raw/E42380DF-....MP4 112 186
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = Path.home() / "whisper-models/ggml-small.en.bin"


def words(src, a, b, tmp):
    wav = tmp / "seg.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", str(src), "-map", "0:a:0",
                    "-ac", "1", "-ar", "16000", str(wav)], check=True, stdin=subprocess.DEVNULL)
    subprocess.run(["whisper-cli", "-m", str(MODEL), "-f", str(wav), "-ml", "1", "-sow", "-ojf", "-of",
                    str(tmp / "seg"), "-np"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   stdin=subprocess.DEVNULL)
    segs = json.load(open(tmp / "seg.json"))["transcription"]
    out = [(a + s["offsets"]["from"] / 1000, a + s["offsets"]["to"] / 1000, s["text"].strip())
           for s in segs if s["text"].strip()]
    log = subprocess.run(["ffmpeg", "-v", "info", "-i", str(wav), "-af", "silencedetect=n=-40dB:d=0.25", "-f",
                          "null", "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL).stderr
    st = [a + float(x) for x in re.findall(r"silence_start: ([0-9.]+)", log)]
    en = [a + float(x) for x in re.findall(r"silence_end: ([0-9.]+)", log)]
    return out, list(zip(st, en))


def glances(src, a, b, tmp):
    gz = ROOT / "media/out/gaze_bin"
    if not gz.exists():
        subprocess.run(["swiftc", "-O", str(ROOT / "tools/video/gaze.swift"), "-o", str(gz)], check=True)
    d = tmp / "frames"
    d.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", str(src), "-vf",
                    "fps=5,scale=540:960", "-q:v", "4", str(d / "%05d.jpg")], check=True, stdin=subprocess.DEVNULL)
    rows = subprocess.run([str(gz), str(d)], capture_output=True, text=True).stdout.splitlines()
    down = [len(r.split()) == 3 and r.split()[1] != "nan" and float(r.split()[1]) < 0.21 for r in rows]
    out, i = [], 0
    while i < len(down):
        j = i
        while j < len(down) and down[j]:
            j += 1
        if j - i >= 2:
            out.append((a + i / 5, a + j / 5))
        i = max(j, i + 1)
    return out


def blocks(src, a, b, tmp, sil):
    """Speech between pauses, each block transcribed on its own (boundaries exact, words reliable)."""
    edges, cur = [], a
    for s, e in sil:
        if s - cur > 0.15:
            edges.append((cur, s))
        cur = e
    if b - cur > 0.15:
        edges.append((cur, b))
    out = []
    for x, y in edges:
        wav = tmp / "blk.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, x - 0.1):.2f}", "-to", f"{y + 0.1:.2f}", "-i",
                        str(src), "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-af", "apad=pad_dur=0.6", str(wav)],
                       check=True, stdin=subprocess.DEVNULL)
        txt = subprocess.run(["whisper-cli", "-m", str(MODEL), "-f", str(wav), "-nt", "-np"], capture_output=True,
                             text=True, stdin=subprocess.DEVNULL).stdout.strip().replace("\n", " ")
        out.append((x, y, txt))
    return out


def main():
    src, a, b = Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
    tmp = Path(tempfile.mkdtemp())
    try:
        _, sil = words(src, a, b, tmp)
        has_video = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                                   "stream=index", "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip()
        gl = glances(src, a, b, tmp) if has_video else []
        for x, y, txt in blocks(src, a, b, tmp, sil):
            read = [f"{g0:.1f}-{g1:.1f}" for g0, g1 in gl if g0 < y + 0.2 and g1 > x - 0.2]
            print(f"{x:7.2f}-{y:7.2f}  {txt}" + (f"   <<READING {' '.join(read)}>>" if read else ""))
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
