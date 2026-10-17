#!/usr/bin/env python3
"""Caption words from the VERBATIM pass, mapped into the cut timeline.

Whisper's transcript is what autocut writes to captions.json, and it smooths
repeats away and mangles words, worst on proper nouns and outside English
(in one Portuguese take it wrote a nonsense phrase for a whole line). CrisperWhisper's verbatim
words (workdir/verbatim.json, raw timeline) are right, so this maps them
through timemap.json into the cut timeline, drops bracketed tags ([UH],
[laughter]) and writes the same shape autocut uses: [{"text","startMs","endMs"}].

Spelled-out numbers become digits, because "8 MIL" reads and "oito mil" does
not (only unambiguous number words; "um/uma" stay, they are articles too).

    verbatim_cut_words.py <workdir> -o words.json [--lang pt]
"""
import argparse, json, re
from pathlib import Path

PT = {"dois": "2", "duas": "2", "três": "3", "tres": "3", "quatro": "4", "cinco": "5", "seis": "6", "sete": "7",
      "oito": "8", "nove": "9", "dez": "10", "onze": "11", "doze": "12", "vinte": "20", "trinta": "30", "quarenta": "40",
      "cinquenta": "50", "sessenta": "60", "setenta": "70", "oitenta": "80", "noventa": "90", "cem": "100"}
EN = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
      "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100"}

def digits(words, table):
    out = []
    i = 0
    while i < len(words):
        w = words[i]; core = re.sub(r"[^\w]", "", w["text"].lower()); punct = re.sub(r"^[\w]+", "", w["text"])
        # "cento e cinco" -> 105
        if core == "cento" and i + 2 < len(words) and re.sub(r"[^\w]", "", words[i+1]["text"].lower()) == "e":
            nxt = re.sub(r"[^\w]", "", words[i+2]["text"].lower())
            if nxt in table and len(table[nxt]) == 1:
                out.append({"text": "10" + table[nxt] + re.sub(r"^[\w]+", "", words[i+2]["text"]), "startMs": w["startMs"], "endMs": words[i+2]["endMs"]}); i += 3; continue
        if core in table:
            out.append({**w, "text": table[core] + punct})
        else:
            out.append(w)
        i += 1
    return out

ap = argparse.ArgumentParser()
ap.add_argument("workdir"); ap.add_argument("-o", "--output", required=True); ap.add_argument("--lang", default="pt")
a = ap.parse_args(); wd = Path(a.workdir)
vb = json.loads((wd / "verbatim.json").read_text()); vwords = vb["words"] if isinstance(vb, dict) else vb
tm = json.loads((wd / "timemap.json").read_text())["entries"]
out = []
for e in tm:
    s, z, off = e["srcStart"], e["srcEnd"], e["outOffset"]
    for w in vwords:
        # a word that starts within a frame before the piece (frame-grid rounding) is still spoken in it
        if not (s - 0.04 <= w["start"] < z - 0.05): continue
        t = w["word"].strip()
        if not t or re.fullmatch(r"\[.*\]", t): continue
        out.append({"text": t, "startMs": round((w["start"] - s + off) * 1000), "endMs": round((min(w["end"], z) - s + off) * 1000)})
out = digits(out, PT if a.lang.startswith("pt") else EN)
Path(a.output).write_text(json.dumps(out))
print(f"{len(out)} words -> {a.output}")
