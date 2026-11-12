"""Offline CLI checks using the real research runner and board renderer."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import research_eval


class ResearchEvalCasesOptionTests(unittest.TestCase):
    def setUp(self):
        runs = research_eval.ROOT / ".runs" / "r33"
        runs.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=runs)
        self.addCleanup(temporary.cleanup)
        self.out = Path(temporary.name) / "output"
        out_patch = patch.object(research_eval, "OUT", self.out)
        out_patch.start()
        self.addCleanup(out_patch.stop)
        path_patch = patch.object(sys, "path", [str(research_eval.ROOT / "scripts"), *sys.path])
        path_patch.start()
        self.addCleanup(path_patch.stop)

    def check_run(self, arguments, source):
        with contextlib.redirect_stdout(io.StringIO()):
            research_eval.main([*arguments, "--sweep", ""])
        raw = source.read_bytes()
        dataset = json.loads(raw.decode("utf-8"))
        records = (self.out / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(records), 1)
        record = json.loads(records[0])
        self.assertEqual(record["cases_file"], source.name)
        self.assertEqual(record["cases_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(record["dataset"], dataset["version"])
        self.assertEqual(record["split"], "compare")
        self.assertEqual(set(record["configs"]), set(research_eval.CONFIGS))
        self.assertTrue({"at", "sha", "note", "sweep"} <= record.keys())
        expected = [case["id"] for case in dataset["cases"] if case["split"] == "compare"]
        for config in record["configs"].values():
            self.assertEqual([row["case"] for row in config["cases"]], expected)
            self.assertEqual(config["summary"]["n_cases"], len(expected))
        self.assertTrue((self.out / "board.html").is_file())

    def test_default_cases(self):
        self.check_run([], research_eval.CASES)

    def test_explicit_original_cases(self):
        self.check_run(["--cases", str(research_eval.CASES)], research_eval.CASES)

    def test_v2_relative_cases(self):
        relative = Path("evals/research/cases_v2.ko.json")
        self.check_run(["--cases", str(relative)], research_eval.ROOT / relative)

    def test_missing_cases_is_an_argument_error_before_output(self):
        missing = self.out.parent / "missing-cases.json"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            research_eval.main(["--cases", str(missing)])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("cannot read cases file", stderr.getvalue())
        self.assertIn(str(missing), stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
