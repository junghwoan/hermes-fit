import json, pathlib, subprocess, sys, tempfile, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'skills/hermes-fit/scripts'))
from hfit import core, feedback
ROOT=pathlib.Path(__file__).resolve().parents[1]
CLI=ROOT/'skills/hermes-fit/scripts/hermes_fit.py'
INSTALL=ROOT/'packaging/install_local.py'

class Hardening(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.tmp.name).resolve(); self.home=self.root/'home'; self.home.mkdir()
  self.header={'schema':'hermes-fit/turns-v1','profile':'demo','range':{'start':'2026-01-01T00:00:00+00:00','end':'2026-02-01T00:00:00+00:00'},'tz':'UTC','budget':{'max_sessions':20,'max_user_turns':20},'single_user_confirmed':True,'source':'synthetic','fidelity':'verbatim'}
 def tearDown(self): self.tmp.cleanup()
 def turn(self,session,text): return {'session_id':session,'turn_id':'t','ts':'2026-01-02T00:00:00+00:00','role':'user','author_id':'demo','content':text,'tool_call_id':None,'synthetic':True}
 def call(self,*args): return subprocess.run([sys.executable,'-I',str(CLI),'--hermes-home',str(self.home),*map(str,args)],capture_output=True,text=True)
 def test_train_counts_exclude_heldout(self):
  sessions=[str(i) for i in range(30)]; held=next(s for s in sessions if int(core.digest(('0\0'+s).encode())[:8],16)%5==0); train=next(s for s in sessions if s!=held and int(core.digest(('0\0'+s).encode())[:8],16)%5!=0)
  out=core.prepare(self.header,[self.turn(train,'too long'),self.turn(held,'forgot context')]); self.assertEqual(out['counts']['sessions'],1); self.assertNotIn('context_miss',out['counts']['matches']); self.assertEqual(out['total_denominators']['sessions'],2)
 def test_contractions_and_real_english_korean_quotes(self):
  for s in ("You didn't do the task", "You didn’t do the task",'실행하지 않았어요'):
   item=core.prepare(self.header,[self.turn('x',s)])['train'][0]; self.assertFalse(item['quoted'])
  for s in ("He said 'didn't do'",'그가 ‘실행하지’라고 말했다','> 실행하지 마','```실행하지```'):
   item=core.prepare(self.header,[self.turn('x',s)])['train'][0]; self.assertTrue(item['quoted'])
 def test_prepare_idempotent_and_opaque_heldout_ids(self):
  source=self.root/'in.jsonl'; source.write_text('\n'.join(json.dumps(x) for x in [self.header,*[self.turn(str(i),'too long') for i in range(12)]])+'\n')
  first=self.call('prepare',source); self.assertEqual(first.returncode,0,first.stderr); run=pathlib.Path(json.loads(first.stdout)['run']); second=self.call('prepare',source); self.assertEqual(second.returncode,0,second.stderr); self.assertEqual(first.stdout,second.stdout)
  ids=self.call('heldout-ids',run.name); self.assertEqual(ids.returncode,0,ids.stderr); self.assertEqual(set(json.loads(ids.stdout)['ids']),{x['id'] for x in json.loads((run/'heldout.sealed.json').read_text())['items']}); self.assertNotIn('too long',ids.stdout)
  (run/'heldout.sealed.json').write_text('{}'); conflict=self.call('prepare',source); self.assertNotEqual(conflict.returncode,0); self.assertIn('conflict',conflict.stderr.lower()); self.assertNotEqual(self.call('heldout-ids',run.name).returncode,0)
 def test_install_help_uninstall_reinstall_and_preserve_unknown(self):
  def run(*a): return subprocess.run([sys.executable,'-I',str(INSTALL),*a,'--hermes-home',str(self.home)],capture_output=True,text=True)
  self.assertEqual(run('install').returncode,0); installed=self.home/'skills/hermes-fit/scripts/hermes_fit.py'; self.assertEqual(subprocess.run([sys.executable,'-I',str(installed),'--help'],capture_output=True).returncode,0)
  result=run('uninstall'); self.assertEqual(result.returncode,0,result.stderr); self.assertFalse((self.home/'skills/hermes-fit').exists()); self.assertEqual(run('install').returncode,0)
  unknown=self.home/'skills/hermes-fit/user.txt'; unknown.write_text('mine'); result=run('uninstall'); self.assertIn('user.txt',result.stdout); self.assertEqual(unknown.read_text(),'mine')
 def test_guardrail_removal_and_partial_removal_refused(self):
  before=b'Ask for approval before external sends.\nGive long answers.\n'; target=self.home/'skills/demo/SKILL.md'; target.parent.mkdir(parents=True); target.write_bytes(before)
  e={'run_id':'a'*64,'profile':'demo','items':[{'id':'E-1','session_id':'s1','category':'style_correction','quoted':False,'text':'too long'}],'counts':{'sessions':1,'user_turns':1}}
  p={'target':{'kind':'skill_md','relpath':'skills/demo/SKILL.md','profile':'demo'},'op':{'replace':{'old':'Ask for approval before external sends.','new':'Send directly.'}},'baseline_digest':core.digest(before),'applicability':{'scope':'task:demo'},'reason':'example','evidence_ids':['E-1'],'denominator':{'sessions':1,'user_turns':1},'preserved_behaviors':['Preserve facts'],'eval_plan':{'guardrail_case_ids':['g']},'origin':'interactive'}
  with self.assertRaises(ValueError): core.stage(self.home,p,e)
  p['op']={'replace':{'old':'Ask for approval before external sends.','new':'When convenient, Ask for approval before external sends.'}}
  with self.assertRaises(ValueError): core.stage(self.home,p,e)
  p['op']={'replace':{'old':'Ask for ','new':''}}
  with self.assertRaises(ValueError): core.stage(self.home,p,e)
  p['op']={'replace':{'old':'long','new':'short'}}; self.assertTrue(core.stage(self.home,p,e)['id'])
 def test_issue_reset_refused(self):
  store=feedback.Store(self.home/'feedback'); b={'issue':'one','revision':0,'proposal':'a'*64,'run':'b'*64,'target':'skills/demo/SKILL.md','profile':'demo','user':'demo','after_digest':'c'*64}; store.start(b)
  with self.assertRaises(ValueError): store.start(dict(b,issue='two'))
  store.start(dict(b,issue='other',proposal='d'*64,run='e'*64))
 def staged_fixture(self, newline=b'\r\n'):
  target=self.home/'skills/demo/SKILL.md'; target.parent.mkdir(parents=True); target.write_bytes(b'Give long answers.'+newline)
  source=self.root/'input.jsonl'; source.write_text('\n'.join(json.dumps(x) for x in [self.header,*[self.turn(str(i),'too long') for i in range(20)]])+'\n')
  prep=self.call('prepare',source); self.assertEqual(prep.returncode,0,prep.stderr); run=pathlib.Path(json.loads(prep.stdout)['run']); train=json.loads((run/'evidence.train.json').read_text()); ids=json.loads(self.call('heldout-ids',run.name).stdout)['ids']
  from hfit import evalpack
  p={'target':{'kind':'skill_md','relpath':'skills/demo/SKILL.md','profile':'demo'},'op':{'replace':{'old':'long','new':'short'}},'baseline_digest':core.digest(target.read_bytes()),'applicability':{'scope':'task:demo'},'reason':'example','evidence_ids':[train['items'][0]['id']],'denominator':{'sessions':train['counts']['sessions'],'user_turns':train['counts']['user_turns']},'preserved_behaviors':['facts'],'eval_plan':{'heldout_ids':ids,'guardrail_case_ids':[x['id'] for x in evalpack.GUARDRAILS]},'origin':'interactive'}
  file=self.root/'proposal.json'; file.write_text(json.dumps(p)); staged=self.call('stage',file,'--evidence',run/'evidence.train.json'); self.assertEqual(staged.returncode,0,staged.stderr)
  return target,run,json.loads(staged.stdout)
 def test_crlf_preview_and_eval_preserve_exact_bytes(self):
  target,run,p=self.staged_fixture(); preview=self.call('preview',p['id']); self.assertEqual(preview.returncode,0,preview.stderr); self.assertIn('\r\n',json.loads(preview.stdout)['diff'])
  packet=self.call('eval-pack',run/'evidence.train.json',run/'heldout.sealed.json',p['id']); self.assertEqual(packet.returncode,0,packet.stderr); data=json.loads(pathlib.Path(json.loads(packet.stdout)['packet']).read_text()); self.assertEqual(data['source_hashes']['baseline'],core.digest(target.read_bytes())); self.assertEqual(data['source_hashes']['candidate'],core.digest(b'Give short answers.\r\n'))
 def test_feedback_author_and_packet_path_validation(self):
  target,run,p=self.staged_fixture(b'\n'); target.write_bytes(b'Give short answers.\n')
  binding={'issue':'issue','revision':0,'proposal':p['id'],'run':run.name,'target':'skills/demo/SKILL.md','profile':'demo','user':'wrong','after_digest':p['predicted_after_digest']}; file=self.root/'binding.json'; file.write_text(json.dumps(binding)); result=self.call('feedback-start',file); self.assertNotEqual(result.returncode,0); self.assertIn('author',result.stderr)
  binding['user']='demo'; file.write_text(json.dumps(binding)); self.assertEqual(self.call('feedback-start',file).returncode,0)
  req={'binding':binding,'cause':'instruction','evidence':p['evidence_ids'],'recheck':{'packet':{'digest':'../../outside'}}}; file.write_text(json.dumps(req)); result=self.call('feedback-revise',file); self.assertNotEqual(result.returncode,0); self.assertIn('full packet digest',result.stderr)
 def test_uninstall_refuses_active_monitor_and_preserves_edited_cache(self):
  def run(*a): return subprocess.run([sys.executable,'-I',str(INSTALL),*a,'--hermes-home',str(self.home)],capture_output=True,text=True)
  self.assertEqual(run('install').returncode,0); installed=self.home/'skills/hermes-fit/scripts/hermes_fit.py'; subprocess.run([sys.executable,'-I',str(installed),'--help'],capture_output=True,check=True)
  cache=next((installed.parent/'hfit/__pycache__').glob('*.pyc')); cache.write_bytes(b'edited by user'); monitor=self.home/'scripts/hermes_fit_monitor.py'; monitor.parent.mkdir(); monitor.write_text('user monitor')
  refused=run('uninstall'); self.assertNotEqual(refused.returncode,0); self.assertIn('schedule-teardown-plan',refused.stderr); self.assertTrue(installed.exists()); monitor.unlink()
  result=run('uninstall'); self.assertEqual(result.returncode,0,result.stderr); self.assertTrue(cache.exists()); self.assertIn(cache.name,result.stdout)
if __name__=='__main__': unittest.main()
