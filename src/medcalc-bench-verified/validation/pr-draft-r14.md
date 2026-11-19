# [WIP] Adapter: medcalc-bench-verified

Draft material only; no upstream PR has been opened.

Adds the complete 1,100-case public MedCalc-Bench Verified test split, covering
55 calculators. The adapter pins upstream revision
801592132bfd833f049b517a4e013e00a5fc40fa, preserves the original scoring function,
and keeps answers and grading code in a separate verifier.

The original code-augmented chat controller is also available through a Harbor
bridge. Original system/user messages, code feedback and the 20-turn limit remain
unchanged. An independent Docker runner and paired-stage driver are prepared.

Validation completed:
- 15 local tests plus 12 repository contract tests passed; package build passed.
- All 1,100 generated full-test tasks (12,100 files) are byte-identical to the
  commit under reference validation.
- Native bridge Docker integration passed with explicit offline stub responses,
  saved answer artifacts and traces. This is not model parity.
- Eight 100-case reference batches passed. One other batch failed before grading
  because its runner Docker daemon was stopped; a separate recovery run is active.
  The final 2,200-trial summary has not yet been produced.

Remaining before requesting upstream review:
- Finish reference validation and attach the complete machine-checked summary.
- Confirm the new entry and the team-approved exact model, endpoint and budget.
- Run native parity on the frozen 110-case proposal (2 per calculator), first
  with 5 paired pilot cases and then 3 runs per side. Also evaluate a standard
  CLI agent as required by the custom-agent guidance.
- Publish actual raw traces/costs and task data, populate parity_experiment.json,
  and request the dataset registry tag. No parity figures or publication links
  have been invented.

Source: https://github.com/nikhilk7153/MedCalc-Bench-Verified
Reference validation: https://github.com/mimosapudical/adapters/actions/runs/44413335549
Native bridge integration: https://github.com/mimosapudical/adapters/actions/runs/44443894631
Recovery: https://github.com/mimosapudical/adapters/actions/runs/44444186906

Contribution: complete benchmark adaptation and measurement-fidelity validation.
This is infrastructure work; no novel clinical method or algorithm is claimed.
AI assistance: Codex assisted with implementation and validation.
