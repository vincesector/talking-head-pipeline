#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Find stumbles (false starts, self-repeats, filler words) inside a VERBATIM
transcript -- one produced by CrisperWhisper in verbatim mode, not mlx-whisper.

Why this exists: mlx-whisper SMOOTHS repetitions out of its own transcript.
"So let's talk about, so let's talk about what happened" comes back from
mlx-whisper as "So let's talk about what happened" -- the abandoned first
attempt is gone before find_retakes.py (which compares whole SEGMENTS) ever
gets a look at it, because there is no second segment to compare against.
CrisperWhisper's verbatim mode transcribes every stumble, with tight word
timing, so this script can see them: it scans WORDS, not segments.

Precision over recall: a wrong cut costs a reshoot, a missed stumble costs
one manual cut. Only a repeat the rules are confident about gets `"apply":
true`; anything murkier is written out as a `"restart?"` candidate for a
human to accept, never auto-cut.

Four kinds of span, all found by scanning the word list left to right:

1. fragment -- a raw word ending in "-" (a false start CrisperWhisper writes
   as e.g. "mo-"). Drops [start(frag), start(next word)). Always applied.
2. repeat -- a phrase said, abandoned, and said again. Tries n-gram lengths
   6 down to 1 at each position, looking for the same n-gram again within 4
   words. Filler words (see below) are transparent to this matching -- "the
   [UH] the analytics" is an immediate repeat of "the". How confidently it's
   applied depends on how far apart the two occurrences are and whether a
   clause boundary (a comma, period, etc.) sits between them:
     - 0 words apart ("immediate"): applied regardless of punctuation, if
       the restart begins within 1.2s. n==1 additionally needs either a
       real gap (>=0.12s) or a fully-adjacent one (~0s, likely a genuine
       stammer) between the two words, or a fragment between them -- a
       small-but-real gap ("very very good") is fluent emphasis, not a
       stumble. very/really/super/many/much are never cut at n==1: they're
       intensifiers, not stumbles.
     - 1-2 words apart: applied only if the phrase is 3+ words long, AND
       nothing in between (the last word of the first occurrence, or any
       intervening word) ends a clause (`, . ? ! : ;`) -- an abandonment
       mid-clause is what makes it a restart. A 2-word phrase here, or a
       clause boundary anywhere, or 3-4 words apart with no clause
       boundary, is written out as an unapplied `restart?` candidate
       instead. Beyond 4 words apart, punctuation at 3-4 words apart, or a
       number word sitting in between ("we did the eighty-seven ... the
       eighty-eight" -- content being narrated, not a stumble remnant),
       isn't flagged at all.
   Two more guards apply everywhere: a number word between the two
   occurrences means it isn't a stumble at all (a repeated scaffold around
   changing numbers is a list or a range, not a restart), and an immediate
   multi-word match whose own phrase recurs yet again a few words later is
   a deliberate anaphoric list ("if you have seen, if you have watched, if
   you have been watching"), not a restart, and isn't flagged either.
   On any match, the actual restart point is wherever the biggest silence
   gap falls between the two occurrences (not just "at the second
   occurrence"), so a genuine pause-then-restart keeps the transitional
   word ("almost" in "two weeks ago, [pause] almost two weeks ago") while a
   same-breath correction drops it ("you could have been | you could have
   made" has ~no gap, so "been" goes too). Chained restarts ("so so around
   half so around half") collapse fully: the scan resumes right after each
   applied match, so a second stumble immediately following the first is
   caught in the same left-to-right pass, and adjacent applied spans merge
   into one; an unconfident restart? match doesn't consume its tokens the
   same way, so a confident stumble sitting inside its span still gets
   found on its own.
3. restart? -- a repeat pattern found but not confident enough to auto-cut
   (see above). Never applied; a human decides.
4. filler -- um, uh, uhm, hmm, erm, ah, or any [BRACKETED] disfluency tag.
   Listed for a human to decide on, never applied on its own (though one
   swallowed inside an applied repeat span is not listed twice).

This never deletes audio. It writes a JSON list of spans, each flagged
`"apply": true` (fragment, confident repeat) or `"apply": false` (filler,
restart? candidate) -- what a caller does with that flag is the caller's
decision.

Usage:
    uv run find_stumbles.py <verbatim.json> [--offset SECONDS] [-o out.json] [--print]
"""
import argparse
import json
import re
import sys
from pathlib import Path

MAX_N = 6
MAX_GAP_WORDS = 4  # how many CONTENT words ahead of the first occurrence to look for a repeat
MAX_RESTART_GAP_S = 1.2  # how long a silence can separate the two occurrences and still count
MIN_SINGLE_WORD_GAP_S = 0.12
RESTART_TIE_EPSILON = 0.12  # see _restart_point
CLAUSE_PUNCT = set(",.?!:;")
FILLER_WORDS = {"um", "uh", "uhm", "hmm", "erm", "ah"}  # English only; see set_language()
LANG = "en"


def set_language(lang):
    """Only English gets the spelled-out filler list. In Portuguese "um" is the
    article ("um desafio"), so for every other language a filler is only a
    bracketed tag like [UH] or [laughter]."""
    global LANG
    LANG = (lang or "en").lower()[:2]
INTENSIFIERS = {"very", "really", "super", "many", "much"}
NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "hundred", "thousand", "million", "billion",
}


def normalize(word):
    return re.sub(r"[^\w]", "", word.lower(), flags=re.UNICODE)


def is_fragment(raw_word):
    return raw_word.strip().endswith("-")


def is_number_word(raw_word):
    """A number sitting between two occurrences of a phrase ('we did the
    eighty-seven ... we did the eighty-eight', 'a hundred and five or a
    hundred and six') is the actual content being narrated, not a
    discardable stumble remnant -- a repeated scaffold around changing
    numbers is a list or a range, never a restart."""
    if any(c.isdigit() for c in raw_word):
        return True
    return any(part.lower() in NUMBER_WORDS for part in re.findall(r"[A-Za-z]+", raw_word))


def is_filler_transparent(raw_word):
    """um/uh/... and any [BRACKETED] disfluency tag (CrisperWhisper writes
    tags like [UH], [UM]) -- invisible to n-gram matching, and swallowed
    into a repeat span's drop when they sit between the two occurrences."""
    w = raw_word.strip()
    if len(w) >= 2 and w[0] == "[" and w[-1] == "]":
        return True
    return LANG == "en" and normalize(w) in FILLER_WORDS


def ends_with_clause_punct(raw_word):
    w = raw_word.rstrip()
    return bool(w) and w[-1] in CLAUSE_PUNCT


def load_words(path, offset):
    data = json.loads(Path(path).read_text())
    words = []
    # autocut saves the verbatim pass as a bare list; the backend prints {"words": [...]}
    for w in (data["words"] if isinstance(data, dict) else data):
        words.append({"word": w["word"], "start": w["start"] + offset, "end": w["end"] + offset})
    return words


# ------------------------------------------------------------- span finding

def find_fragment_spans(words):
    spans = []
    for i, w in enumerate(words):
        if is_fragment(w["word"]) and i + 1 < len(words):
            spans.append({"kind": "fragment", "apply": True, "from_idx": i, "to_idx": i + 1, "n": 1})
    return spans


def find_filler_spans(words):
    spans = []
    for i, w in enumerate(words):
        if is_filler_transparent(w["word"]):
            spans.append({"kind": "filler", "apply": False, "from_idx": i, "to_idx": i + 1, "n": 1})
    return spans


def find_repeat_spans(words, tokens):
    """Scan left to right over CONTENT words (fillers are transparent). At
    each position, try n-gram lengths from MAX_N down to 1, looking for the
    same n-gram again within MAX_GAP_WORDS content words. On any match --
    applied or a flagged restart? candidate -- resume scanning right after
    it, so a chain of stumbles collapses in one pass instead of needing
    multiple re-scans."""
    n_words = len(words)
    content_idx = [i for i in range(n_words) if not is_filler_transparent(words[i]["word"])]
    content_tokens = [tokens[i] for i in content_idx]
    pos_of = {orig: p for p, orig in enumerate(content_idx)}

    spans = []
    i = 0
    while i < n_words:
        if is_filler_transparent(words[i]["word"]):
            i += 1
            continue
        match = _find_repeat_at(words, content_tokens, content_idx, pos_of[i])
        if match is None:
            i += 1
            continue
        from_idx, to_idx, n, kind, apply = match
        spans.append({"kind": kind, "apply": apply, "from_idx": from_idx, "to_idx": to_idx, "n": n})
        # An applied span really does remove its tokens, so scanning resumes past
        # them. A restart? or filler-adjacent candidate changes nothing -- only
        # advance past the first occurrence, so a real stumble sitting just past
        # it (inside the same words a wide, unconfident candidate here spans)
        # still gets its own look, e.g. "I've lost a s- [UH] I've" (restart?,
        # not confident) must not swallow the immediate "I've I've" right after it.
        i = to_idx if apply else from_idx + n
    return spans


def _find_repeat_at(words, content_tokens, content_idx, p):
    n_content = len(content_tokens)
    for n in range(min(MAX_N, n_content - p), 0, -1):
        gram = content_tokens[p:p + n]
        if any(t == "" for t in gram):
            continue
        result = _try_n(words, content_tokens, content_idx, p, n, gram)
        if result is not None:
            return result
    return None


LIST_LOOKAHEAD = 8


def _is_rhetorical_list(content_tokens, gram, q, n):
    """The same short scaffold appearing a THIRD time shortly after the
    second occurrence is a deliberate anaphoric list ('if you have seen,
    if you have watched, if you have been watching'), not a single
    abandon-and-restart -- a real stumble is said twice, not three-plus.
    Forward only: a chain of restarts that keeps reusing the exact same
    n-gram ("just by putting [money] ... just by putting [stable points]")
    would trip a backward version of this same check on its own later
    links, since each link's OWN text doesn't vary the way a genuine list's
    trailing content does ("and just wait" / "and just earn"); the 2-vs-3+
    word distinction that actually separates those two cases is handled by
    requiring n>=3 to auto-apply a 1-2-words-apart match at all (below)."""
    window = content_tokens[q + n:q + n + LIST_LOOKAHEAD]
    return any(window[k:k + n] == gram for k in range(len(window) - n + 1))


def _try_n(words, content_tokens, content_idx, p, n, gram):
    """Search content-word gaps of 0 (immediate) up through MAX_GAP_WORDS,
    applying the rule for whichever bucket a candidate match falls into.
    A candidate that matches but fails its bucket's rule (an n==1 immediate
    "very very", or a 3-4-word-apart match with punctuation in between)
    is skipped, not treated as "no match at this n" -- a later, valid
    bucket may still fire (this is how "more more more" -- where the first
    pair has ~0s gap and reads as a plain stutter, not an immediate stumble
    -- still gets caught one word over, at 1-intervening)."""
    n_content = len(content_tokens)
    first_last = content_idx[p + n - 1]  # original index of the first occurrence's last word

    for gap_words in range(0, MAX_GAP_WORDS + 1):
        q = p + n + gap_words
        if q + n > n_content or content_tokens[q:q + n] != gram:
            continue
        if gap_words == 0 and n >= 2 and _is_rhetorical_list(content_tokens, gram, q, n):
            continue  # only immediate matches: a 1-2/3-4-apart match chaining into
                       # another match right after (see "you could have been | you
                       # could have made [immediate] you could have made") is a
                       # restart chain, not a list -- lists recite the same short
                       # scaffold with ~0 gap each time ("if you have X, if you have Y")
        second_first = content_idx[q]  # original index of the second occurrence's first word
        time_gap = words[second_first]["start"] - words[first_last]["end"]
        if time_gap > MAX_RESTART_GAP_S:
            continue

        # Punctuation anywhere from the START of the first occurrence through the
        # word right before the second one starts -- not just its last word --
        # rules out a coincidental match that happens to straddle a sentence
        # boundary ("December.  I opened a twenty-five" / "December.  I opened"
        # are two unrelated sentences that both start "December. I", not one
        # abandoned attempt; the boundary sits inside the matched n-gram itself).
        has_punct = any(ends_with_clause_punct(words[k]["word"]) for k in range(content_idx[p], second_first))

        if gap_words == 0:
            if n == 1:
                if normalize(words[content_idx[p]]["word"]) in INTENSIFIERS:
                    continue  # emphasis ("very very"), never a stumble -- keep looking elsewhere
                frag_between = any(is_fragment(words[k]["word"]) for k in range(first_last + 1, second_first))
                if not (time_gap >= MIN_SINGLE_WORD_GAP_S or time_gap <= 1e-6 or frag_between):
                    continue  # small-but-real gap: fluent doubling, not a stumble
            return content_idx[p], _restart_point(words, first_last, second_first), n, "repeat", True

        frag_between = any(is_fragment(words[k]["word"]) for k in range(first_last + 1, second_first))
        if any(is_number_word(words[k]["word"]) for k in range(first_last + 1, second_first)):
            continue  # a number in between is content being narrated, not a stumble remnant

        if n == 1:
            # A single common word recurring a few words apart ("the", "a", "so",
            # "because") is coincidental in fluent speech, not a stumble -- UNLESS
            # a false start sits between the two, which is what "you mo- you" is:
            # "you" and "you" are 1 word apart, but that word is "mo-", a fragment,
            # not a real intervening word.
            if gap_words > 2 or not frag_between:
                continue
            kind, apply = ("restart?", False) if has_punct else ("repeat", True)
            return content_idx[p], _restart_point(words, first_last, second_first), n, kind, apply

        if gap_words in (1, 2):
            # A 2-word scaffold 1-2 words apart ("and just [wait] and just [earn]",
            # "if [you] if you") is short enough that hitting it twice in fluent
            # speech is common; require a 3+ word phrase to auto-apply here, but
            # still flag a 2-word one for review.
            if n == 2 or has_punct:
                return content_idx[p], _restart_point(words, first_last, second_first), n, "restart?", False
            return content_idx[p], _restart_point(words, first_last, second_first), n, "repeat", True

        # gap_words in (3, 4): only a punctuation-free run is even flagged
        if has_punct:
            continue
        return content_idx[p], _restart_point(words, first_last, second_first), n, "restart?", False

    return None


def _restart_point(words, first_last, second_first):
    """Largest silence gap between the end of the abandoned occurrence and
    the start of the kept one wins; a boundary within RESTART_TIE_EPSILON of
    that max also counts, and among those the LATEST one wins. Real ASR
    timing jitters a few tens to a couple hundred ms between runs of the
    same audio -- a strict "largest gap wins" here can flip which boundary
    is picked by a difference that isn't meaningful, stranding a trailing
    word of the abandoned take outside any cut (measured: the same "you
    could have been | you could have made" moment produced a 0.0s/0.0s tie
    in one transcription and a 0.10s/0.0s near-tie in another; both must
    drop "been")."""
    gaps = {k: words[k + 1]["start"] - words[k]["end"] for k in range(first_last, second_first)}
    max_gap = max(gaps.values())
    best_k = max(k for k, g in gaps.items() if g >= max_gap - RESTART_TIE_EPSILON)
    return best_k + 1


# -------------------------------------------------------------------- merge

def merge_spans(spans):
    """Adjacent/overlapping spans (by token index, which is equivalent to
    overlap in time since to_idx is always the index of the first word that
    stays) merge into one -- but only within the same apply group, so an
    unapplied filler or restart? candidate never silently swallows an
    applied cut, or vice versa."""
    spans = sorted(spans, key=lambda s: (s["from_idx"], s["to_idx"]))
    merged = []
    for s in spans:
        if merged and s["apply"] == merged[-1]["apply"] and s["from_idx"] <= merged[-1]["to_idx"]:
            prev = merged[-1]
            prev["to_idx"] = max(prev["to_idx"], s["to_idx"])
            prev["kinds"].add(s["kind"])
            prev["n"] = max(prev["n"], s["n"])
        else:
            merged.append({**s, "kinds": {s["kind"]}})
    return merged


_KIND_PRIORITY = ["repeat", "restart?", "fragment", "filler"]


def _kind_label(kinds):
    if len(kinds) == 1:
        return next(iter(kinds))
    for k in _KIND_PRIORITY:
        if k in kinds:
            return k
    return "+".join(sorted(kinds))


def _text(words, lo_idx, hi_idx):
    return " ".join(w["word"] for w in words[lo_idx:hi_idx])


def _keep_text(words, from_idx, max_words=8):
    out = []
    for w in words[from_idx:from_idx + max_words]:
        out.append(w["word"])
        if w["word"].rstrip().endswith((".", "!", "?")):
            break
    return " ".join(out)


def build_spans(words):
    tokens = [normalize(w["word"]) for w in words]
    raw = find_fragment_spans(words) + find_repeat_spans(words, tokens) + find_filler_spans(words)
    merged = merge_spans(raw)

    out = []
    for s in merged:
        from_idx, to_idx = s["from_idx"], s["to_idx"]
        kind = _kind_label(s["kinds"])
        entry = {
            "from": words[from_idx]["start"],
            "to": words[to_idx]["start"] if to_idx < len(words) else words[-1]["end"],
            "kind": kind,
            "drop_text": _text(words, from_idx, to_idx),
            "keep_text": _keep_text(words, to_idx) if kind != "filler" else "",
            "n": s["n"],
            "apply": s["apply"],
        }
        out.append(entry)
    out.sort(key=lambda e: e["from"])
    return out


# ------------------------------------------------------------------ output

def fmt_ts(s):
    m, sec = divmod(s, 60)
    return f"{int(m):02d}:{sec:04.1f}"


def print_spans(spans):
    applied = [s for s in spans if s["apply"]]
    not_applied = [s for s in spans if not s["apply"]]

    print(f"{len(applied)} applied span(s):")
    for s in applied:
        print(f'  {fmt_ts(s["from"])}-{fmt_ts(s["to"])}  {s["kind"]}  "{s["drop_text"]}"  ->  keeps "{s["keep_text"]}"')

    print(f"\n{len(not_applied)} not-applied span(s) (filler / restart?):")
    for s in not_applied:
        suffix = f'  ->  keeps "{s["keep_text"]}"' if s["keep_text"] else ""
        print(f'  {fmt_ts(s["from"])}-{fmt_ts(s["to"])}  {s["kind"]}  "{s["drop_text"]}"{suffix}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verbatim", help="verbatim words JSON, CrisperWhisper shape: {\"words\":[{\"word\",\"start\",\"end\"}]}")
    ap.add_argument("--lang", default="en", help="ISO code; only en has spelled-out fillers")

    ap.add_argument("--offset", type=float, default=0.0, help="seconds added to every timestamp before scanning")
    ap.add_argument("-o", "--output", default=None, help="output JSON path (default: <input>.stumbles.json)")
    ap.add_argument("--print", dest="do_print", action="store_true", help="print a human-readable list")
    args = ap.parse_args()
    set_language(args.lang)

    words = load_words(args.verbatim, args.offset)
    spans = build_spans(words)

    out_path = args.output or str(Path(args.verbatim).with_suffix("")) + ".stumbles.json"
    Path(out_path).write_text(json.dumps(spans, indent=2, ensure_ascii=False))

    if args.do_print:
        print_spans(spans)
        print()
    n_applied = sum(1 for s in spans if s["apply"])
    n_other = len(spans) - n_applied
    print(f"wrote {out_path} ({n_applied} applied, {n_other} not applied)")


if __name__ == "__main__":
    main()
