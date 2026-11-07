#!/usr/bin/env python3
"""Regression tests for the immediate-repeat rule in find_stumbles.py: a phrase that ends one sentence and
opens the next is script text, not a stumble. Run from scripts/align/: python3 -m unittest tests.test_stumble_restart_rule
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import find_stumbles  # noqa: E402
from find_stumbles import build_spans  # noqa: E402


def make(text, gaps=None):
    """Words at 0.3 s each; gaps maps a word index to the silence (s) before it."""
    gaps, words, t = gaps or {}, [], 0.0
    for i, w in enumerate(text.split()):
        t += gaps.get(i, 0.05)
        words.append({"word": w, "start": round(t, 3), "end": round(t + 0.3, 3)})
        t += 0.3
    return words


def applied(words):
    return [s for s in build_spans(words) if s["apply"]]


class TestSentenceBoundaryIsNotARestart(unittest.TestCase):
    def test_door_tail_then_door_opens_is_kept(self):
        words = make("some markets have a bouncer at the door. The door opens at about two million dollars.",
                     gaps={8: 0.4})
        self.assertEqual(applied(words), [])

    def test_door_kept_with_a_long_pause_too(self):
        words = make("a bouncer at the door. The door opens at two million.", gaps={5: 0.9})
        self.assertEqual(applied(words), [])

    def test_single_word_tail_then_new_sentence(self):
        self.assertEqual(applied(make("I like that. That is great.", gaps={3: 0.3})), [])

    def test_question_and_exclamation_boundaries(self):
        self.assertEqual(applied(make("what is the market? The market is open.", gaps={4: 0.3})), [])
        self.assertEqual(applied(make("watch the door! The door opens.", gaps={3: 0.3})), [])


class TestRealRestartsStillCaught(unittest.TestCase):
    def test_the_the_door(self):
        spans = applied(make("a bouncer at the the door opens", gaps={4: 0.0}))
        self.assertEqual(len(spans), 1, spans)
        self.assertEqual(spans[0]["drop_text"], "the")

    def test_we_went_to_we_went_to_the_store(self):
        spans = applied(make("so we went to, we went to the store", gaps={3: 0.25}))
        self.assertEqual(len(spans), 1, spans)
        self.assertEqual(spans[0]["drop_text"], "we went to,")

    def test_whole_sentence_retake_after_a_sentence_end(self):
        spans = applied(make("thank you very much. So I'll see you. So I'll see you on Acmex.", gaps={7: 0.2}))
        self.assertEqual(len(spans), 1, spans)
        self.assertEqual(spans[0]["drop_text"], "So I'll see you.")

    def test_retake_of_the_opening_sentence(self):
        spans = applied(make("Since the U.S. Since the U.S. just changed", gaps={3: 0.4}))
        self.assertEqual(len(spans), 1, spans)

    def test_restart_written_with_a_full_stop_but_no_capital(self):
        spans = applied(make("the same competition, but at your size. but at your size so check it out", gaps={9: 0.05}))
        self.assertEqual(len(spans), 1, spans)

    def test_false_start_with_comma_mid_sentence(self):
        spans = applied(make("it opens at, it opens at two million", gaps={3: 0.3}))
        self.assertEqual(len(spans), 1, spans)


class TestScriptAsAHint(unittest.TestCase):
    """--script: a repeat the script also says at that point is intended speech and is kept; a repeat that is
    not in the script is judged by the normal rules; the script never forces a cut."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: find_stumbles.set_scripts([]))

    def script(self, text, name="SCRIPTS.md"):
        path = self.tmp / name
        path.write_text(text)
        return path

    def test_door_with_a_script_is_kept(self):
        find_stumbles.set_scripts([self.script("Some markets have a bouncer at the door. The door opens at $2 million.")])
        words = make("some markets have a bouncer at the door. The door opens at about two million dollars.", gaps={8: 0.4})
        self.assertEqual(applied(words), [])

    def test_script_keeps_a_repeat_the_sentence_rule_would_cut(self):
        # a deliberate echo with no sentence end: "very important, important" style, written in the script
        text = "we sell the the the rule of three, the the the rule"
        words = make("we sell the the the rule of three", gaps={1: 0.0, 2: 0.0, 3: 0.0})
        self.assertGreaterEqual(len(applied(words)), 1)  # without a script it is cut as a stutter
        find_stumbles.set_scripts([self.script("Intro. We sell the the the rule of three. Next.")])
        words = make("we sell the the the rule of three", gaps={1: 0.0, 2: 0.0, 3: 0.0})
        self.assertEqual(applied(words), [])
        self.assertTrue(find_stumbles.SCRIPT_PROTECTED)

    def test_repeat_not_in_the_script_is_still_caught(self):
        find_stumbles.set_scripts([self.script("We went to the store. Then we came home.")])
        spans = applied(make("so we went to, we went to the store", gaps={3: 0.25}))
        self.assertEqual(len(spans), 1, spans)
        self.assertEqual(spans[0]["drop_text"], "we went to,")

    def test_script_is_local_a_phrase_elsewhere_in_it_does_not_protect(self):
        find_stumbles.set_scripts([self.script("Day one. It opens at, it opens at nine. Later we talk about the store and the door.")])
        spans = applied(make("so we went to the the door and then left", gaps={5: 0.0}))
        self.assertEqual(len(spans), 1, spans)

    def test_spoken_number_matches_written_number(self):
        find_stumbles.set_scripts([self.script("We pay $2 million, 2 million in total, every month.")])
        words = make("we pay two million two million in total every month", gaps={3: 0.0})
        self.assertEqual(applied(words), [])

    def test_script_hint_survives_spelling_noise(self):
        find_stumbles.set_scripts([self.script("Trade on Acmex Acmex today, every day.")])
        words = make("trade on Acmexx Acmexx today every day", gaps={4: 0.0})
        self.assertEqual(applied(words), [])

    def test_ad_libbed_stumble_far_from_the_script_text_is_cut(self):
        find_stumbles.set_scripts([self.script("We went to the store and bought milk.")])
        spans = applied(make("and honestly I think I think that was fine", gaps={4: 0.0, 5: 0.25}))
        self.assertEqual(len(spans), 1, spans)

    def test_coverage_tells_a_wrong_script_from_the_right_one(self):
        words = make("so we went to the store and bought some milk for dinner")
        find_stumbles.set_scripts([self.script("So we went to the store and bought some milk for dinner.", "a.md"),
                                   self.script("Completely different text about options and volatility surfaces.", "b.md")])
        cov = find_stumbles.script_coverage(words)
        self.assertGreater(cov[str(self.tmp / "a.md")], 0.9)
        self.assertLess(cov[str(self.tmp / "b.md")], 0.1)


if __name__ == "__main__":
    unittest.main()
