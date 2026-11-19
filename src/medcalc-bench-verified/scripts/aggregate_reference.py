"""Require 1,100 exact positive/negative controls across original and recovery runs."""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--original',type=Path,required=True)
p.add_argument('--recovery',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
records={'oracle':{},'nop':{}}
for root,recovery in [(a.original,False),(a.recovery,True)]:
    for path in root.rglob('result.json'):
        # The failed original shard never reached grading; only its replacement
        # is authoritative. Do not silently combine partial/duplicate attempts.
        if not recovery and any(part.endswith('-shard-8') for part in path.parts):
            continue
        j=json.loads(path.read_text())
        if 'trial_name' not in j:continue
        assert not j.get('exception_info'),str(path)
        assert j.get('verifier_environment_mode')=='separate',str(path)
        role=j['agent_info']['name']
        assert role in records,role
        name=j['task_name'].rsplit('/',1)[-1]
        row=int(name.removeprefix('case-'))
        assert 1<=row<=1100 and (not recovery or (row-1)%11==8),str(path)
        reward=j['verifier_result']['rewards']['reward']
        assert reward==(1 if role=='oracle' else 0),str(path)
        assert row not in records[role],(role,row)
        records[role][row]={'reward':reward,'task_checksum':j['task_checksum'],'trial_name':j['trial_name']}
for role in records:
    assert set(records[role])==set(range(1,1101)),(role,len(records[role]))
for row in range(1,1101):
    assert records['oracle'][row]['task_checksum']==records['nop'][row]['task_checksum'],row
summary={'complete':True,'oracle_cases':1100,'oracle_full_reward':1100,'nop_cases':1100,'nop_zero_reward':1100,
         'exceptions':0,'live_model_parity':False,'original_workflow_run':44413335549,'recovery_workflow_run':44444186906,
         'generator_equivalence_workflow_run':44443894631,
         'oracle_source_commit':'6b0130e2128fe1a188906c3eb8bab893f732bdef',
         'note':'Combined original shards 0-7,9,10 and infrastructure recovery shard 8. No exclusions. Original runner Docker outage retained in history.',
         'records':records}
a.output.parent.mkdir(parents=True,exist_ok=True)
with a.output.open('x') as stream:json.dump(summary,stream,indent=2)
print('PASS: 1100/1100 full-reward oracles, 1100/1100 zero-reward nop controls, zero exceptions; model parity remains pending.')
