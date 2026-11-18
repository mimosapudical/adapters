import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from medcalc_bench_verified.adapter import MedCalcBenchVerifiedAdapter, upstream_prompt
from medcalc_bench_verified.source import load_source
from medcalc_bench_verified.grading import load_scorer, score_answer, numeric_eval


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = load_source(Path.home()/".cache"/"harbor-medcalc")
        cls.rows = list(csv.DictReader(io.StringIO(cls.sources["datasets/test_data.csv"].read_text())))
        src = cls.sources["evaluation/evaluate.py"].read_text()
        cls.safe, cls.original = staticmethod(load_scorer(src)), staticmethod(load_scorer(src, restricted=False))

    def test_all_gold_and_wrong_answers(self):
        for row in self.rows:
            with self.subTest(row=row["Row Number"]):
                self.assertEqual(score_answer(row["Ground Truth Answer"], row, self.safe), 1)
                self.assertEqual(score_answer("not an answer", row, self.safe), 0)
                self.assertEqual(score_answer(row["Ground Truth Answer"], row, self.safe),
                                 score_answer(row["Ground Truth Answer"], row, self.original))

    def test_numeric_boundaries_and_original_rounding(self):
        count = 0
        for row in self.rows:
            if row["Output Type"] == "decimal":
                for answer in [row["Lower Limit"], row["Upper Limit"],
                               str(float(row["Lower Limit"])-1), str(float(row["Upper Limit"])+1)]:
                    self.assertEqual(score_answer(answer, row, self.safe), score_answer(answer, row, self.original))
                    count += 1
        row = next(r for r in self.rows if r["Calculator ID"] == "4")
        for answer in ["2.5", "3.5", "7/2", "-2.5"]:
            self.assertEqual(score_answer(answer, row, self.safe), score_answer(answer, row, self.original))
        self.assertEqual(count, 2720)

    def test_no_code_execution(self):
        for text in ["__import__('os').system('false')", "float('nan')", "(1).__class__", "True", "9**9999999"]:
            with self.subTest(text=text), self.assertRaises((ValueError, SyntaxError)):
                numeric_eval(text)

    def test_full_generation_and_schema(self):
        from harbor.models.task.config import TaskConfig
        with tempfile.TemporaryDirectory() as folder:
            paths = MedCalcBenchVerifiedAdapter(Path(folder)).run()
            self.assertEqual(len(paths), 1100)
            names = set()
            for path in paths:
                config = TaskConfig.model_validate_toml((path/"task.toml").read_text())
                names.add(config.task.name)
                self.assertEqual(config.verifier.environment_mode.value, "separate")
                self.assertEqual(list((path/"environment").iterdir()), [path/"environment/Dockerfile"])
                self.assertNotIn("Ground Truth", (path/"instruction.md").read_text())
                self.assertNotIn("github.com", (path/"instruction.md").read_text())
                self.assertTrue((path/"solution/answer.txt").exists())
                self.assertTrue((path/"tests/gold.json").exists())
            self.assertEqual(len(names), 1100)

    def test_selection_and_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            args = dict(output_dir=folder, limit=1)
            paths = MedCalcBenchVerifiedAdapter(**args).run()
            with self.assertRaises(FileExistsError):
                MedCalcBenchVerifiedAdapter(**args).run()
            self.assertEqual(paths, MedCalcBenchVerifiedAdapter(**args, overwrite=True).run())
            with self.assertRaises(ValueError):
                MedCalcBenchVerifiedAdapter(folder, task_ids=["../bad"]).run()

    def test_prompt_and_date_semantics(self):
        text = self.sources["evaluation/generate_code_prompt.py"].read_text()
        prompt = upstream_prompt(text, self.rows[0])
        self.assertIn(self.rows[0]["Patient Note"], prompt)
        self.assertIn(self.rows[0]["Question"], prompt)
        self.assertIn("Do not perform any computations yourself", prompt)
        row = next(r for r in self.rows if r["Output Type"] == "date")
        for answer in [row["Ground Truth Answer"], "1/1/1900", "2026-11-18"]:
            self.assertEqual(score_answer(answer, row, self.safe), score_answer(answer, row, self.original))


if __name__ == "__main__":
    unittest.main()
