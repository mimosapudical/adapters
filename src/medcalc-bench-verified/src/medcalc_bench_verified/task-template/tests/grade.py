"""Runs only in the fresh verifier; answers are data, never executable code."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from grading import load_scorer, score_answer

root = Path(__file__).parent
scorer = load_scorer((root/"upstream_evaluate.py").read_text())
gold = json.loads((root/"gold.json").read_text())
answer_path = Path("/workspace/answer.txt")
reward = 0
if answer_path.is_file() and answer_path.stat().st_size <= 128:
    reward = score_answer(answer_path.read_text().strip(), gold, scorer)
Path("/logs/verifier/reward.txt").write_text(str(reward) + "\n")
