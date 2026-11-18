"""Fail closed on missing trials, infrastructure exceptions or wrong rewards."""
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("directory", type=Path)
p.add_argument("--expected-count", type=int, required=True)
p.add_argument("--reward", type=int, required=True)
a = p.parse_args()
trials = []
for path in a.directory.rglob("result.json"):
    result = json.loads(path.read_text())
    if "trial_name" in result:
        trials.append(result)
assert len(trials) == a.expected_count, (len(trials), a.expected_count)
assert len({t["task_name"] for t in trials}) == a.expected_count
bad = [t["trial_name"] for t in trials if t.get("exception_info") or
       t.get("verifier_result", {}).get("rewards", {}).get("reward") != a.reward or
       t.get("verifier_environment_mode") != "separate"]
print(json.dumps({"trials": len(trials), "expected_reward": a.reward, "failures": bad}, indent=2))
assert not bad, bad
