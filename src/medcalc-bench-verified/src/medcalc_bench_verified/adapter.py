"""Materialize the complete public test split without exposing gold metadata."""
import ast
import csv
import io
import json
import shutil
from pathlib import Path
from .source import load_source


def upstream_prompt(source, row):
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                    and n.name == "apply_calc")
    statements = []
    for node in function.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "messages" for t in node.targets):
            break
        statements.append(node)
    env = {"question": row["Question"], "patient_note": row["Patient Note"]}
    exec(compile(ast.Module(body=statements, type_ignores=[]), "upstream/prompt", "exec"), env)
    return env["system"] + "\n\n" + env["prompt"]


class MedCalcBenchVerifiedAdapter:
    def __init__(self, output_dir, limit=None, overwrite=False, task_ids=None,
                 cache_dir=Path.home()/".cache"/"harbor-medcalc", split="test",
                 shard_index=0, shard_count=1):
        if split != "test":
            raise ValueError("Only the full test split is implemented")
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        if not 0 <= shard_index < shard_count:
            raise ValueError("Invalid shard")
        self.output_dir = Path(output_dir)
        self.limit, self.overwrite, self.task_ids = limit, overwrite, task_ids
        self.sources = load_source(Path(cache_dir))
        self.split, self.shard_index, self.shard_count = split, shard_index, shard_count

    def run(self):
        rows = list(csv.DictReader(io.StringIO(self.sources["datasets/test_data.csv"].read_text())))
        ids = [r["Row Number"] for r in rows]
        if len(rows) != 1100 or len(set(ids)) != 1100:
            raise ValueError("Unexpected upstream split")
        if self.task_ids and set(self.task_ids) - set(ids):
            raise ValueError("Unknown task ID")
        if self.task_ids:
            rows = [r for r in rows if r["Row Number"] in self.task_ids]
        rows = rows[self.shard_index::self.shard_count]
        if self.limit:
            rows = rows[:self.limit]
        paths = [self.output_dir / f"case-{r['Row Number']}" for r in rows]
        if any(p.exists() for p in paths) and not self.overwrite:
            raise FileExistsError("Output tasks already exist; use --overwrite")
        template = Path(__file__).parent / "task-template"
        prompt_source = self.sources["evaluation/generate_code_prompt.py"].read_text()
        for row, target in zip(rows, paths):
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(template, target)
            config = (target/"task.toml").read_text().replace("{{TASK_ID}}", f"case-{row['Row Number']}")
            (target/"task.toml").write_text(config)
            instruction = upstream_prompt(prompt_source, row)
            instruction += "\nSave only your final answer value, without tags or units, to /workspace/answer.txt. Python is available.\n"
            (target/"instruction.md").write_text(instruction)
            gold = {k: row[k] for k in ("Calculator ID", "Ground Truth Answer", "Lower Limit", "Upper Limit")}
            (target/"tests/gold.json").write_text(json.dumps(gold))
            shutil.copyfile(self.sources["evaluation/evaluate.py"], target/"tests/upstream_evaluate.py")
            shutil.copyfile(Path(__file__).parent/"grading.py", target/"tests/grading.py")
            (target/"solution/answer.txt").write_text(row["Ground Truth Answer"])
        return paths
