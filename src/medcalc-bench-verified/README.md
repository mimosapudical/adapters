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

Prepared proposal: 110 deterministic cases, two per calculator; five pilot cases
cover distinct calculators and decimal/integer/date outputs. Frozen IDs and a
verified image digest are in `validation/parity-plan.proposed-r09.json`.
The model, endpoint and team approval fields are deliberately blank.

The original code-augmented controller is now available as
`medcalc_bench_verified.native_agent:MedCalcNativeAgent`. Its three upstream
controller functions are loaded without editing their bodies. An HTTP shim
adapts the legacy OpenAI client call to an OpenAI-compatible endpoint. Original
system/user message roles, Python-code feedback, retries by the model and the
20-turn limit are preserved. No generation code or gold data enters the model
prompt. All 1,100 instructions round-trip to the exact native request.

The independent original-side runner starts Docker directly and grades against
the pinned original scorer. Numeric inputs are screened before its unsafe eval;
the Harbor bridge invokes the same original controller in Harbor's container.
Both sides must use the approved exact model, endpoint, image and resources.
Original-side Docker uses bridge networking; Harbor uses its public-egress policy.
The tasks need no private endpoints, but this network-policy distinction must be
reviewed in the parity plan before live execution. Native protocol replay is
separate from CLI-agent generalization; a standard Codex/Claude Code run remains
part of the team-coordinated evaluation requirements.

After team confirmation, fill the plan and set the API key in the execution
environment (never put a key in the JSON or repository):

```bash
# These commands have NOT been run with a real model.
uv run medcalc-bench-verified --split parity --output-dir /tmp/parity-tasks
uv run python -m medcalc_bench_verified.run_paired --plan approved-plan.json --output /new/evidence-directory
```

The driver enforces the order pilot-original → pilot-Harbor → run-1-original →
run-1-Harbor → run-2-original → run-2-Harbor → run-3-original → run-3-Harbor.
Missing trials, API failures or container errors stop collection; they are not
silently converted to model failures. The driver writes raw arrays, means,
sample SEM and range-overlap status only after three complete runs per side.
An offline stub validates transport and execution only; it is never recorded as
model parity or a benchmark score.

Report original/Harbor raw run scores, mean ± sample SEM, per-calculator results,
errors, and the required overlap of run-score ranges. SEM = sample standard
deviation / sqrt(number of runs). Range overlap is the repository's acceptance
rule, not a formal proof of statistical equivalence. Retain raw traces and actual
API costs. Dataset and Hugging Face evidence publication remain pending.

## Notes & Caveats

Preflight base: Harbor Index adapters `7b4df9deb2381ae32f26e6cebec06aaa2975dc56`.
Existing v2 merged-PR search returned no results at initial preflight. An older merged
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
- [x] Implement original-controller and Harbor bridge plus paired experiment driver.
- [ ] Execute team-approved live-model parity and a standard CLI-agent evaluation.
- [ ] Publish task/evidence datasets and obtain structural and semantic review.

New files are confined to this adapter and a fork-only validation workflow. Do not
modify existing adapters, shared validators, clinical formulas, dataset answers,
or the original benchmark's train/test split. Relevant original functions:
`evaluation/evaluate.py:11–53` (`check_correctness`) and
`evaluation/generate_code_prompt.py:50–66` (`apply_calc` prompt construction).
There is no existing MedCalc implementation in the checked Harbor source tree.

First Docker smoke failed before grading because the separate verifier lacked an environment definition. Added tests/Dockerfile and a regression assertion; the failed run remains available in Actions. The second smoke exposed the corresponding runtime contract: separate-verifier checks must be baked into the verifier image. Added COPY . /tests/ only in tests/Dockerfile, never the agent Dockerfile. Both were adapter environment failures, not model failures.

Full reference validation continues on commit `6b0130e2128fe1a188906c3eb8bab893f732bdef`
and the original branch. `validation/evidence-r08.json` independently checks six
artifact ZIP digests, 600 unique oracle rewards of 1 and 600 unique nop rewards
of 0, with zero exceptions. It is explicitly partial. Raw ZIPs remain available
from Actions for 14 days. At the next live check, shards 6 and 7 also passed. Shard 8 failed before grading because its GitHub runner Docker daemon was stopped; an independent shard-8 recovery explicitly starts/checks Docker. Final pass counts remain pending completion of all jobs.

The parity work is isolated on `medcalc-native-parity-r08`. A byte-level comparison
against the oracle commit checks all 1,100 generated full-test tasks before
carrying oracle evidence forward; the native bridge has separate offline Docker
integration CI. This avoids rerunning unchanged generated tasks when only the
native agent, subset selector or reporting code changes.

A final evidence workflow waits for original shards 9/10 and recovery shard 8,
then validates exactly 1,100 unique tasks per control and matching task checksums.
It archives all raw logs and its full summary for 90 days. It fails closed on
missing cases, duplicates, exceptions, wrong rewards or a shared verifier.
The proposed PR description is in `validation/pr-draft-r14.md`; it is not submitted.

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
