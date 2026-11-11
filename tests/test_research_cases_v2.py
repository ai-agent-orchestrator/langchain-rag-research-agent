"""Offline contract checks for the opt-in synthetic research corpus."""
from collections import Counter
import json
from pathlib import Path
import re
import unittest


CASES = Path(__file__).resolve().parents[1] / "evals/research/cases_v2.ko.json"
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
TOPICS = {"econ", "tech", "social", "env", "edu"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class ResearchCasesV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CASES.read_text(encoding="utf-8")
        cls.dataset = json.loads(cls.raw, object_pairs_hook=unique_object)
        cls.cases = cls.dataset["cases"]

    def test_dataset_schema_and_synthetic_notice(self):
        self.assertEqual(set(self.dataset), {"version", "note", "cases"})
        self.assertEqual(self.dataset["version"], "research-eval/2")
        self.assertIn("합성", self.dataset["note"])
        self.assertIn("실제 통계 아님", self.dataset["note"])
        self.assertIsInstance(self.cases, list)
        self.assertEqual(len(self.cases), 30)

    def test_unique_case_and_document_ids(self):
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        doc_ids = [doc_id for case in self.cases for doc_id in case["docs"]]
        self.assertEqual(len(doc_ids), len(set(doc_ids)))
        for identifier in ids + doc_ids:
            self.assertRegex(identifier, r"^[a-z][a-z0-9-]*$")

    def test_splits_and_topic_diversity(self):
        self.assertEqual(Counter(c["split"] for c in self.cases),
                         {"compare": 20, "confirm": 10})
        self.assertEqual({c["id"].split("-")[0] for c in self.cases}, TOPICS)
        for topic in TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(Counter(c["split"] for c in self.cases
                                         if c["id"].startswith(topic + "-")),
                                 {"compare": 4, "confirm": 2})
        compare = {c["question"] for c in self.cases if c["split"] == "compare"}
        confirm = {c["question"] for c in self.cases if c["split"] == "confirm"}
        self.assertTrue(compare.isdisjoint(confirm))

    def test_required_case_and_gold_fields(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(set(case), {"id", "split", "question", "checklist", "docs", "gold"})
                self.assertIsInstance(case["question"], str)
                self.assertTrue(case["question"].strip())
                self.assertIsInstance(case["checklist"], list)
                self.assertEqual(set(case["checklist"]), set(case["gold"]["metrics"]))
                self.assertIsInstance(case["docs"], dict)
                self.assertTrue(case["docs"])
                self.assertTrue(all(isinstance(t, str) and t.strip() for t in case["docs"].values()))
                gold = case["gold"]
                self.assertEqual(set(gold), {"metrics", "causal", "constraints", "con"})
                self.assertIsInstance(gold["metrics"], dict)
                self.assertIn(len(gold["metrics"]), (2, 3))
                for key in ("causal", "constraints", "con"):
                    self.assertIsInstance(gold[key], list)
                self.assertIn(len(gold["causal"]), (1, 2))
                self.assertEqual(len(gold["constraints"]), 1)
                self.assertIn(len(gold["con"]), (0, 1))

    def test_gold_numbers_occur_with_their_metric_in_evidence(self):
        for case in self.cases:
            evidence = [text for doc_id, text in case["docs"].items() if "-bg" not in doc_id]
            for metric, value in case["gold"]["metrics"].items():
                with self.subTest(case=case["id"], metric=metric):
                    self.assertIsInstance(metric, str)
                    self.assertTrue(metric.strip())
                    self.assertIsInstance(value, str)
                    self.assertRegex(value, r"^\d+(?:\.\d+)?$")
                    # Token equality prevents 8 matching 18, or 2 matching 2.4.
                    self.assertTrue(any(metric in text and value in
                                        {n.replace(",", "") for n in NUMBER.findall(text)}
                                        for text in evidence))

    def test_gold_causal_groups_are_grounded_in_one_document(self):
        for case in self.cases:
            evidence = [text for doc_id, text in case["docs"].items() if "-bg" not in doc_id]
            for group in case["gold"]["causal"]:
                with self.subTest(case=case["id"], group=group):
                    self.assertIsInstance(group, list)
                    self.assertTrue(group)
                    self.assertTrue(all(isinstance(p, str) and p.strip() for p in group))
                    self.assertTrue(any(all(p in text for p in group) for text in evidence))

    def test_constraint_and_counter_phrases_are_grounded(self):
        for case in self.cases:
            for field, marker in (("constraints", "[합성 조건]"), ("con", "[합성 반대 근거]")):
                evidence = [t for t in case["docs"].values() if t.startswith(marker)]
                self.assertEqual(len(evidence), len(case["gold"][field]))
                for phrase in case["gold"][field]:
                    with self.subTest(case=case["id"], field=field):
                        self.assertIsInstance(phrase, str)
                        self.assertTrue(phrase.strip())
                        self.assertTrue(any(phrase in text for text in evidence))

    def test_background_count_and_separation_from_gold(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                background = [t for doc_id, t in case["docs"].items() if "-bg" in doc_id]
                self.assertIn(len(background), range(3, 7))
                self.assertEqual(len(background), len(set(background)))
                phrases = [p for group in case["gold"]["causal"] for p in group]
                phrases += case["gold"]["constraints"] + case["gold"]["con"]
                for text in background:
                    self.assertTrue(text.startswith("[합성 배경 잡음]"))
                    self.assertFalse(NUMBER.search(text))
                    self.assertTrue(all(p not in text for p in phrases))

    def test_synthetic_marking_and_no_personal_data_shapes(self):
        for case in self.cases:
            self.assertTrue(case["question"].startswith("[합성]"))
            self.assertTrue(all(t.startswith("[합성 ") for t in case["docs"].values()))
        # No contact/payment fixtures are needed: reject these shapes entirely.
        for pattern in (r"\d{10,}", r"\b0\d{1,3}[- .]\d{3,4}[- .]\d{4}\b",
                        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                        r"\b\d{6}[- ]\d{7}\b", r"\b(?:\d{4}[- ]){3}\d{4}\b"):
            self.assertIsNone(re.search(pattern, self.raw), pattern)


if __name__ == "__main__":
    unittest.main()
