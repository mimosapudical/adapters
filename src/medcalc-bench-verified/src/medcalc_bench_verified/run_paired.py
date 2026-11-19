"""Execute paired stages only after a concrete team-approved plan exists."""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from .adapter import MedCalcBenchVerifiedAdapter
from .parity import read_rows, run_original, validate_plan


def collect_harbor(directory, expected_ids):
    records = []
    for path in directory.rglob('result.json'):
        result = json.loads(path.read_text())
        if 'trial_name' not in result:
            continue
        if result.get('exception_info') or result.get('verifier_environment_mode') != 'separate':
            raise RuntimeError(f'Harbor infrastructure failure: {path}')
        row_id = result['task_name'].rsplit('/', 1)[-1].removeprefix('case-')
        reward = (result.get('verifier_result') or {}).get('rewards', {}).get('reward')
        if reward not in (0, 1):
            raise ValueError(f'Missing or invalid reward: {path}')
        records.append({'row_id':row_id,'reward':reward})
    if len(records) != len(expected_ids) or {r['row_id'] for r in records} != set(expected_ids):
        raise ValueError('Incomplete or duplicated Harbor result coverage')
    return {'side':'harbor','cases':records,'score':statistics.mean(r['reward'] for r in records)}


def comparison(original, harbor):
    if len(original) != 3 or len(harbor) != 3:
        raise ValueError('Exactly three completed runs per side are required')
    output = {'runs_per_side':3,'units':'fraction correct'}
    for name, values in [('original',original),('harbor',harbor)]:
        output[name] = {'runs':values,'mean':statistics.mean(values),'sample_sem':statistics.stdev(values)/math.sqrt(3)}
    output['ranges_overlap'] = max(original) >= min(harbor) and max(harbor) >= min(original)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pilot-only', action='store_true')
    parser.add_argument('--cache-dir', type=Path, default=Path.home()/'.cache/harbor-medcalc')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    validate_plan(plan)
    if not os.environ.get('OPENAI_API_KEY'):
        parser.error('OPENAI_API_KEY is required')
    args.output.mkdir(parents=True, exist_ok=False)
    rows, sources = read_rows(args.cache_dir)
    original_scores, harbor_scores = [], []
    stages = [('pilot',plan['pilot_ids'],0)] + [(f'run-{i}',plan['task_ids'],i) for i in range(1,4)]
    if args.pilot_only:
        stages = stages[:1]
    for label, ids, index in stages:
        stage = args.output/label
        stage.mkdir()
        # Explicit order: both sides pilot, both sides run 1, both sides run 2, both sides run 3.
        run_original(plan, rows, sources, stage/'original', index, pilot=(index==0))
        tasks = MedCalcBenchVerifiedAdapter(stage/'tasks', task_ids=ids, cache_dir=args.cache_dir).run()
        for task in tasks:
            for image in [task/'environment/Dockerfile',task/'tests/Dockerfile']:
                content = image.read_text().splitlines()
                content[0] = 'FROM '+plan['image']
                image.write_text('\n'.join(content)+'\n')
        env = {**os.environ,'OPENAI_BASE_URL':plan['base_url']}
        command = [sys.executable,'-m','harbor.cli.main','run','-p',str((stage/'tasks').resolve()),
                   '-a','medcalc_bench_verified.native_agent:MedCalcNativeAgent','-m',plan['model'],
                   '-n','1','--max-retries','0','--jobs-dir',str((stage/'harbor').resolve()),'--job-name',label]
        with (stage/'harbor-command.log').open('w') as log:
            subprocess.run(command, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        harbor = collect_harbor(stage/'harbor', ids)
        (stage/'harbor-summary.json').write_text(json.dumps(harbor, indent=2))
        original = json.loads((stage/'original/result.json').read_text())
        if index:
            original_scores.append(original['score'])
            harbor_scores.append(harbor['score'])
    if args.pilot_only:
        (args.output/'pilot-summary.json').write_text(json.dumps({'pilot_only':True,'full_parity_complete':False,'original':original,'harbor':harbor},indent=2))
        return
    (args.output/'comparison.json').write_text(json.dumps(comparison(original_scores,harbor_scores),indent=2))


if __name__ == '__main__':
    main()
