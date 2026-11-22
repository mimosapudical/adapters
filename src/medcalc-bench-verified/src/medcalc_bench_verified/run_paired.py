"""Execute paired stages only after a concrete team-approved plan exists."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from .adapter import MedCalcBenchVerifiedAdapter
from .parity import read_rows, run_original, validate_plan


def collect_harbor(directory, expected_ids):
    records = []
    for path in directory.rglob('result.json'):
        result = json.loads(path.read_text())
        if 'trial_name' not in result:
            continue
        if result.get('exception_info') or result.get('verifier_environment_mode') != 'separate':
            raise RuntimeError(f'Harbor infrastructure failure: {path}')
        row_id = result['task_name'].rsplit('/', 1)[-1].removeprefix('case-')
        reward = (result.get('verifier_result') or {}).get('rewards', {}).get('reward')
        if reward not in (0, 1):
            raise ValueError(f'Missing or invalid reward: {path}')
        records.append({'row_id':row_id,'reward':reward})
    if len(records) != len(expected_ids) or {r['row_id'] for r in records} != set(expected_ids):
        raise ValueError('Incomplete or duplicated Harbor result coverage')
    return {'side':'harbor','cases':records,'score':statistics.mean(r['reward'] for r in records)}


def comparison(original, harbor):
    if len(original) != 3 or len(harbor) != 3:
        raise ValueError('Exactly three completed runs per side are required')
    output = {'runs_per_side':3,'units':'fraction correct'}
    for name, values in [('original',original),('harbor',harbor)]:
        output[name] = {'runs':values,'mean':statistics.mean(values),'sample_sem':statistics.stdev(values)/math.sqrt(3)}
    output['ranges_overlap'] = max(original) >= min(harbor) and max(harbor) >= min(original)
    return output


def stage_scores(stage, ids):
    harbor = collect_harbor(stage / "harbor", ids)
    original = json.loads((stage / "original/result.json").read_text())
    records = original["cases"]
    if (
        len(records) != len(ids)
        or {record["row_id"] for record in records} != set(ids)
        or any(record["reward"] not in (0, 1) for record in records)
    ):
        raise ValueError(f"Incomplete or invalid original results: {stage}")
    original["score"] = statistics.mean(record["reward"] for record in records)
    return original, harbor


def run_stage(stage, index, ids, plan, rows, sources, cache_dir):
    stage.mkdir()
    run_original(plan, rows, sources, stage / "original", index, pilot=(index == 0))
    tasks = MedCalcBenchVerifiedAdapter(stage / "tasks", task_ids=ids, cache_dir=cache_dir).run()
    for task in tasks:
        for image in [task / "environment/Dockerfile", task / "tests/Dockerfile"]:
            content = image.read_text().splitlines()
            content[0] = "FROM " + plan["image"]
            image.write_text("\n".join(content) + "\n")
    env = {**os.environ, "OPENAI_BASE_URL": plan["base_url"]}
    command = [
        sys.executable, "-m", "harbor.cli.main", "run", "-p", str((stage / "tasks").resolve()),
        "-a", "medcalc_bench_verified.native_agent:MedCalcNativeAgent", "-m", plan["model"],
        "-n", "1", "--max-retries", "0", "--agent-kwarg", f"code_image={plan['image']}",
        "--agent-kwarg", f"cache_dir={cache_dir.resolve()}", "--jobs-dir",
        str((stage / "harbor").resolve()), "--job-name", stage.name,
    ]
    with (stage / "harbor-command.log").open("x") as log:
        subprocess.run(command, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)


def run_experiment(output, plan, cache_dir, through, resume):
    package = Path(__file__).parent
    code_files = sorted(
        path for path in package.rglob("*") if path.is_file() and "__pycache__" not in path.parts
    )
    manifest = {
        "plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
        "files": {
            path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in code_files
        },
    }
    receipt = output / "experiment.json"
    if resume:
        if json.loads(receipt.read_text()) != manifest:
            raise ValueError("The approved plan or adapter files changed since the previous stage")
    else:
        output.mkdir(parents=True, exist_ok=False)
        receipt.write_text(json.dumps(manifest, indent=2))

    rows, sources = read_rows(cache_dir)
    original_scores, harbor_scores = [], []
    for index in range(through + 1):
        label = "pilot" if index == 0 else f"run-{index}"
        ids = plan["pilot_ids"] if index == 0 else plan["task_ids"]
        stage = output / label
        completed = stage / "harbor-summary.json"
        if not stage.exists():
            run_stage(stage, index, ids, plan, rows, sources, cache_dir)
        elif not completed.is_file():
            raise RuntimeError(f"Unfinished stage at {stage}. Preserve and inspect its attempts before retrying.")
        original, harbor = stage_scores(stage, ids)
        if not completed.exists():
            completed.write_text(json.dumps(harbor, indent=2))
        if index == 0:
            pilot = output / "pilot-summary.json"
            if not pilot.exists():
                pilot.write_text(json.dumps({
                    "pilot_only": True, "full_parity_complete": False,
                    "original": original, "harbor": harbor,
                }, indent=2))
        else:
            original_scores.append(original["score"])
            harbor_scores.append(harbor["score"])
    result = output / "comparison.json"
    if through == 3 and not result.exists():
        result.write_text(json.dumps(comparison(original_scores, harbor_scores), indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--pilot-only", action="store_true")
    stage.add_argument("--through-run", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/harbor-medcalc")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    validate_plan(plan)
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required")
    through = 0 if args.pilot_only else args.through_run
    run_experiment(args.output, plan, args.cache_dir, through, args.resume)


if __name__ == "__main__":
    main()
