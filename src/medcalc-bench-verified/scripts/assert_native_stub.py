"""A zero reward alone does not prove that the bridge actually executed."""
import json
from pathlib import Path
import sys
root=Path(sys.argv[1])
trials=[p.parent for p in root.rglob('result.json') if 'trial_name' in json.loads(p.read_text())]
assert len(trials)==3
for trial in trials:
    assert (trial/'artifacts/answer.txt').read_text()=='5', trial
    trace=json.loads((trial/'agent/native-trace.json').read_text())
    assert trace['answer']=='5', trial
    assert '\n5\n' in trace['messages'][3]['content'], trial
print('3/3 native stub traces and answer artifacts verified; no model/API evidence claimed.')
