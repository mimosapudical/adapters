import contextlib
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
        controller = load_controller(self.controller_source, api)
        with contextlib.redirect_stdout(io.StringIO()):
            answer, messages = controller('What is the value?', 'Example note', 'stub')
        self.assertEqual(answer, '5')
        self.assertEqual(len(api.calls), 2)
        self.assertIn('5', api.calls[1][-1]['content'])
        self.assertEqual(api.calls[0][0]['role'], 'system')
        self.assertEqual(api.calls[0][1]['role'], 'user')
        self.assertIn('Example note', api.calls[0][1]['content'])

    def test_original_turn_limit_and_api_errors(self):
        api = StubAPI(['Please clarify'] * 20)
        with contextlib.redirect_stdout(io.StringIO()):
            answer, _ = load_controller(self.controller_source, api)('Question', 'Note', 'stub')
        self.assertIsNone(answer)
        self.assertEqual(len(api.calls), 20)
        with self.assertRaises(StopIteration):
            load_controller(self.controller_source, StubAPI([]))('Question', 'Note', 'stub')

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


class IsolatedRuntimeTests(unittest.TestCase):
    def test_stub_entrypoint_with_isolated_python(self):
        import shutil, subprocess, sys, tempfile
        sources=load_source(Path.home()/'.cache/harbor-medcalc')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            import medcalc_bench_verified.native_runtime as runtime
            shutil.copy(runtime.__file__,root/'native_runtime_core.py')
            shutil.copy(Path(__file__).with_name('native_stub_runtime.py'),root/'stub.py')
            (root/'request.json').write_text(json.dumps({'question':'Question','patient_note':'Note'}))
            subprocess.run([sys.executable,'-I',str(root/'stub.py'),'--request',str(root/'request.json'),
                            '--source',str(sources['evaluation/generate_code_prompt.py']),
                            '--output',str(root/'answer.txt'),'--trace',str(root/'trace.json')],check=True,capture_output=True)
            self.assertEqual((root/'answer.txt').read_text(),'5')


if __name__ == '__main__':
    unittest.main()
