import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ReferenceCollectionTests(unittest.TestCase):
    def test_requires_complete_oracle_and_negative_controls(self):
        script=Path(__file__).parents[1]/'scripts/aggregate_reference.py'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for row in range(1,1101):
                location=root/('recovery' if (row-1)%11==8 else 'original')
                for role in ('oracle','nop'):
                    target=location/role/str(row)/'result.json'
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text(json.dumps({'trial_name':f'{role}-{row}','task_name':f'case-{row}',
                       'exception_info':None,'verifier_environment_mode':'separate','agent_info':{'name':role},
                       'task_checksum':f'synthetic-fixture-{row}', 'verifier_result':{'rewards':{'reward':int(role=='oracle')}}}))
            command=[sys.executable,str(script),'--original',str(root/'original'),'--recovery',str(root/'recovery')]
            subprocess.run(command+['--output',str(root/'good.json')],check=True,capture_output=True)
            report=json.loads((root/'good.json').read_text())
            self.assertEqual(report['oracle_cases'],1100)
            self.assertFalse(report['live_model_parity'])
            (root/'original/nop/1/result.json').unlink()
            bad=subprocess.run(command+['--output',str(root/'bad.json')],capture_output=True)
            self.assertNotEqual(bad.returncode,0)
            self.assertFalse((root/'bad.json').exists())


if __name__=='__main__':unittest.main()
