"""Smallest complete Reel: face hook -> voice-over explainer -> face close -> end card.

1. Put a face take and a voice memo in media/raw/ and a music track at media/raw/music/track.mp3.
2. Find your speech blocks:   python3 tools/video/inspect_take.py media/raw/face.mp4 0 60
3. Paste the (start, end) pairs below, with the words you said, then:
       python3 tools/video/example_reel.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import reelbuild as r  # noqa: E402
from reelbuild import CORAL, INK, MINT, PAPER, PINE, W, k  # noqa: E402

FACE = r.RAW / "face.mp4"
r.MEMO = r.RAW / "voice_memo.m4a"

HOOK = [(1.20, 3.40), (3.90, 6.10)]  # speech blocks from inspect_take.py
HOOK_TEXT = "Replace this with exactly what you say in the hook. Every word, in order."
VO = [(0.50, 2.80), (3.30, 5.90), (6.40, 9.00)]
VO_TEXT = "One. The first point you explain. Two. The second point. Three. The third point."
CLOSE = [(20.10, 22.60)]
CLOSE_TEXT = "The link is in my bio."

STEPS = [("1", "First point", 0), ("2", "Second point", 1), ("3", "Third point", 2)]  # (chip, label, VO block)


def scene(img, d, t, w):
    """Draw the explainer frame at time t. w.at("word") = when a word is said; w.spans[i] = block i (start, end)."""
    starts = [max(0.0, w.spans[b][0] - 0.12) for *_x, b in STEPS]
    i = max(j for j, s in enumerate(starts) if t >= s or j == 0)
    lt = t - starts[i]
    r.row(d, 760, STEPS[i][0], MINT, STEPS[i][1], k.back(lt / 0.35), sub="draw anything you like here")
    if i:
        img.paste(r.whip(img.copy(), lt))
    r.step_header(img, "Your series title", STEPS[i][0], STEPS[i][1], len(STEPS), i + min(1.0, lt / 2), k.back(lt / 0.3))


def main():
    r.setup("example")
    hook = r.face_part("hook", FACE, HOOK, HOOK_TEXT, title=("Your title", "behind your head"),
                       title_until=("Every", 0), sfx=[("Every", 0, "tick")])
    mid = r.explainer_part("vo", VO, VO_TEXT, scene, sfx=[("One.", 0, "pop"), ("Two.", 0, "pop"), ("Three.", 0, "pop")])
    close = r.face_part("close", FACE, CLOSE, CLOSE_TEXT,
                        chips=[("yoursite.com · link in bio", "link", 0, 330, PAPER, PINE)])
    r.assemble([hook, mid, close], ("Tomorrow:", "your next Reel"), "example_reel")


if __name__ == "__main__":
    main()
