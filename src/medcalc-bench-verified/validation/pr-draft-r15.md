# [WIP] Adapter: medcalc-bench-verified

## Scope

Add the 1,100 public MedCalc-Bench Verified test cases spanning 55 calculators.
The generator pins the Verified v1.0.8 source commit and checks source hashes.
Harbor collects the answer as a task artifact and grades it in a separate
verifier. Jingzhi Chen developed the adapter, native bridge, and validation
with Codex assistance.

## Reference validation

| Control | Trials | Expected outcome | Observed outcome |
| --- | ---: | --- | ---: |
| Harbor Oracle | 1,100 | Reward 1 | 1,100 |
| Harbor Nop | 1,100 | Reward 0 | 1,100 |

The aggregate has zero exceptions, 1,100 distinct cases per control, and matching
task checksums for each case. One runner Docker outage was recovered before
aggregation. The oracle replays the released reference answer.

[Raw jobs and machine-checked summary](https://github.com/mimosapudical/adapters/actions/runs/44444712671)

## Matched evaluation

The native bridge preserves the pinned controller's chat flow and grading on
both sides. Model-generated Python runs in a separate, unnetworked Docker worker
without the API credential. The proposed 110-case subset selects two cases per
calculator, with five preselected cases for the paired pilot. Live parity,
standard CLI agent results, evidence publication and registry testing are pending.

Proposed tags: v1.0 and parity, subject to registry approval.

[Original benchmark](https://github.com/nikhilk7153/MedCalc-Bench-Verified)
