"""TEST ONLY: exercise the original controller without any HTTP transport."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0, str(Path(__file__).parent))
from native_runtime_core import load_controller

class Stub:
    def __init__(self):
        self.ChatCompletion = self
        self.replies = iter(["```python\nprint(2 + 3)\n```", "<answer> 5 <" + chr(92) + "answer>"])
    def create(self, model, messages):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.replies)))])

p = argparse.ArgumentParser()
for option in ["request", "source", "output", "trace"]:
    p.add_argument("--"+option, type=Path, required=True)
a = p.parse_args()
task = json.loads(a.request.read_text())
answer, messages = load_controller(a.source.read_text(), Stub())(task["question"], task["patient_note"], "offline-stub")
assert answer == "5"
a.output.write_text(answer)
a.trace.parent.mkdir(parents=True, exist_ok=True)
a.trace.write_text(json.dumps({"test_only": True, "answer": answer, "messages": messages}))
