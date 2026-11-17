from __future__ import annotations

import unittest

from memory_book.text import excerpt


class ExcerptBoundaryTests(unittest.TestCase):
    def assert_original_window(self, text, query, budget, evidence):
        value, spans = excerpt(text, query, budget)
        self.assertIn(evidence, value)
        self.assertLessEqual(len(value), budget)
        self.assertEqual(len(spans), 1)
        start, end = spans[0]
        self.assertEqual(value, ("…" if start else "") + text[start:end]
                         + ("…" if end < len(text) else ""))

    def test_fitting_utterance_keeps_the_subject_before_a_late_keyword(self):
        evidence = "ASSISTANT: The revised sapphire chamber operates with a pressure of 82 pascals."
        text = "Unrelated calibration notes. " * 8 + "\n" + evidence + "\n" + "Other records. " * 12
        self.assert_original_window(text, "pressure", 100, evidence)

    def test_fitting_line_preserves_a_qualification_in_the_next_sentence(self):
        evidence = "USER: Mina: Coconut flour is optional. Use 45 grams only for the dense version."
        text = "Earlier kitchen notes. " * 12 + "\n" + evidence + "\n" + "More notes. " * 20
        self.assert_original_window(text, "coconut flour", 95, evidence)

    def test_long_line_uses_an_intact_sentence_when_it_fits(self):
        evidence = "The revised sapphire chamber operates with a pressure of 82 pascals."
        text = "Unrelated calibration notes. " * 8 + evidence + " " + "Other records. " * 12
        self.assert_original_window(text, "pressure", 95, evidence)

    def test_unicode_boundaries_still_use_original_source_coordinates(self):
        evidence = "ASSISTANT: 为保证旧记录可追溯，café Straße 的缓存现在保留23分钟。"
        text = "历史记录。" * 40 + "\n" + evidence + "\n" + "其他信息。" * 40
        self.assert_original_window(text, "cafe strasse 缓存", 62, evidence)

    def test_repeated_keyword_fragment_does_not_displace_complete_fact(self):
        evidence = "USER: The current oak configuration uses a key of amber."
        text = "oak " * 30 + "\n" + evidence + "\n" + "Other notes. " * 20
        self.assert_original_window(text, "oak", 80, evidence)

    def test_distinct_query_terms_outrank_repetition_in_another_sentence(self):
        evidence = "The oak instrument uses an amber key for calibration."
        text = "oak " * 30 + "\n" + evidence + "\n" + "Other notes. " * 20
        self.assert_original_window(text, "oak amber calibration", 80, evidence)


if __name__ == "__main__":
    unittest.main()
