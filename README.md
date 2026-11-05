# Reel kit: edit Reels with Claude Code, no editing app

This is the setup behind the Reels on [@debo.builds.ai](https://www.instagram.com/debo.builds.ai/).
I record my face and one voice memo. Claude Code writes a short Python script per Reel, and this kit
cuts the takes, times the captions to my words, puts the title behind my head, draws the animated
scenes, adds sound effects and music, and exports a 1080x1920 file.

No editing app, no paid tools, no cloud. Everything runs on a Mac.

## What you need

- A Mac with Apple Silicon (the person cut-out uses Apple's Vision framework through Swift).
- Xcode command line tools: `xcode-select --install`
- `brew install ffmpeg whisper-cpp`
- Python 3 with Pillow: `python3 -m pip install pillow`
- A Whisper model, saved where the scripts look for it:
  ```
  mkdir -p ~/whisper-models
  curl -L -o ~/whisper-models/ggml-small.en.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
  ```
- [Claude Code](https://claude.com/claude-code), to write and adjust the per-Reel scripts.
- Your own music track at `media/raw/music/track.mp3`. None is included, because music licences do not transfer.

## How a Reel gets made

1. **Record.** One or more face takes on a phone (vertical, 4K if you can), and one voice memo with the
   explanation. Say each line, pause, say the next. Mistakes are fine: repeat the line and carry on.
   Copy the files into `media/raw/`.
2. **Find the good parts.**
   ```
   python3 tools/video/inspect_take.py media/raw/face.mp4 0 60
   ```
   This prints every stretch of speech with its start and end time, what was said, and a flag where your
   eyes drop to read a prompter.
3. **Write the Reel script.** Copy `tools/video/example_reel.py`, paste in the speech blocks you want to keep
   and the exact words, and describe each scene. This is the part Claude Code does for me; the prompt I use
   is below.
4. **Render.**
   ```
   python3 tools/video/example_reel.py
   ```
   The file lands in `media/out/`.
5. **Check it.** Transcribe the result and look at frames across the whole Reel before posting:
   ```
   ffmpeg -i media/out/example_reel.mp4 -ar 16000 -ac 1 /tmp/check.wav
   whisper-cli -m ~/whisper-models/ggml-small.en.bin -f /tmp/check.wav -nt
   ffmpeg -i media/out/example_reel.mp4 -vf "fps=1/1.5,scale=216:384,tile=9x3" -frames:v 1 /tmp/sheet.png
   ```

## The prompt I give Claude Code

> Read STYLE.md and tools/video/reelbuild.py. My face take is media/raw/face.mp4 and my voice memo is
> media/raw/voice_memo.m4a. Run inspect_take.py on both, pick the last clean take of every line, and write
> tools/video/build_myreel.py in the style of example_reel.py: title behind my head in the hook, one scene
> per step in the explainer with the step header, a card over any block where I read the prompter. Do not
> speed up or clip my voice. Render it, then transcribe the result and show me a contact sheet of frames.

## What is in here

| File | What it does |
|---|---|
| `tools/video/reelbuild.py` | The builder: cuts at pauses, word timings, captions, title behind the head, cover cards, scenes, sound effects, music, loudness |
| `tools/video/reelkit.py` | Colours, fonts, background, cards, chips, hand-drawn circle, sound-effect synthesis |
| `tools/video/inspect_take.py` | Lists the speech blocks, words and prompter glances in a take |
| `tools/video/segment.swift` | Person mask per frame (Apple Vision), used to put the title behind you |
| `tools/video/gaze.swift` | Eye openness and pupil position per frame, used to spot prompter reading |
| `tools/video/example_reel.py` | The smallest complete Reel script |
| `STYLE.md` | The style rules the scripts follow, and where they came from |

## Things to know before you rely on it

- It is tuned to one setup: a seated person, phone on a stand, face in the lower half of the frame.
  `FACE_CX` and `ZOOMS` at the top of `reelbuild.py` set the crop; change them for your framing.
- Word timings come from Whisper and are corrected against pauses. They are good, not perfect; always do
  step 5.
- The colours and fonts are my brand. Change the palette at the top of `reelkit.py`.
- The end card says my business name and site. Change the text in `end_card()` in `reelbuild.py`.
- Rendering a 40 second Reel takes two to four minutes on an M-series Mac.

## Licence

Code: MIT (see `LICENSE`). Fonts: SIL Open Font License (see `assets/fonts/OFL-*.txt`).

Built by [Debasmita Sarkar](https://nexgenailab.com), NexGen AI Labs. If you want AI built into your own
app, that is what I do: [nexgenailab.com](https://nexgenailab.com).
