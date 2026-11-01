import json, pathlib, subprocess, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'skills/hermes-fit/scripts'))
from hfit import core

class InputTests(unittest.TestCase):
    def header(self):
        return {'schema':'hermes-fit/turns-v1','profile':'demo','range':{'start':'2026-01-01T00:00:00+00:00','end':'2026-02-01T00:00:00+00:00'},'tz':'UTC','budget':{'max_sessions':10,'max_user_turns':20},'single_user_confirmed':True,'source':'synthetic','fidelity':'verbatim'}
    def turn(self, session='s1', turn='1', content='Please stop asking unnecessarily', author='a'):
        return dict(session_id=session, turn_id=turn, ts='2026-01-02T00:00:00+00:00', role='user', author_id=author, content=content, tool_call_id=None, synthetic=True)
    def test_repeated_turns_and_replay(self):
        a=self.turn(); b=self.turn(turn='2'); result=core.prepare(self.header(),[a,b,dict(a)], seed='x')
        self.assertEqual(result['counts']['user_turns'],2)
    def test_mixed_missing_author_refused(self):
        with self.assertRaises(ValueError): core.prepare(self.header(),[self.turn(),self.turn(turn='2',author=None)])
    def test_multi_author_refused(self):
        with self.assertRaises(ValueError): core.prepare(self.header(),[self.turn(),self.turn(turn='2',author='b')])
    def test_select_author_refuses_mixed_session_context(self):
        with self.assertRaises(ValueError): core.prepare(self.header(),[self.turn(author='a'),self.turn(turn='2',author='b')],author='a')
    def test_select_author_excludes_other_sessions(self):
        result=core.prepare(self.header(),[self.turn('s1',author='a'),self.turn('s2',author='b')],author='a')
        self.assertEqual(result['counts']['sessions'],1)
        self.assertEqual(result['counts']['user_turns'],1)
    def test_invalid_time_budget(self):
        h=self.header(); h['range']['start']='2026-01-01T00:00:00'
        with self.assertRaises(ValueError): core.prepare(h,[self.turn()])
        h=self.header(); h['budget']['max_user_turns']=0
        with self.assertRaises(ValueError): core.prepare(h,[self.turn()])
    def test_replay_tool_id_does_not_inflate(self):
        a=self.turn(); a['tool_call_id']='call-1'; b=dict(a,turn_id='2')
        self.assertEqual(core.prepare(self.header(),[a,b])['counts']['user_turns'],1)
    def test_quoted_signal_and_secret_absent(self):
        text='"Please make it shorter" password=fictional-secret-123 testperson@example.com'
        out=core.prepare(self.header(),[self.turn(content=text)])
        items=out['train']+out['heldout']; self.assertTrue(items[0]['quoted'])
        self.assertNotIn('fictional-secret-123',json.dumps(out)); self.assertNotIn('testperson@example.com',json.dumps(out))
    def test_no_false_positive_and_redaction(self):
        self.assertNotIn('positive', core.categories('not great')); self.assertEqual(core.categories(''),[])
        self.assertNotIn('secret-canary@example.com',core.redact('secret-canary@example.com'))
    def test_split_context_never_crosses_sessions(self):
        turns=[self.turn('a','1'),dict(self.turn('b','2'),role='assistant',content='OTHER SESSION')]
        result=core.prepare(self.header(),turns, seed='x')
        self.assertNotIn('OTHER SESSION',json.dumps(result['train'])); self.assertNotIn('OTHER SESSION',json.dumps(result['heldout']))

