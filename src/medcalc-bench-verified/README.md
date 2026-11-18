# MedCalc-Bench Verified → Harbor

## Overview

Full public test split: 1,100 cases, 55 calculators, 20 cases each. No training
or one-shot examples are adapted. Status: development; model parity and registry
publication have not happened. Do not interpret offline scorer checks as Harbor
oracle trials or model parity.

## What is MedCalc-Bench Verified?

A corrected release of the NeurIPS 2024 MedCalc-Bench medical-calculation benchmark.
Each case has a patient note, question, clinical calculator, reference answer,
explanation and original grading bounds. Source:
https://github.com/nikhilk7153/MedCalc-Bench-Verified

Pinned source revision: `801592132bfd833f049b517a4e013e00a5fc40fa`.
The generator checks SHA-256 for the dataset, scorer and prompt source before use.
Dataset licensing is CC-BY-SA 4.0; attribution and source provenance remain in
this documentation and task metadata, outside the agent-visible workspace.

## Adapter Features

- Stable names based on original row numbers, full test split, deterministic CI shards.
- Original `check_correctness` function loaded from its AST without unused imports.
- Inclusive decimal bounds, Python integer rounding, date and gestational-age behavior retained.
- Untrusted numeric answers accept only bounded arithmetic, not Python calls or attributes.
  This deliberate input-safety restriction is the only scorer-language change; validated
  ordinary answers and boundary values are checked against the unrestricted original.
- Prompt prefix is extracted from upstream `apply_calc`; only an output-file instruction
  is appended. The standard CLI-agent interface is an adaptation of the code-augmented
  protocol, not a reproduction of the original chat controller or direct-answer table.
- Separate verifier, explicitly collected answer file, no gold files in the agent image.
- Oracle replays the published reference answer. It checks packaging/grading, not
  independent clinical correctness of the published answer or a reconstructed calculation.

## Generated Task Structure

```
case-<row>/
  task.toml
  instruction.md
  environment/Dockerfile
  solution/solve.sh
  solution/answer.txt
  tests/Dockerfile
  tests/test.sh
  tests/grade.py
  tests/grading.py
  tests/upstream_evaluate.py
  tests/gold.json
```

Each role has its own Dockerfile. No data is copied into either image at build time. Answer artifacts are materialized at
`/workspace/answer.txt` in the fresh verifier, per the pinned Harbor runtime.

## Run Evaluation / Harness

Registry execution is unavailable until the team publishes the dataset. Do not
use an invented registry ID. Once published, the intended registry invocation is
`harbor run -d medcalc-bench-verified/medcalc-bench-verified`.

For local reproduction, from this directory:

```bash
uv sync --locked
uv run medcalc-bench-verified --output-dir datasets/medcalc-bench-verified
uv run harbor run -p datasets/medcalc-bench-verified -a oracle -n 2 --max-retries 0
uv run harbor run -p datasets/medcalc-bench-verified -a nop -n 2 --max-retries 0
```

Compatibility/runtime pin: Harbor `99218a4611e3bd76e49ce3b5f977e8c8134ad3ac` (0.23.0).
Container base: `python:3.12.12-slim-bookworm`; the first workflow records actual
build logs, and a mutable tag must be replaced by the observed digest before
formal parity. Docker with Compose is required.

## Usage: Create Task Directories

```bash
uv run medcalc-bench-verified --output-dir /tmp/tasks
uv run medcalc-bench-verified --output-dir /tmp/pilot --limit 5
```

The CLI also accepts `--task-ids 1 2`, `--overwrite`, `--cache-dir`, and deterministic
`--shard-index K --shard-count N`. Unknown IDs, invalid shards, nonpositive limits,
modified cached inputs and unintended overwrites fail explicitly.

## Comparison with Original Benchmark (Parity)

No live-model parity has run. `parity_experiment.json` is intentionally empty.
Nothing in CI submits model API requests. Before model execution the team must
approve the exact agent version, dated model ID, budgets, prompt/tool interface,
subset and three runs per side. Ownership of this new entry remains unconfirmed.

