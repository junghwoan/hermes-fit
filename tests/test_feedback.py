import pathlib, sys, tempfile, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'skills/hermes-fit/scripts'))
from hfit import feedback, evalpack, core

class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=feedback.Store(pathlib.Path(self.tmp.name).resolve()/'state')
        self.bind={'issue':'issue-1','revision':0,'proposal':'a'*64,'run':'run-1','target':'skills/demo/SKILL.md','profile':'demo','user':'user-1','after_digest':core.digest(b'before')}
        self.store.start(self.bind)
    def tearDown(self): self.tmp.cleanup()
    def record(self, rating='worse', reason='The output skipped a required detail', **changes):
        entry=dict(self.bind, feedback_id='feedback-1', rating=rating, reason=reason); entry.update(changes); return self.store.record(entry)
    def test_worse_needs_review_and_bounded_rounds(self):
        self.record(); plan=self.store.plan('issue-1'); self.assertEqual(plan['status'],'needs_cause_review'); self.assertTrue(plan['requires_new_approval']); self.assertEqual(plan['remaining_rounds'],2)
        with self.assertRaises(ValueError): self.store.revise('issue-1',dict(self.bind, revision=1,proposal='c'*64,run='run-2'),cause='instruction',evidence=[],guardrails='pass')
    def test_positive_preserved_and_stop(self):
        self.record('better','The shorter answer kept the facts'); plan=self.store.plan('issue-1'); self.assertEqual(plan['status'],'satisfied'); self.assertIn('kept the facts',plan['preserved'][0])
    def test_silence_unknown(self): self.assertEqual(self.store.plan('issue-1')['status'],'unknown')
    def test_replay_and_wrong_binding(self):
        for field,value in [('proposal','f'*64),('revision',1),('user','other'),('run','other'),('target','skills/other/SKILL.md')]:
            with self.assertRaises(ValueError): self.record(**{field:value})
        self.record()
        with self.assertRaises(ValueError): self.record()
    def test_guardrail_regression_refused(self):
        self.record()
        new=dict(self.bind,revision=1,proposal='c'*64,run='run-2')
        with self.assertRaises(ValueError): self.store.revise('issue-1',new,cause='instruction',evidence=['E-1'],guardrails='regression')
    def recheck(self,proposal,baseline,candidate):
        held=[{'id':'H'+str(i),'session_id':'s'+str(i),'text':'case '+str(i)} for i in range(3)]
        packet=evalpack.pack([],held,baseline,candidate,proposal,'seed')
        results=[{'id':c['id'],'baseline':'approval','candidate':'approval','verdict':'tie','baseline_judgment':'met','candidate_judgment':'met','baseline_evidence':'approval','candidate_evidence':'approval'} for c in packet['cases']]
        return {'proposal':proposal,'packet':packet,'run':{'packet_digest':packet['digest'],'results':results}}
    def test_two_round_limit(self):
        self.record(); prev=self.bind
        for revision in (1,2):
            baseline='before' if revision==1 else 'after-1'; candidate='after-'+str(revision)
            new=dict(prev,revision=revision,proposal=str(revision)*64,run='run-'+str(revision+1),after_digest=core.digest(candidate.encode()))
            self.store.revise('issue-1',new,cause='instruction',evidence=['E-1'],guardrails=self.recheck(new['proposal'],baseline,candidate))
            self.store.record(dict(new,feedback_id='feedback-'+str(revision+1),rating='worse',reason='Still misses the detail'))
            prev=new
        self.assertEqual(self.store.plan('issue-1')['status'],'budget_exhausted')
    def test_scheduled_cannot_approve(self):
        with self.assertRaises(ValueError): self.store.approval('issue-1',origin='scheduled')

if __name__=='__main__': unittest.main()

class ObservationTests(FeedbackTests):
    def test_comparable_task_linked_and_replay_rejected(self):
        event=dict(self.bind,task_id='task-1',observation='The next similar answer retained the required detail.')
        self.store.observe(event)
        self.assertEqual(self.store.plan('issue-1')['observations'][0]['task_id'],'task-1')
        with self.assertRaises(ValueError): self.store.observe(event)
        with self.assertRaises(ValueError): self.store.observe(dict(event,task_id='task-2',user='wrong'))
    def test_no_change_stop(self):
        self.record('same','No relevant instruction cause was found')
        self.store.stop('issue-1','no_change')
        self.assertEqual(self.store.plan('issue-1')['status'],'no_change')
    def test_guardrail_regression_persists_stop(self):
        self.record(); candidate='after'; new=dict(self.bind,revision=1,proposal='c'*64,run='run-2',after_digest=feedback.core.digest(candidate.encode()))
        check=self.recheck(new['proposal'],'before',candidate); check['run']['results'][0]['candidate_judgment']='violated'
        with self.assertRaises(ValueError): self.store.revise('issue-1',new,'instruction',['E-1'],check)
        self.assertEqual(self.store.plan('issue-1')['status'],'guardrail_regression')
