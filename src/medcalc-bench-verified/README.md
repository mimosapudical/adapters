# MedCalc-Bench Verified → Harbor

## Overview

Full public test split: 1,100 cases, 55 calculators, 20 cases each. No training
or one-shot examples are adapted. Full Docker reference validation is complete.
Live-model parity and registry publication are pending.

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
- The native Harbor bridge preserves upstream chat messages and the 20-turn controller.
  Both parity sides use a fresh, credential-free Docker worker for each model code
  block. The host owns the API connection and Harbor receives only the final answer.
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

Each role has its own Dockerfile. Only the verifier image contains grading code and gold data; the agent image contains neither. Answer artifacts are materialized at
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
build logs. The parity plan pins the evaluation image digest. Docker with Compose
is required.

To verify the current native bridge without a model key, run the same smoke
test used in CI on a Docker host:

```bash
bash scripts/smoke_native.sh /tmp/medcalc-native-smoke
```

The output directory must be new. The test verifies real container execution
with scripted replies, grading, and the captured answer and trace on three cases.

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

Prepared proposal: 110 deterministic cases, two per calculator; five pilot cases
cover distinct calculators and decimal/integer/date outputs. Frozen IDs and a
verified image digest are in `validation/parity-plan.proposed-r15.json`.
The model, endpoint and team approval fields are deliberately blank.

The original-side runner feeds the pinned controller directly from test rows. The
Harbor side reconstructs the same request from generated tasks and passes the
answer through artifact collection and a separate verifier. Both paths use the
same original controller, HTTP transport, pinned worker image and restricted
scorer. A shared worker limits each Python block to 30 seconds and 64 KiB of
console output. It starts without network access or host mounts. Review these
execution differences from the published native harness with the team before
running parity. A standard Codex or Claude Code evaluation remains pending.

After team confirmation, fill the plan, pull its digest-pinned image with Docker, and set the API key in the execution
environment (never put a key in the JSON or repository):

```bash
# These commands have NOT been run with a real model.
uv run medcalc-bench-verified --split parity --output-dir /tmp/parity-tasks
uv run python -m medcalc_bench_verified.run_paired --plan approved-plan.json --output /new/evidence-directory
```

For a five-case check only, append `--pilot-only`; this writes a pilot summary
explicitly marked as incomplete parity. The fork's **MedCalc approved model
experiment** workflow provides the same entry point: keep `pilot_only=true`,
select the reviewed ref, enter the team-confirmed model/endpoint/approval, and store its key as the
`MEDCALC_API_KEY` repository Actions secret. The workflow never starts on a
push and never treats a pilot as the full three-repeat experiment.

The driver follows the same paired order for every invocation. On a persistent
Linux Docker host, start with `--pilot-only`. After reviewing the pilot, run the
same command and output path with `--resume --through-run 1`, then advance
through runs 2 and 3. Completed stages are checked from their raw results and
reused. The driver checks the plan and adapter files before resuming and stops
on incomplete stages so their attempts can be inspected. It writes the full
mean, sample SEM and range-overlap summary after all three pairs are complete.
Use a persistent host for the full experiment if the pilot projects a longer
runtime than the hosted job allows.

An offline stub validates transport and execution only; it is never recorded as
model parity or a benchmark score.

Report original/Harbor raw run scores, mean ± sample SEM, per-calculator results,
errors, and the required overlap of run-score ranges. SEM = sample standard
deviation / sqrt(number of runs). Range overlap is the repository's acceptance
rule, not a formal proof of statistical equivalence. Retain raw traces and actual
API costs. Dataset and Hugging Face evidence publication remain pending.

## Notes & Caveats

Reference validation used Harbor Docker and a separate verifier on all 1,100
test cases. Oracle returned reward 1 on 1,100/1,100 and Nop returned reward 0 on
1,100/1,100, with zero exceptions among accepted trials. One initial shard
stopped before grading because its Docker daemon was unavailable. The final
aggregation replaced that shard with its infrastructure recovery and checked
distinct IDs and matching task checksums across controls.

- [Final reference evidence and raw trial artifacts](https://github.com/mimosapudical/adapters/actions/runs/44444712671)
- [Native transport smoke on the earlier bridge](https://github.com/mimosapudical/adapters/actions/runs/44445431188)

The original oracle replays the released gold files. Numerical answer handling
uses restricted Python arithmetic for both sides of the proposed experiment.
The live comparison covers the resulting shared code execution configuration
and the selected subset. The standard CLI agent sees an output-file instruction
and is evaluated separately from the matched native-controller pair.

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

```bibtex
@inproceedings{khandekar2024medcalc,
  title = {MedCalc-Bench: Evaluating Large Language Models for Medical Calculations},
  author = {Khandekar, Nikhil and others},
  booktitle = {Advances in Neural Information Processing Systems},
  year = {2024},
  url = {https://arxiv.org/abs/2406.12036}
}
```

Runtime: https://github.com/harbor-framework/harbor/tree/99218a4611e3bd76e49ce3b5f977e8c8134ad3ac

## Authors & Contributions

Original benchmark and dataset: MedCalc-Bench / Verified contributors.
Adapter implementation and validation: Jingzhi Chen, with Codex assistance.
