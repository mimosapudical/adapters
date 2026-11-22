"""Harbor bridge for the original, pinned MedCalc chat/code controller."""
import asyncio
import json
from pathlib import Path
import tempfile
from .adapter import upstream_prompt
from .native_runtime import ChatAPI, run_controller
from .source import load_source, REVISION
from harbor.agents.base import BaseAgent

SUFFIX = "\nSave only your final answer value, without tags or units, to /workspace/answer.txt. Python is available.\n"


def request_from_instruction(instruction, source):
    if not instruction.endswith(SUFFIX):
        raise ValueError("Unexpected adapter instruction suffix")
    original = instruction[:-len(SUFFIX)]
    _, user = original.split("Patient Note:\n\n", 1)
    note, question = user.rsplit("\n\nQuestion:\n\n", 1)
    question = question.removesuffix("\n\n")
    row = {"Patient Note": note, "Question": question}
    if upstream_prompt(source, row) != original:
        raise ValueError("Instruction did not round-trip to the original prompt")
    return {"patient_note": note, "question": question}


class MedCalcNativeAgent(BaseAgent):
    @staticmethod
    def name():
        return "medcalc-native"

    def __init__(self, *args, code_image=None, cache_dir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.code_image = code_image
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache/harbor-medcalc"

    def version(self):
        return REVISION + "+bridge-0.2"

    async def setup(self, environment):
        path = load_source(self.cache_dir)["evaluation/generate_code_prompt.py"]
        self.controller_source = path.read_text()

    def _chat_api(self):
        key, base = self._get_env("OPENAI_API_KEY"), self._get_env("OPENAI_BASE_URL")
        if not key or not base:
            raise ValueError("OPENAI_API_KEY and OPENAI_BASE_URL are required")
        return ChatAPI(self.model_name, base, key)

    async def run(self, instruction, environment, context):
        if not self.model_name or not self.code_image:
            raise ValueError("An exact team-approved model and code image are required")
        request = request_from_instruction(instruction, self.controller_source)
        trace = await asyncio.to_thread(
            run_controller, self.controller_source, request, self.model_name,
            self._chat_api(), self.code_image,
        )
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "native-trace.json").write_text(json.dumps(trace, indent=2))
        with tempfile.TemporaryDirectory() as directory:
            answer = Path(directory) / "answer.txt"
            answer.write_text(trace["answer"])
            await environment.upload_file(answer, "/workspace/answer.txt")