class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.home=pathlib.Path(self.tmp.name).resolve()
        (self.home/'skills/demo').mkdir(parents=True); (self.home/'skills/demo/SKILL.md').write_text('before\n')
    def tearDown(self): self.tmp.cleanup()
    def proposal(self):
        return {'target':{'kind':'skill_md','relpath':'skills/demo/SKILL.md','profile':'demo'},'op':{'replace':{'old':'before','new':'after'}},'baseline_digest':core.digest(b'before\n'),'applicability':{'scope':'task:demo'},'reason':'test','evidence_ids':['E-1'],'counterevidence_ids':[],'denominator':{'sessions':1,'user_turns':1},'preserved_behaviors':['retain approval for destructive, external, credential and payment actions'],'eval_plan':{'heldout_ids':['H-1'],'guardrail_case_ids':['G-1']},'origin':'interactive'}
    def evidence(self):
        return {'run_id':'a'*64,'profile':'demo','items':[{'id':'E-1','session_id':'s1','category':'style_correction','quoted':False}], 'counts':{'sessions':1,'user_turns':1}}
    def test_stage_verify_conflict(self):
        staged=core.stage(self.home,self.proposal(),self.evidence()); self.assertEqual(core.verify(self.home,staged)['status'],'observed_before')
        target=self.home/'skills/demo/SKILL.md'; target.write_text('after\n'); self.assertEqual(core.verify(self.home,staged)['status'],'observed_after')
        target.write_text('after\nlater\n'); self.assertEqual(core.rollback_plan(self.home,staged)['status'],'rollback_conflict'); self.assertEqual(target.read_text(),'after\nlater\n')
    def test_forbidden_and_escape(self):
        for path in ['../SOUL.md','skills/hermes-fit/SKILL.md','SOUL.md','/tmp/a']:
            p=self.proposal(); p['target']['relpath']=path
            with self.assertRaises(ValueError): core.stage(self.home,p,self.evidence())
    def test_symlink_and_stale(self):
        (self.home/'skills/link').symlink_to(self.home/'skills/demo',target_is_directory=True)
        p=self.proposal(); p['target']['relpath']='skills/link/SKILL.md'
        with self.assertRaises(ValueError): core.stage(self.home,p,self.evidence())
        p=self.proposal(); p['baseline_digest']='0'*64
        with self.assertRaises(ValueError): core.stage(self.home,p,self.evidence())

class MonitorTests(unittest.TestCase):
    def test_stable_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d).resolve()/'export.jsonl'; path.write_text('synthetic')
            args=[sys.executable,str(ROOT/'skills/hermes-fit/scripts/monitor.py'),str(path)]
            self.assertEqual(subprocess.check_output(args),subprocess.check_output(args))

if __name__=='__main__': unittest.main()

class EvidenceGateTests(ProposalTests):
    def evidence(self):
        return {'run_id':'a'*64,'profile':'demo','items':[{'id':'E-1','session_id':'s1','category':'unnecessary_ask','quoted':False}], 'counts':{'sessions':1,'user_turns':1}}
    def test_unbound_or_quoted_evidence_refused(self):
        with self.assertRaises(ValueError): core.stage(self.home,self.proposal(),{'run_id':'a'*64,'profile':'demo','items':[],'counts':{'sessions':1,'user_turns':1}})
        evidence=self.evidence(); evidence['items'][0]['quoted']=True
        with self.assertRaises(ValueError): core.stage(self.home,self.proposal(),evidence)
    def test_sensitive_approval_preserved(self):
        p=self.proposal(); p['preserved_behaviors']=['be brief']
        with self.assertRaises(ValueError): core.stage(self.home,p,self.evidence())
    def test_wrong_denominator_refused(self):
        p=self.proposal(); p['denominator']['sessions']=7
        with self.assertRaises(ValueError): core.stage(self.home,p,self.evidence())

class MonitorSafetyTests(unittest.TestCase):
    def test_pending_freezes_fingerprint_and_parent_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve(); export=root/'export'; export.write_text('one'); state=root/'state'
            args=[sys.executable,str(ROOT/'skills/hermes-fit/scripts/monitor.py'),str(export),'--state',str(state)]
            baseline=subprocess.check_output(args); (state/'pending').write_text('review')
            export.write_text('two'); self.assertEqual(subprocess.check_output(args),baseline)
            (state/'pending').unlink(); self.assertNotEqual(subprocess.check_output(args),baseline)
            (root/'link').symlink_to(root,target_is_directory=True)
            result=subprocess.run([sys.executable,str(ROOT/'skills/hermes-fit/scripts/monitor.py'),str(root/'link/export')],capture_output=True)
            self.assertNotEqual(result.returncode,0)
