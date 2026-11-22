"""Offline transport for the Harbor Docker integration test."""
from types import SimpleNamespace

from medcalc_bench_verified.native_agent import MedCalcNativeAgent


class StubAPI:
    def __init__(self):
        self.ChatCompletion = self
        self.records = []
        self.replies = iter(['```python\nimport os\nassert "OPENAI_API_KEY" not in os.environ\nprint(2 + 3)\n```', "<answer> 5 <\\answer>"])

    def create(self, model, messages):
        content = next(self.replies)
        self.records.append(content)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class StubNativeAgent(MedCalcNativeAgent):
    @staticmethod
    def name():
        return "medcalc-offline-stub"

    def _chat_api(self):
        return StubAPI()
