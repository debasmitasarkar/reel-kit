# Style rules the scripts follow

These came from measuring one reference Reel frame by frame (2 frames per second: layout, caption size,
how often the picture changes) and then checking my own first Reels against it.

1. **Captions:** one or two words at a time, big (about 104 px on a 1080x1920 frame), white with a dark
   outline, each word appearing when it is said. Never left hanging more than half a second into a pause.
2. **List Reels get a header that stays up:** title box, a numbered step chip, and a segmented progress bar
   that fills as the step is spoken (`step_header`).
3. **Explainers:** one full scene per step, labels 56 px or larger, a quick whip into each new scene, and a
   visible change at least every two seconds inside a scene (a pop, a tick, a slide, a fill).
4. **Hook:** a visual event at least every three seconds: title, chip, card. No ten seconds of face alone.
5. **Still cards longer than two seconds get motion** (for example `question_card(answers=...)` types
   example answers into the field).
6. **The title sits behind your head.** Both lines are drawn first, then you are pasted back on top using
   the person mask, so your head overlaps the bottom of the key line.
7. **Keep your face on screen while you explain** whenever the explanation was recorded on camera: put the
   facts on cards above your head instead of cutting away.
8. **Prompter glances get covered.** `inspect_take.py` flags them; put a full-screen card over that block
   and let the voice carry on.
9. **Never speed up or clip the voice.** Cuts happen in the middle of a pause, with short fades, and pauses
   up to 0.45 s are kept as they were spoken.
10. **Pauses that carry a joke or a reaction:** use speech-only blocks and raise `MAX_PAUSE` for that part.
    A block with silence inside it gets its words mistimed.
11. **Every number on screen is measured or sourced**, with the source on the card.
12. **Sound:** effects about 10 dB under the voice, music well under the voice, final loudness -14 LUFS.

Safe zone for anything that matters: x 60-990, y 180-1500. The apps cover the rest.
