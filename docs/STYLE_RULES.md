# Style rules

The craft this pipeline enforces. Every rule here exists because breaking it produced a draft that
got rejected, and most of them are cheap to check before a render. They are neutral: they apply to a
finance explainer, a cooking channel, a dev log or a founder update alike.

The meta-rule: **every effect has a purpose, an entry word and an exit word, all from the
transcript.** If you cannot name all three, the effect does not go in.

## The cut

1. **Repetitions, false starts and restarts are cut by default.** Finding them and leaving them in
   is the failure. Keep the LAST take; when a pause sits between two takes, the pause is where the
   second take starts.
2. **Check every cut with a verbatim transcript of the cut**, read end to end. Regular Whisper
   smooths repeats away and will tell you a broken cut is clean.
3. **Measure sync per file from the lips. Never hardcode an offset.** Wireless mics and capture
   software drift by session.
4. **Edges live in real silence** (under -55 dB). A cut at an energy dip inside connected speech
   clips the word. Keep at least ~0.2 s of air after a kept word's tail; 0.1 s runs sentences together.
5. **No stitched piece under 1 s without speech.** A silent sliver between two jump cuts reads as a
   glitch.
6. **Pauses have a rhythm.** Cap only the long ones (over ~0.65 s down to ~0.5 s heard); short pauses
   are the speaker's breath. Scripted pauses (a beat before a reveal) are content: keep them.
7. **Constant frame rate.** Recorders drop frames under load; a variable-rate cut makes every
   frame-indexed effect drift by the end.

## The open

8. **Face first.** The first 2-3 s are the speaker's face, and frame 0 is already a strong,
   readable image (not a fade from black). No full-screen graphic before ~2.5 s. Feeds autoplay
   muted; a stats-first open reads as an infographic and gets scrolled past.

## Camera moves

9. **Punches are sentence-long, few and purposeful.** Land as the key sentence builds, hold through
   it, release on its last word or the next pause. **Never a one-word punch**: it is a twitch.
   On long form roughly one per 30-45 s of talking head, only on key lines.
10. **Punches come from the transcript, never from a timer.** Read the whole transcript, find every
    moment with weight, place punches there, then check spacing. Never the reverse: evenly spaced
    zooms are the clearest tell of automated editing, and so are obvious beats left flat.
11. **Two linked phrases: punch the half that carries the story** (the reveal, not the setup).
12. **One push per passage with a nested accent** instead of three punches in one sentence.
13. **Every curve eases at both ends; nothing attacks in under ~12 frames.** Quadratic in-out to push,
    sine in-out to release (a release that gets noticed has failed).
14. **Anchor zooms on the tracked face**, and lock reframes to the face position on the landing
    frame. A camera that chases the subject reads as a cheap gimbal.
15. **On UI, a zoom is a real zoom** (1.6-2.2x), centred on the element so its left and right margins
    are pixel-equal. No small sideways nudges. Fixed chrome (a logo, a source line) fades while the
    camera is pushed in.
16. **No text sliced by a zoom or by the frame edge.** Zoomed content fades out above the caption
    band (the `World` edge fade); captions never zoom.
17. **Screen-share segments get no punches, no captions, no cards.** The screen is the interest.

## Captions

18. **Fixed lower third, same position and style everywhere**: talking head, side layout, screen
    scene. UI layers reserve that band and sit above it. Head-tracked captions are off unless asked.
19. **Emphasis = accent typeface AND bigger (1.22x), never one without the other.** A font swap alone
    reads as a bug; size alone reads as a mistake.
20. **Emphasis applies to whole phrases** ("cash flow", "the first ten customers"), and a caption card
    never breaks inside an emphasised phrase.
21. **A word the captions emphasise is a punch candidate.** The two systems must not disagree.
22. **Proofread proper nouns.** Grep the transcript for every brand, product and name before building
    captions; the model mangles them and the sentence still reads fluently. Numbers as digits.
23. Max two lines. No em dashes on screen.

## Graphics and layout

24. **Nothing on the face.** Captions, cards, chips, logos, 3D objects: move it, shrink it, or put it
    behind the speaker with roto. Check the face box over the whole window, with margin for movement.
25. **No boxed text chips over the speaker.**
26. **No one-sided accent lines** (a coloured bar on the top, left or any single edge of a card). It
    is the first tell of a generated UI. Highlight with a fill tint, a full even border, or text colour.
27. **Whole-frame fades only.** Never fade the containers while the title stays.
28. **Transitions: fade + blur (default), plain fade, or a liquid stinger.** Never a zigzag/jagged-teeth
    shutter: it cheapens everything around it.
29. **Cards are sized to their content.** No empty bands; a card grows on its word.
30. **Objects in the room live in world space** (inside the punch transform), so they scale and drift
    with the speaker. Screen-pinned objects read as stickers on the lens.
31. **A reframe ships with what it makes room for.** A camera move toward an empty wall gives the
    viewer nothing and the reviewer nothing to approve.
32. **Go big when there is room.** Logos and badges about twice the size instinct suggests; 3D type
    with equal padding from every frame edge (at least ~90 px at 1080 wide).
33. **Hero word behind the speaker: above the head, every glyph readable.** A number must read as the
    number: no digit may sit fully behind the head. Check a still at landing + 25.
34. **Roto is rationed.** It costs ~12 minutes of compute per minute of footage. Openers and hero
    moments; 15 s per video by default.
35. **Objects and icons are real logos or sourced/generated images.** Code draws motion, text, UI and
    charts, not objects (arrowheads especially).
36. **Recreated product UI is one-to-one.** Same labels, layout, fields and flow as the real app; only
    the data is yours, and it is real. Never "improve" a UI you are depicting.

## Numbers and truth

37. **Verify every number on screen.** It equals what the speaker says, or a value fetched and saved
    with its source and time. Never invent a number to fill a card or a chart.
38. **Facts on screen come from the script's facts**, not from what would look good.

## Sound

39. **Every SFX is tied to something visible**: a transition, a hero landing, a hard punch, a card,
    a click. No sound without a visible cause.
40. **Subtle.** Audible when you listen for it, never competing with the voice: median ~10 dB under
    the voice, accents at voice level at most. Start low (linear volumes ~0.01-0.05 against a voice at
    -14 LUFS) and go up only if inaudible.
41. **Measure the render's audio delay and trim it** (`sync_trim.sh`). Final |offset| under 5 ms.

## Process

42. **Plan gate before anything expensive.** Inventory, observations, proposed plan, the human's go,
    then build. Re-read the plan from disk after approval.
43. **Stills before renders, patches before re-renders.** A still costs seconds, a patch minutes, a
    full render the afternoon.
44. **Ask when wording is ambiguous.** One specific question beats a conservative guess.
45. **Hold the ETA.** Pipeline fixes found mid-job get the minimum patch; start rendering as soon as
    the plan is right.
