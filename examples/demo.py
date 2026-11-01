#!/usr/bin/env python3
"""SYNTHETIC, disposable CLI journey; all native writes and judgments are simulated."""
import hashlib, json, pathlib, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
CLI=ROOT/'skills/hermes-fit/scripts/hermes_fit.py'
sys.path.insert(0,str(CLI.parent))
from hfit import core, evalpack

def main():
    with tempfile.TemporaryDirectory() as directory:
        root=pathlib.Path(directory).resolve(); home=root/'home'; target=home/'skills/demo/SKILL.md'; target.parent.mkdir(parents=True); target.write_text('Give a long answer.\n')
        def call(*args):
            p=subprocess.run([sys.executable,'-I',str(CLI),'--hermes-home',str(home),*map(str,args)],text=True,capture_output=True)
            if p.returncode: raise RuntimeError(p.stderr)
            return json.loads(p.stdout)
        def write(name,obj):
            path=root/name; path.write_text(json.dumps(obj,ensure_ascii=False)); return path
        def prepared(n):
            header={'schema':'hermes-fit/turns-v1','profile':'demo','range':{'start':'2026-01-01T00:00:00+00:00','end':'2026-02-01T00:00:00+00:00'},'tz':'UTC','budget':{'max_sessions':20,'max_user_turns':20},'single_user_confirmed':True,'source':'SYNTHETIC','fidelity':'verbatim'}
            turns=[{'session_id':f'synthetic-{n}-{i}','turn_id':f'turn-{i}','ts':'2026-01-02T00:00:00+00:00','role':'user','author_id':'demo','content':'Please make it shorter','tool_call_id':None,'synthetic':True} for i in range(20)]
            path=root/f'input-{n}.jsonl'; path.write_text('\n'.join(json.dumps(x) for x in [header,*turns])+'\n')
            result=call('prepare',path,'--seed','2'); run=pathlib.Path(result['run']); train=json.loads((run/'evidence.train.json').read_text()); held=call('heldout-ids',run.name)['ids']
            if not train['items'] or len(held)<3: raise RuntimeError('synthetic split unexpectedly small')
            return run,train,held
        def stage(run,train,held,before,after):
            p={'target':{'kind':'skill_md','relpath':'skills/demo/SKILL.md','profile':'demo'},'op':{'replace':{'old':before,'new':after}},'baseline_digest':hashlib.sha256(target.read_bytes()).hexdigest(),'applicability':{'scope':'task:demo'},'reason':'Synthetic style example','evidence_ids':[train['items'][0]['id']],'counterevidence_ids':[],'denominator':{'sessions':train['counts']['sessions'],'user_turns':train['counts']['user_turns']},'preserved_behaviors':['Preserve facts and legitimate disagreement.'],'eval_plan':{'heldout_ids':held,'guardrail_case_ids':[case['id'] for case in evalpack.GUARDRAILS]},'origin':'interactive'}
            return call('stage',write('proposal.json',p),'--evidence',run/'evidence.train.json')
        print('SYNTHETIC: no user history, Hermes tool, model or actual approval is used.')
        run,train,held=prepared(1); first=stage(run,train,held,'long','short'); print('Native plan:',call('native-plan',first['id'])['tool'])
        target.write_text('Give a short answer.\n')  # Simulation only, inside the temporary directory.
        print('Simulated target:',call('verify',first['id'])['status'])
        b={'issue':'demo','revision':0,'proposal':first['id'],'run':run.name,'target':'skills/demo/SKILL.md','profile':'demo','user':'demo','after_digest':first['predicted_after_digest']}
        call('feedback-start',write('binding.json',b)); print('Before feedback:',call('feedback-status','demo')['status'])
        call('feedback-record',write('feedback.json',dict(b,feedback_id='f1',rating='worse',reason='The answer omitted a needed detail.')))
        print('After feedback:',call('feedback-status','demo')['status'])
        run2,train2,held2=prepared(2); second=stage(run2,train2,held2,'short','concise but complete')
        packed=call('eval-pack',run2/'evidence.train.json',run2/'heldout.sealed.json',second['id']); packet=json.loads(pathlib.Path(packed['packet']).read_text())
        judgments=[{'id':case['id'],'baseline':'Synthetic response preserves approval and facts.','candidate':'Synthetic response preserves approval and facts.','verdict':'tie','baseline_judgment':'met','candidate_judgment':'met','baseline_evidence':'approval','candidate_evidence':'approval'} for case in packet['cases']]
        review={'packet_digest':packet['digest'],'results':judgments}; print('Simulated recheck:',call('eval-validate',packed['packet'],write('review.json',review))['status'])
        target.write_text('Give a concise but complete answer.\n')  # Simulation only; no native approval or tool was invoked.
        b2=dict(b,revision=1,proposal=second['id'],run=run2.name,after_digest=second['predicted_after_digest'])
        request={'binding':b2,'cause':'instruction','evidence':second['evidence_ids'],'recheck':{'proposal':second['id'],'packet':packet,'run':review}}
        call('feedback-revise',write('revision.json',request))
        call('feedback-record',write('feedback2.json',dict(b2,feedback_id='f2',rating='better',reason='The concise answer kept the detail.')))
        print('After revision feedback:',call('feedback-status','demo')['status'])
        print('Simulated judgments do not establish independent review or user benefit.')
if __name__=='__main__': main()
