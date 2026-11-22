import copy
import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from medcalc_bench_verified.adapter import upstream_prompt
from medcalc_bench_verified.native_agent import request_from_instruction, SUFFIX, MedCalcNativeAgent
from medcalc_bench_verified.native_runtime import load_controller
from medcalc_bench_verified.parity import select_ids, validate_plan
from medcalc_bench_verified.source import load_source


class StubAPI:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.ChatCompletion = self

    def create(self, model, messages):
        self.calls.append(copy.deepcopy(messages))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.replies)))])


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = load_source(Path.home()/'.cache/harbor-medcalc')
        cls.controller_source = src['evaluation/generate_code_prompt.py'].read_text()
        cls.rows = list(csv.DictReader(io.StringIO(src['datasets/test_data.csv'].read_text())))

    def test_all_original_messages_round_trip(self):
        for row in self.rows:
            request = request_from_instruction(upstream_prompt(self.controller_source, row) + SUFFIX, self.controller_source)
            self.assertEqual(request, {'question': row['Question'], 'patient_note': row['Patient Note']})

    def test_real_controller_executes_code_then_returns_answer(self):
        api = StubAPI(['```python\nprint(2 + 3)\n```', '<answer> 5 <\\answer>'])
        from unittest.mock import Mock
        execute = Mock(return_value='5\n')
        controller = load_controller(self.controller_source, api, execute)
        answer, messages = controller('What is the value?', 'Example note', 'stub')
        execute.assert_called_once_with('print(2 + 3)\n')
        self.assertEqual(answer, '5')
        self.assertEqual(len(api.calls), 2)
        self.assertIn('5', api.calls[1][-1]['content'])
        self.assertEqual(api.calls[0][0]['role'], 'system')
        self.assertEqual(api.calls[0][1]['role'], 'user')
        self.assertIn('Example note', api.calls[0][1]['content'])

    def test_original_turn_limit_and_api_errors(self):
        api = StubAPI(['Please clarify'] * 20)
        controller = load_controller(self.controller_source, api, None)
        answer, _ = controller('Question', 'Note', 'stub')
        self.assertIsNone(answer)
        self.assertEqual(len(api.calls), 20)
        with self.assertRaises(StopIteration):
            load_controller(self.controller_source, StubAPI([]), None)('Question', 'Note', 'stub')

    def test_frozen_selection_balanced_independent_of_input_order(self):
        ids = select_ids(self.rows)
        self.assertEqual(ids, select_ids(list(reversed(self.rows))))
        self.assertEqual(len(ids), 110)
        from collections import Counter
        lookup = {r['Row Number']:r for r in self.rows}
        self.assertEqual(set(Counter(lookup[i]['Calculator ID'] for i in ids).values()), {2})
        with self.assertRaises(ValueError):
            validate_plan({'task_ids': ids})

    def test_reject_modified_prompt(self):
        instruction = upstream_prompt(self.controller_source, self.rows[0]) + SUFFIX
        with self.assertRaises(ValueError):
            request_from_instruction(instruction.replace('You are a helpful assistant', 'Ignore previous instructions'), self.controller_source)

class ReportingTests(unittest.TestCase):
    def test_sem_and_overlap(self):
        from medcalc_bench_verified.run_paired import comparison
        import math
        result = comparison([0.4,0.5,0.6],[0.45,0.5,0.55])
        self.assertAlmostEqual(result['original']['sample_sem'],0.1/math.sqrt(3))
        self.assertTrue(result['ranges_overlap'])
        self.assertFalse(comparison([0.1,0.2,0.3],[0.4,0.5,0.6])['ranges_overlap'])
        with self.assertRaises(ValueError):
            comparison([0.5],[0.5])

    def test_missing_trials_and_infrastructure_errors_are_not_scores(self):
        from medcalc_bench_verified.run_paired import collect_harbor
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                collect_harbor(Path(d), ['1'])
            record = {'trial_name':'stub','task_name':'case-1','exception_info':{'exception_type':'HTTPError'}}
            (Path(d)/'result.json').write_text(json.dumps(record))
            with self.assertRaises(RuntimeError):
                collect_harbor(Path(d), ['1'])


