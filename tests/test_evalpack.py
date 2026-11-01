import pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'skills/hermes-fit/scripts'))
from hfit import evalpack

class PackTests(unittest.TestCase):
    def setUp(self):
        self.train=[{'id':'E1','session_id':'train','text':'training'}]
        self.heldout=[{'id':'H'+str(i),'session_id':'held-'+str(i),'text':'task '+str(i)} for i in range(3)]
        self.packet=evalpack.pack(self.train,self.heldout,'base','candidate','a'*64,'seed')
    def results(self):
        return {'packet_digest':self.packet['digest'],'results':[{'id':c['id'],'baseline':'Must ask for approval','candidate':'Must ask for approval','verdict':'tie','baseline_judgment':'met','candidate_judgment':'met','baseline_evidence':'approval','candidate_evidence':'approval'} for c in self.packet['cases']]}
    def test_complete_and_bound(self):
        self.assertEqual(evalpack.validate(self.packet,self.results())['status'],'complete')
        packet=dict(self.packet,proposal='b'*64)
        with self.assertRaises(ValueError): evalpack.validate(packet,self.results())
    def test_guardrail_regression_and_empty_rejected(self):
        run=self.results(); run['results'][0]['candidate_judgment']='violated'
        with self.assertRaises(ValueError): evalpack.validate(self.packet,run)
        run=self.results(); run['results'][0]['candidate']=''
        with self.assertRaises(ValueError): evalpack.validate(self.packet,run)
    def test_leakage_rejected(self):
        with self.assertRaises(ValueError): evalpack.pack(self.train,[dict(self.heldout[0],session_id='train')],'a','b','a'*64,'x')
    def test_missing_and_false_pass_rejected(self):
        with self.assertRaises(ValueError): evalpack.validate(self.packet,{'packet_digest':self.packet['digest'],'results':[],'pass':True})

if __name__=='__main__': unittest.main()

class BindingTests(unittest.TestCase):
    def test_cannot_substitute_candidate(self):
        from hfit import feedback
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            store=feedback.Store(pathlib.Path(d).resolve()/'state')
            old={'issue':'i','revision':0,'proposal':'a'*64,'run':'r0','target':'skills/demo/SKILL.md','profile':'demo','user':'u','after_digest':'b'*64}
            store.start(old); store.record(dict(old,feedback_id='f',rating='worse',reason='Missing detail'))
            new=dict(old,revision=1,proposal='c'*64,run='r1',after_digest='d'*64)
            held=[{'id':'H'+str(i),'session_id':'s'+str(i),'text':'task'} for i in range(3)]
            packet=evalpack.pack([],held,'before','different',new['proposal'],'s')
            results=[{'id':c['id'],'baseline':'approval','candidate':'approval','verdict':'tie','baseline_judgment':'met','candidate_judgment':'met','baseline_evidence':'approval','candidate_evidence':'approval'} for c in packet['cases']]
            check={'proposal':new['proposal'],'packet':packet,'run':{'packet_digest':packet['digest'],'results':results}}
            with self.assertRaises(ValueError): store.revise('i',new,'instruction',['E-1'],check)
