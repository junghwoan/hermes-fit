import hashlib, json, pathlib, subprocess, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
CLI=ROOT/'skills/hermes-fit/scripts/hermes_fit.py'
class CLITests(unittest.TestCase):
    def test_simulated_journey_and_feedback_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp).resolve(); home=root/'home'; target=home/'skills/demo/SKILL.md'; target.parent.mkdir(parents=True); target.write_text('before\n')
            def cmd(*args):
                p=subprocess.run([sys.executable,'-I',str(CLI),'--hermes-home',str(home),*map(str,args)],capture_output=True,text=True)
                return p
            header={'schema':'hermes-fit/turns-v1','profile':'demo','range':{'start':'2026-01-01T00:00:00+00:00','end':'2026-02-01T00:00:00+00:00'},'tz':'UTC','budget':{'max_sessions':2,'max_user_turns':3},'single_user_confirmed':True,'source':'synthetic','fidelity':'verbatim'}
            turn={'session_id':'s1','turn_id':'t1','ts':'2026-01-02T00:00:00+00:00','role':'user','author_id':'demo','content':'Please make it shorter','tool_call_id':None,'synthetic':True}
            export=root/'input.jsonl'; export.write_text(json.dumps(header)+'\n'+json.dumps(turn)+'\n')
            prepared=cmd('prepare',export,'--seed','0'); self.assertEqual(prepared.returncode,0,prepared.stderr)
            run=pathlib.Path(json.loads(prepared.stdout)['run']); train=json.loads((run/'evidence.train.json').read_text())
            if not train['items']: self.skipTest('synthetic case assigned to heldout')
            p={'target':{'kind':'skill_md','relpath':'skills/demo/SKILL.md','profile':'demo'},'op':{'replace':{'old':'before','new':'after'}},'baseline_digest':hashlib.sha256(b'before\n').hexdigest(),'applicability':{'scope':'task:demo'},'reason':'Improve brevity','evidence_ids':[train['items'][0]['id']],'counterevidence_ids':[],'denominator':{'sessions':1,'user_turns':1},'preserved_behaviors':['keep facts'], 'eval_plan':{'heldout_ids':[],'guardrail_case_ids':['G-approval','G-factual','G-boundary']},'origin':'interactive'}
            path=root/'proposal.json'; path.write_text(json.dumps(p)); staged=cmd('stage',path,'--evidence',run/'evidence.train.json'); self.assertEqual(staged.returncode,0,staged.stderr)
            proposal=json.loads(staged.stdout); ident=proposal['id']; self.assertEqual(json.loads(cmd('native-plan',ident).stdout)['tool'],'skill_manage')
            self.assertEqual(json.loads(cmd('verify',ident).stdout)['status'],'observed_before')
            duplicate=dict(p,reason='A different proposal for the same target'); duplicate_path=root/'duplicate.json'; duplicate_path.write_text(json.dumps(duplicate))
            self.assertNotEqual(cmd('stage',duplicate_path,'--evidence',run/'evidence.train.json').returncode,0)
            other=home/'skills/scheduled/SKILL.md'; other.parent.mkdir(); other.write_text('before\n')
            scheduled=dict(p,origin='scheduled',target={'kind':'skill_md','relpath':'skills/scheduled/SKILL.md','profile':'demo'}); scheduled_path=root/'scheduled.json'; scheduled_path.write_text(json.dumps(scheduled))
            scheduled_result=cmd('stage',scheduled_path,'--evidence',run/'evidence.train.json'); self.assertEqual(scheduled_result.returncode,0,scheduled_result.stderr)
            scheduled_proposal=json.loads(scheduled_result.stdout)
            # Explicit synthetic simulation; no native call and no real approval.
            target.write_text('after\n'); observed=json.loads(cmd('verify',ident).stdout); self.assertEqual(observed['status'],'observed_after'); self.assertIn('unverified',observed['observation'])
            binding={'issue':'sample','revision':0,'proposal':ident,'run':run.name,'target':'skills/demo/SKILL.md','profile':'demo','user':'demo','after_digest':proposal['predicted_after_digest']}
            other.write_text('after\n'); scheduled_binding=dict(binding,issue='scheduled',proposal=scheduled_proposal['id'],target='skills/scheduled/SKILL.md'); sb=root/'scheduled-binding.json'; sb.write_text(json.dumps(scheduled_binding))
            self.assertNotEqual(cmd('feedback-start',sb).returncode,0)
            bp=root/'binding.json'; bp.write_text(json.dumps(binding)); self.assertEqual(cmd('feedback-start',bp).returncode,0)
            ep=root/'entry.json'; ep.write_text(json.dumps(dict(binding,feedback_id='f1',rating='worse',reason='The detail was missing')))
            self.assertEqual(cmd('feedback-record',ep).returncode,0); self.assertNotEqual(cmd('feedback-record',ep).returncode,0)
            self.assertEqual(json.loads(cmd('feedback-status','sample').stdout)['status'],'needs_cause_review')
            target.write_text('after\nlater edit\n'); self.assertEqual(json.loads(cmd('rollback-plan',ident).stdout)['status'],'rollback_conflict'); self.assertEqual(target.read_text(),'after\nlater edit\n')

if __name__=='__main__': unittest.main()

class ScheduleTests(unittest.TestCase):
    def test_invalid_schedule_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as d:
            home=pathlib.Path(d).resolve()/'unused'
            p=subprocess.run([sys.executable,'-I',str(CLI),'--hermes-home',str(home),'schedule-plan','--profile','demo','--cadence','0 9 * * 1','--timezone','UTC','--active-timezone','UTC','--native-version','0.22.2','--export','/synthetic.jsonl'],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0); self.assertFalse(home.exists())