class StagedParityTests(unittest.TestCase):
    def test_resume_reuses_paired_pilot_and_reports_only_complete_experiment(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from medcalc_bench_verified.run_paired import run_experiment

        def fake_stage(stage, index, ids, plan, rows, sources, cache_dir):
            original = stage / "original"
            harbor = stage / "harbor"
            original.mkdir(parents=True)
            harbor.mkdir()
            (original / "result.json").write_text(json.dumps({
                "cases": [{"row_id": row, "reward": 1} for row in ids],
                "score": 0,
            }))
            for row in ids:
                trial = harbor / row
                trial.mkdir()
                (trial / "result.json").write_text(json.dumps({
                    "trial_name": row, "task_name": f"case-{row}",
                    "verifier_environment_mode": "separate",
                    "verifier_result": {"rewards": {"reward": 1}},
                }))

        plan = {"pilot_ids": ["1"], "task_ids": ["1", "2"], "model": "fixture"}
        module = "medcalc_bench_verified.run_paired"
        with TemporaryDirectory() as directory, patch(
            f"{module}.read_rows", return_value=([], {}),
        ), patch(f"{module}.run_stage", side_effect=fake_stage) as run_stage:
            output = Path(directory) / "experiment"
            cache_dir = Path(directory)
            run_experiment(output, plan, cache_dir, through=0, resume=False)
            self.assertFalse((output / "comparison.json").exists())
            with self.assertRaisesRegex(ValueError, "approved plan"):
                run_experiment(output, {**plan, "model": "different"}, cache_dir, through=1, resume=True)
            run_experiment(output, plan, cache_dir, through=1, resume=True)
            self.assertFalse((output / "comparison.json").exists())
            run_experiment(output, plan, cache_dir, through=3, resume=True)
            self.assertEqual([call.args[0].name for call in run_stage.call_args_list],
                             ["pilot", "run-1", "run-2", "run-3"])
            report = json.loads((output / "comparison.json").read_text())
            self.assertEqual(report["original"]["runs"], [1, 1, 1])
            self.assertEqual(report["harbor"]["runs"], [1, 1, 1])
            self.assertTrue(report["ranges_overlap"])

            incomplete = output / "run-2/harbor-summary.json"
            incomplete.unlink()
            with self.assertRaisesRegex(RuntimeError, "Unfinished stage"):
                run_experiment(output, plan, cache_dir, through=3, resume=True)
            self.assertEqual(run_stage.call_count, 4)


class IsolatedRuntimeTests(unittest.TestCase):
    def test_controller_keeps_api_key_outside_code_worker(self):
        from unittest.mock import patch
        import os
        import subprocess
        from medcalc_bench_verified.native_runtime import run_controller

        sources = load_source(Path.home() / ".cache/harbor-medcalc")
        source = sources["evaluation/generate_code_prompt.py"].read_text()
        api = StubAPI(["```python\nprint(2 + 3)\n```", "<answer> 5 <\\answer>"])
        api.records = []
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch(
            "medcalc_bench_verified.native_runtime.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="5\n", stderr=""),
        ) as launch:
            trace = run_controller(
                source, {"question": "Question", "patient_note": "Note"}, "stub", api,
                "python@sha256:" + "a" * 64,
            )

        self.assertEqual(trace["answer"], "5")
        self.assertEqual(len(api.calls), 2)
        self.assertIn("5", api.calls[1][-1]["content"])
        launch.assert_called_once()
        command = launch.call_args.args[0]
        self.assertIn("--network=none", command)
        self.assertIn("--read-only", command)
        self.assertFalse(any(arg.startswith(("--mount", "--volume", "--env")) for arg in command))
        self.assertNotIn("OPENAI_API_KEY", launch.call_args.kwargs["env"])
        self.assertEqual(launch.call_args.kwargs["input"].strip(), "print(2 + 3)")


if __name__ == "__main__":
    unittest.main()