Proposed study: choose two fixed cases per calculator (110 cases), run a 5–10-case
paired pilot, one full paired run, then two more paired runs. Freeze the IDs and
configuration first. Implement the selected CLI agent on the original-benchmark
fork and use identical instructions and budgets on both sides; do not compare a
CLI agent against the old chat controller. The 110-case proposal is not yet an
implemented/approved `parity` split. The CLI currently supports the complete test split.

Report original/Harbor raw run scores, mean ± sample SEM, per-calculator results,
errors, and the required overlap of run-score ranges. SEM = sample standard
deviation / sqrt(number of runs). Range overlap is the repository's acceptance
rule, not a formal proof of statistical equivalence. Retain raw traces and actual
API costs. Dataset and Hugging Face evidence publication remain pending.

## Notes & Caveats

Preflight base: Harbor Index adapters `7b4df9deb2381ae32f26e6cebec06aaa2975dc56`.
Existing v2 merged-PR search returned no results at preflight. An older merged
CanItEdit adapter provides a useful acceptance pattern: full oracle, negative
controls, genuine three-repeat matched parity, and published artifacts. Current
WIPs with partial oracle or pending parity are examples of incomplete milestones,
not evidence that those requirements are waived.

Implementation checklist:
- [x] Inspect source, prompts, original scorer and existing adapters for overlap.
- [x] Generate all 1,100 cases, preserving the original prompt prefix and scoring.
- [x] Keep gold data and scorer outside the agent image; use a separate verifier.
- [x] Offline scorer differential and hostile-answer checks.
- [ ] Complete Docker oracle 1,100/1,100 with zero exceptions and nop 0/1,100.
- [ ] Resolve exact image digest and team approval of ownership/parity configuration.
- [ ] Implement and execute the approved original-side agent, then matched model parity.
- [ ] Publish task/evidence datasets and obtain structural and semantic review.

New files are confined to this adapter and a fork-only validation workflow. Do not
modify existing adapters, shared validators, clinical formulas, dataset answers,
or the original benchmark's train/test split. Relevant original functions:
`evaluation/evaluate.py:11–53` (`check_correctness`) and
`evaluation/generate_code_prompt.py:50–66` (`apply_calc` prompt construction).
There is no existing MedCalc implementation in the checked Harbor source tree.

First Docker smoke failed before grading because the separate verifier lacked an environment definition. Added tests/Dockerfile and a regression assertion; the failed run remains available in Actions. This was an adapter environment failure, not a model failure.

All validation runs retain fresh filenames/run IDs. Offline tests are contract
checks; no clinical algorithm or novel scientific method is claimed. This is a
benchmark-infrastructure contribution; its coauthor route depends on Harbor
Index accepting the entry and ultimately merging the completed adapter.

## Installation / Prerequisites

Python 3.12+, uv, Linux Docker Engine with Compose; access to pinned public GitHub
files during generation. No GPU or model key is needed for oracle validation.
`uv sync --locked` installs the pinned Harbor test runtime. Production adapter
logic itself uses only the Python standard library.

## Troubleshooting

- A digest failure means the input is not the pinned release; do not bypass it.
- A missing answer scores zero. A missing scorer/gold or container error is an
  infrastructure failure and must not be described as model failure.
- CI fails for missing trials, exceptions, incorrect rewards, or shared verification.
- Structural validation currently reports missing completed parity. Do not fabricate
  an experiment entry to make that check green.

## Citation

MedCalc-Bench: Evaluating Large Language Models for Medical Calculations.
NeurIPS 2024 Datasets and Benchmarks. https://arxiv.org/abs/2406.12036

Harbor Adapters and Harbor-Index: Infrastructure and a Curated Meta-Dataset for
Large-Scale Agentic Evaluation. https://arxiv.org/abs/2609.04298

Runtime methodology: https://github.com/harbor-framework/harbor/tree/99218a4611e3bd76e49ce3b5f977e8c8134ad3ac

## Authors & Contributions

Original benchmark and dataset: MedCalc-Bench / Verified contributors.
Adapter implementation and validation: Jingzhi Chen, with Codex assistance.
