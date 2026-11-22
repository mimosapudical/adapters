"""Run one matched native task against a local Ollama model, without credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from medcalc_bench_verified.adapter import MedCalcBenchVerifiedAdapter
from medcalc_bench_verified.grading import load_scorer, score_answer
from medcalc_bench_verified.native_agent import MedCalcNativeAgent
from medcalc_bench_verified.native_runtime import ChatAPI, run_controller
from medcalc_bench_verified.parity import read_rows
from medcalc_bench_verified.run_paired import collect_harbor


class LocalChatAPI(ChatAPI):
    def __init__(self, model):
        self.model = model
        self.base_url = "http://127.0.0.1:11434/v1"
        self.key = None
        self.records = []
        self.ChatCompletion = self


class LocalModelAgent(MedCalcNativeAgent):
    @staticmethod
    def name():
        return "medcalc-native-local"

    def _chat_api(self):
        return LocalChatAPI(self.model_name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    adapter_root = Path(__file__).resolve().parents[1]
    plan = json.loads((adapter_root / "validation/parity-plan.proposed-r15.json").read_text())
    row_id = plan["pilot_ids"][0]
    image = plan["image"]
    cache = Path.home() / ".cache/harbor-medcalc"
    rows, sources = read_rows(cache)
    row = next(row for row in rows if row["Row Number"] == row_id)
    question = {"question": row["Question"], "patient_note": row["Patient Note"]}
    source = sources["evaluation/generate_code_prompt.py"].read_text()
    scorer = load_scorer(sources["evaluation/evaluate.py"].read_text())

    original = run_controller(source, question, args.model, LocalChatAPI(args.model), image)
    (output / "original-trace.json").write_text(json.dumps(original, indent=2))
    original_score = score_answer(original["answer"].strip(), row, scorer) if len(original["answer"].encode()) <= 128 else 0

    tasks = output / "tasks"
    MedCalcBenchVerifiedAdapter(tasks, task_ids=[row_id], cache_dir=cache).run()
    subprocess.run([
        sys.executable, "-m", "harbor.cli.main", "run", "-p", str(tasks),
        "-a", "keyless_pilot:LocalModelAgent", "-m", args.model, "-n", "1",
        "--max-retries", "0", "--agent-kwarg", f"code_image={image}",
        "--agent-kwarg", f"cache_dir={cache}", "--jobs-dir", str(output / "jobs"),
        "--job-name", "local-model",
    ], check=True)
    harbor = collect_harbor(output / "jobs", [row_id])
    harbor_trace_path, = (output / "jobs").rglob("native-trace.json")
    harbor_trace = json.loads(harbor_trace_path.read_text())
    for trace in (original, harbor_trace):
        if not trace["calls"] or any(call["model"] != args.model for call in trace["calls"]):
            raise RuntimeError("The reported model does not match the pinned local model name.")
    if original["calls"][0]["request"] != harbor_trace["calls"][0]["request"]:
        raise RuntimeError("Initial requests differ across harnesses.")
    summary = {
        "classification": "exploratory local model pilot; not an approved parity result",
        "case_id": row_id,
        "model": args.model,
        "original_score": original_score,
        "harbor_score": harbor["score"],
        "original_calls": len(original["calls"]),
        "harbor_calls": len(harbor_trace["calls"]),
        "matched_first_request": True,
        "original_stop_reason": original.get("stop_reason"),
        "harbor_stop_reason": harbor_trace.get("stop_reason"),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
