"""Harbor bridge for the original, pinned MedCalc chat/code controller."""
import json
from pathlib import Path
import tempfile
from .adapter import upstream_prompt
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

    def version(self):
        return REVISION + "+bridge-0.1"

    async def setup(self, environment):
        self.sources = load_source(Path.home()/".cache"/"harbor-medcalc")
        result = await environment.exec("mkdir -p /opt/native")
        if result.return_code:
            raise RuntimeError("Could not prepare native controller")
        await environment.upload_file(Path(__file__).with_name("native_runtime.py"), "/opt/native/runtime.py")
        await environment.upload_file(self.sources["evaluation/generate_code_prompt.py"], "/opt/native/controller.py")

    async def run(self, instruction, environment, context):
        if not self.model_name:
            raise ValueError("An exact team-approved model ID is required")
        key, base = self._get_env("OPENAI_API_KEY"), self._get_env("OPENAI_BASE_URL")
        if not key or not base:
            raise ValueError("OPENAI_API_KEY and OPENAI_BASE_URL are required")
        request = request_from_instruction(instruction, self.sources["evaluation/generate_code_prompt.py"].read_text())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"request.json"
            path.write_text(json.dumps(request))
            await environment.upload_file(path, "/opt/native/request.json")
        result = await environment.exec(
            "python -I /opt/native/runtime.py --request /opt/native/request.json --source /opt/native/controller.py "
            "--output /workspace/answer.txt --trace /logs/agent/native-trace.json",
            cwd="/workspace", timeout_sec=1200,
            env={"OPENAI_API_KEY": key, "OPENAI_BASE_URL": base,
                 "MODEL_NAME": self.model_name, "MEDCALC_SANDBOX": "1"})
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir/"native-stdout.txt").write_text(result.stdout or "")
        (self.logs_dir/"native-stderr.txt").write_text(result.stderr or "")
        if result.return_code:
            raise RuntimeError("Native controller failed; inspect native-stderr.txt")
