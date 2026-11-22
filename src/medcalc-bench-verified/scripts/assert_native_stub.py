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
    feedback = trace['messages'][3]
    prefix = 'I have executed your code, and the output is:'
    suffix = 'If there was an error, or the computed answer is obviously incorrect,'
    assert feedback['role'] == 'user' and feedback['content'].startswith(prefix), trial
    output, separator, _ = feedback['content'][len(prefix):].partition(suffix)
    assert separator and output.strip() == '5', trial
print('3/3 native stub traces and answer artifacts verified; no model/API evidence claimed.')
