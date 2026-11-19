"""Freeze balanced task IDs and independently run the original controller in Docker.

This module has no API side effects without the explicit run-original command.
An approved plan is required; blank approvals/model configuration fail closed.
"""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from .source import load_source, REVISION
from .grading import load_scorer, score_answer, numeric_eval


def read_rows(cache):
    src = load_source(Path(cache))
    return list(csv.DictReader(io.StringIO(src["datasets/test_data.csv"].read_text()))), src


def select_ids(rows, per_calculator=2):
    groups = {}
    for row in rows:
        groups.setdefault(row["Calculator ID"], []).append(row)
    selected = []
    for group in groups.values():
        if len(group) < per_calculator:
            raise ValueError("Too few cases in stratum")
        ranked = sorted(group, key=lambda r: hashlib.sha256(("medcalc-parity-v1:"+r["Row Number"]).encode()).hexdigest())
        selected.extend(r["Row Number"] for r in ranked[:per_calculator])
    return sorted(selected, key=int)


def validate_plan(plan):
    for name in ["approved_by", "approval_reference", "model", "base_url", "image"]:
        if not isinstance(plan.get(name), str) or not plan[name].strip() or "<" in plan[name]:
            raise ValueError(f"Missing approved plan field: {name}")
    if plan.get("source_revision") != REVISION or plan.get("runs_per_side") != 3:
        raise ValueError("Wrong source revision or run count")
    if "@sha256:" not in plan["image"]:
        raise ValueError("Pin the exact Docker image digest before model execution")
    pilot = plan.get("pilot_ids", [])
    if len(pilot) != 5 or len(set(pilot)) != 5 or not set(pilot) <= set(plan.get("task_ids", [])):
        raise ValueError("Expected five distinct pilot IDs inside the full parity set")
    ids = plan.get("task_ids", [])
    if len(ids) != 110 or len(set(ids)) != 110:
        raise ValueError("Expected 110 unique frozen parity cases")


def run_original(plan, rows, sources, output, run_index, pilot=False):
    validate_plan(plan)
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required")
    output.mkdir(parents=True, exist_ok=False)
    ids = plan["pilot_ids"] if pilot else plan["task_ids"]
    lookup = {r["Row Number"]: r for r in rows}
    if set(ids)-lookup.keys():
        raise ValueError("Plan references unknown upstream rows")
    scorer = load_scorer(sources["evaluation/evaluate.py"].read_text(), restricted=False)
    records = []
    for row_id in ids:
        row = lookup[row_id]
        case = output/f"case-{row_id}"
        case.mkdir()
        workspace = case/"workspace"
        workspace.mkdir()
        with tempfile.TemporaryDirectory() as d:
            request = Path(d)/"request.json"
            request.write_text(json.dumps({"question": row["Question"], "patient_note": row["Patient Note"]}))
            env = {**os.environ, "MODEL_NAME": plan["model"], "OPENAI_BASE_URL": plan["base_url"], "MEDCALC_SANDBOX": "1"}
            command = ["docker", "run", "--rm", "--cpus", "1", "--memory", "1024m", "--workdir", "/workspace",
                       "--env", "OPENAI_API_KEY", "--env", "OPENAI_BASE_URL", "--env", "MODEL_NAME", "--env", "MEDCALC_SANDBOX",
                       "--mount", f"type=bind,src={request},dst=/opt/native/request.json,readonly",
                       "--mount", f"type=bind,src={Path(__file__).with_name('native_runtime.py')},dst=/opt/native/runtime.py,readonly",
                       "--mount", f"type=bind,src={sources['evaluation/generate_code_prompt.py']},dst=/opt/native/controller.py,readonly",
                       "--mount", f"type=bind,src={workspace.resolve()},dst=/workspace", plan["image"],
                       "timeout", "1200", "python", "-I", "/opt/native/runtime.py", "--request", "/opt/native/request.json", "--source", "/opt/native/controller.py",
                       "--output", "/workspace/answer.txt", "--trace", "/workspace/native-trace.json"]
            with (case/"stdout.txt").open("w") as out, (case/"stderr.txt").open("w") as err:
                result = subprocess.run(command, env=env, stdout=out, stderr=err, timeout=1250)
            if result.returncode:
                raise RuntimeError(f"Original-side environment/API failure: case {row_id}; not a model score")
        answer = (workspace/"answer.txt").read_text().strip()
        reward = 0
        if len(answer.encode()) <= 128:
            try:
                # Preserve the upstream scorer while preventing its eval from
                # executing model-supplied code on the orchestration host.
                if int(row["Calculator ID"]) not in (13, 68, 69):
                    numeric_eval(answer)
                reward = score_answer(answer, row, scorer)
            except (ValueError, SyntaxError, TypeError, OverflowError, ZeroDivisionError):
                reward = 0
        records.append({"row_id": row_id, "reward": reward})
        (case/"score.json").write_text(json.dumps(records[-1]))
    (output/"result.json").write_text(json.dumps({"side":"original", "run_index":run_index, "cases":records,
       "score":sum(r["reward"] for r in records)/len(records), "source_revision":REVISION}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run-original"])
    parser.add_argument("--cache-dir", type=Path, default=Path.home()/".cache"/"harbor-medcalc")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--run-index", type=int, choices=[1,2,3], default=1)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    rows, sources = read_rows(args.cache_dir)
    if args.command == "prepare":
        ids = select_ids(rows)
        lookup = {r["Row Number"]:r for r in rows}
        # Five distinct calculator strata and mixed answer types where available.
        pilot = []
        for kind in ["decimal", "integer", "date"]:
            pilot.append(next(i for i in ids if lookup[i]["Output Type"] == kind))
        for i in ids:
            if len(pilot) == 5:
                break
            if lookup[i]["Calculator ID"] not in {lookup[j]["Calculator ID"] for j in pilot}:
                pilot.append(i)
        plan = {"source_revision":REVISION,"model":"", "base_url":"", "image":"",
                "approved_by":"", "approval_reference":"", "runs_per_side":3,
                "agent":"medcalc-native@"+REVISION+"+bridge-0.1", "task_ids":ids, "pilot_ids":pilot,
                "status":"proposal; no model calls executed", "api_calls_upper_bound":(3*2*110+2*5)*20}
        with args.output.open("x") as handle:
            json.dump(plan, handle, indent=2)
    else:
        if args.plan is None:
            parser.error("--plan is required")
        run_original(json.loads(args.plan.read_text()), rows, sources, args.output, args.run_index, args.pilot)


if __name__ == "__main__":
    main()
