#!/usr/bin/env python3
"""Hermes Fit: offline evidence preparation and native tool planning."""
import argparse
import difflib
import json
import os
import re
import stat
import sys
from pathlib import Path
if sys.version_info < (3,10):
    raise SystemExit('Hermes Fit requires Python 3.10 or newer')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from hfit import core, feedback, evalpack, schedule

def read(path):
    path=Path(os.path.abspath(path)); current=Path(path.anchor)
    for part in path.parts[1:]:
        current=current/part
        if stat.S_ISLNK(current.lstat().st_mode): raise ValueError('symlink in input path')
    return path.read_bytes().decode('utf-8')
def load(path): return json.loads(read(path))
def save(path,obj):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2,sort_keys=True); f.write('\n')
def encoded(obj): return (json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8')
def prepared_run(home,ident):
    if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{64}',ident): raise ValueError('full run digest required')
    folder=state(home)/'runs'/ident
    manifest=load(folder/'manifest.json')
    if set(manifest)!={'evidence.train.json','heldout.sealed.json','report.json'}: raise ValueError('run manifest mismatch')
    if {x.name for x in folder.iterdir()}!=set(manifest)|{'manifest.json'}: raise ValueError('run file conflict')
    for name,value in manifest.items():
        if core.digest(read(folder/name).encode('utf-8'))!=value: raise ValueError('run file conflict')
    train=load(folder/'evidence.train.json'); held=load(folder/'heldout.sealed.json')
    if train.get('run_id')!=ident or held.get('run_id')!=ident or train.get('profile')!=held.get('profile'): raise ValueError('run binding mismatch')
    return folder,train,held

def check_author(p,b):
    binding=p.get('author_binding')
    if not isinstance(binding,dict): raise ValueError('missing author selection binding')
    if binding.get('kind')=='author_id':
        if binding.get('sha256')!=core.digest(core.canonical(b.get('user'))): raise ValueError('feedback user differs from selected author')
    elif binding!={'kind':'single_user_confirmed'}: raise ValueError('ambiguous feedback attribution')

def emit(obj): print(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True))
def state(home): return feedback._safe_dir(Path(home)/'hermes-fit')
def journal(home,ident,event,observation):
    folder=state(home); store=feedback.Store(folder)
    with store.locked():
        path=folder/'observations.jsonl'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'a',encoding='utf-8') as f:
            f.write(json.dumps({'proposal':ident,'event':event,'observation':observation},sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())

def staged(home,ident):
    if len(ident)!=64 or any(c not in '0123456789abcdef' for c in ident): raise ValueError('full proposal digest required')
    return load(state(home)/'staged'/(ident+'.json'))

def main():
    parser=argparse.ArgumentParser(description='Hermes Fit '+core.VERSION+' — offline helper; never applies target changes')
    parser.add_argument('--hermes-home',required=True,help='explicit Hermes home; no default')
    sub=parser.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('prepare'); p.add_argument('input'); p.add_argument('--seed',default='0'); p.add_argument('--author')
    p=sub.add_parser('heldout-ids'); p.add_argument('run')
    p=sub.add_parser('stage'); p.add_argument('proposal'); p.add_argument('--evidence',required=True)
    for name in ('preview','native-plan','verify','rollback-plan','verify-rollback'):
        p=sub.add_parser(name); p.add_argument('digest')
    p=sub.add_parser('feedback-start'); p.add_argument('binding')
    p=sub.add_parser('feedback-record'); p.add_argument('entry')
    p=sub.add_parser('feedback-status'); p.add_argument('issue')
    p=sub.add_parser('feedback-observe'); p.add_argument('entry')
    p=sub.add_parser('feedback-stop'); p.add_argument('issue'); p.add_argument('reason',choices=('no_change','insufficient_evidence','guardrail_regression'))
    p=sub.add_parser('feedback-revise'); p.add_argument('revision')
    p=sub.add_parser('eval-pack'); p.add_argument('train'); p.add_argument('heldout'); p.add_argument('proposal'); p.add_argument('--seed',default='0')
    p=sub.add_parser('eval-validate'); p.add_argument('packet'); p.add_argument('run')
    p=sub.add_parser('schedule-plan'); p.add_argument('--profile',required=True); p.add_argument('--cadence',required=True); p.add_argument('--timezone',required=True); p.add_argument('--active-timezone',required=True); p.add_argument('--export',required=True); p.add_argument('--native-version',required=True)
    p=sub.add_parser('pending-resolve'); p.add_argument('digest'); p.add_argument('--reason',required=True,choices=('applied','declined','no_change'))
    p=sub.add_parser('schedule-audit'); p.add_argument('digest')
    p=sub.add_parser('schedule-setup'); p.add_argument('plan'); p.add_argument('preflight')
    p=sub.add_parser('schedule-teardown-plan'); p.add_argument('plan'); p.add_argument('listing'); p.add_argument('--observed-profile',required=True)
    p=sub.add_parser('schedule-cleanup'); p.add_argument('plan'); p.add_argument('receipt'); p.add_argument('listing'); p.add_argument('--observed-profile',required=True)
    p=sub.add_parser('schedule-register'); p.add_argument('plan'); p.add_argument('receipt'); p.add_argument('listing'); p.add_argument('--observed-profile',required=True); p.add_argument('--active-timezone',required=True); p.add_argument('--native-record')
    args=parser.parse_args(); home=Path(os.path.abspath(args.hermes_home))
    try:
        if args.cmd=='prepare':
            lines=[json.loads(s) for s in read(args.input).splitlines() if s.strip()]
            if not lines: raise ValueError('empty export')
            result=core.prepare(lines[0],lines[1:],args.seed,args.author)
            run=feedback._safe_dir(state(home)/'runs')
            out=run/core.digest(core.canonical(result))
            documents={'evidence.train.json':{'items':result['train'],'counts':result['counts'],'total_denominators':result['total_denominators'],'author_binding':result['author_binding'],'seed':result['seed'],'run_id':out.name,'profile':lines[0]['profile']},
                       'heldout.sealed.json':{'items':result['heldout'],'seed':result['seed'],'run_id':out.name,'profile':lines[0]['profile']},'report.json':result['report']}
            documents['manifest.json']={name:core.digest(encoded(value)) for name,value in documents.items()}
            if out.exists():
                if out.is_symlink() or not out.is_dir() or {x.name for x in out.iterdir()}!=set(documents) or any(read(out/name).encode('utf-8')!=encoded(value) for name,value in documents.items()): raise ValueError('prepared run conflict')
            else:
                out.mkdir(mode=0o700)
                for name,value in documents.items(): save(out/name,value)
            emit({'run':str(out),'counts':result['counts'],'total_denominators':result['total_denominators'],'notice':'training counts exclude heldout; total denominators contain no category counts'})
        elif args.cmd=='heldout-ids':
            _,_,held=prepared_run(home,args.run)
            emit({'run_id':args.run,'ids':[item['id'] for item in held['items']]})
        elif args.cmd=='stage':
            evidence=load(args.evidence); expected=state(home)/'runs'/str(evidence.get('run_id',''))/'evidence.train.json'
            if Path(os.path.abspath(args.evidence))!=expected: raise ValueError('evidence must be the selected prepared run')
            prepared_run(home,evidence.get('run_id'))
            p=core.stage(home,load(args.proposal),evidence); d=feedback._safe_dir(state(home)/'staged')
            with feedback.Store(state(home)).locked():
                existing=[load(path) for path in d.glob('*.json')]
                same_run=[item for item in existing if item.get('run_id')==p['run_id']]
                if len(same_run)>=3: raise ValueError('three-proposal run limit')
                if any(item['target']['relpath']==p['target']['relpath'] for item in same_run): raise ValueError('duplicate target in run')
                save(d/(p['id']+'.json'),p)
            schedule.mark_pending(home,p['id']); journal(home,p['id'],'staged','proposal stored; no approval or native write observed'); emit(p)
        elif args.cmd=='preview':
            p=staged(home,args.digest); obs=core.verify(home,p)
            if obs['status']!='observed_before': raise ValueError('baseline is not current')
            target=core.target_path(home,p['target']); old=read(target) if target.exists() else ''; new=core._change(p,old.encode())
            emit({'proposal':p,'diff':''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before excerpt',tofile='after excerpt')),'evaluation':'unevaluated unless independently checked'})
        elif args.cmd=='native-plan':
            p=staged(home,args.digest); obs=core.verify(home,p)
            if obs['status']!='observed_before': raise ValueError('baseline is not current')
            emit(core.native_plan(p))
        elif args.cmd=='verify':
            obs=core.verify(home,staged(home,args.digest)); journal(home,args.digest,'verify',obs['status']); emit(obs)
        elif args.cmd=='verify-rollback':
            obs=core.verify(home,staged(home,args.digest)); emit({'status':'observed_before' if obs['status']=='observed_before' else 'rollback_conflict','observation':obs})
        elif args.cmd=='rollback-plan':
            plan=core.rollback_plan(home,staged(home,args.digest)); journal(home,args.digest,'rollback-plan',plan['status']); emit(plan)
        elif args.cmd=='feedback-start':
            b=load(args.binding); p=staged(home,b['proposal']); observation=core.verify(home,p)
            if p['origin']!='interactive': raise ValueError('scheduled proposals require interactive restaging')
            check_author(p,b)
            if observation['status']!='observed_after' or p['target']['relpath']!=b['target'] or p['target']['profile']!=b['profile'] or p['run_id']!=b['run'] or p['predicted_after_digest']!=b['after_digest']: raise ValueError('binding does not match observed target')
            feedback.Store(state(home)/'feedback').start(b); emit({'status':'recorded','observation':observation})
        elif args.cmd=='feedback-record': feedback.Store(state(home)/'feedback').record(load(args.entry)); emit({'status':'recorded'})
        elif args.cmd=='feedback-status': emit(feedback.Store(state(home)/'feedback').plan(args.issue))
        elif args.cmd=='feedback-observe': feedback.Store(state(home)/'feedback').observe(load(args.entry)); emit({'status':'observation recorded'})
        elif args.cmd=='feedback-stop': feedback.Store(state(home)/'feedback').stop(args.issue,args.reason); emit({'status':args.reason})
        elif args.cmd=='feedback-revise':
            request=load(args.revision); b=request['binding']; p=staged(home,b['proposal']); observation=core.verify(home,p)
            if p['origin']!='interactive': raise ValueError('scheduled proposals require interactive restaging')
            check_author(p,b)
            if not set(request['evidence']) or not set(request['evidence']).issubset(set(p['evidence_ids'])): raise ValueError('revision evidence is not bound to staged proposal')
            packet=request['recheck']['packet']; packet_id=packet.get('digest')
            if not isinstance(packet_id,str) or not re.fullmatch(r'[0-9a-f]{64}',packet_id): raise ValueError('full packet digest required')
            frozen=load(state(home)/'eval'/(packet_id+'.json'))
            if core.canonical(packet)!=core.canonical(frozen): raise ValueError('recheck must use the prepared frozen packet')
            if observation['status']!='observed_after' or p['target']['relpath']!=b['target'] or p['target']['profile']!=b['profile'] or p['run_id']!=b['run'] or p['predicted_after_digest']!=b['after_digest']: raise ValueError('revision target is not observed')
            feedback.Store(state(home)/'feedback').revise(b['issue'],b,request['cause'],request['evidence'],request['recheck']); emit({'status':'revision recorded','observation':observation})
        elif args.cmd=='eval-pack':
            train=load(args.train); held=load(args.heldout); proposal=staged(home,args.proposal)
            _,verified_train,verified_held=prepared_run(home,proposal['run_id'])
            if train!=verified_train or held!=verified_held: raise ValueError('evaluation input differs from verified run')
            if core.digest(core.canonical(train))!=proposal['evidence_digest'] or held.get('run_id')!=proposal['run_id'] or held.get('profile')!=proposal['target']['profile']: raise ValueError('evaluation input binding mismatch')
            if set(proposal['eval_plan']['heldout_ids'])!={x['id'] for x in held['items']}: raise ValueError('heldout coverage differs from proposal')
            if set(proposal['eval_plan']['guardrail_case_ids'])!={x['id'] for x in evalpack.GUARDRAILS}: raise ValueError('frozen guardrails differ from proposal')
            target=core.target_path(home,proposal['target'])
            if core.verify(home,proposal)['status']!='observed_before': raise ValueError('baseline is not current')
            baseline=read(target) if target.exists() else ''
            candidate=core._change(proposal,baseline.encode())
            if core.digest(candidate.encode())!=proposal['predicted_after_digest']: raise ValueError('candidate mismatch')
            packet=evalpack.pack(train['items'],held['items'],baseline,candidate,proposal['id'],args.seed)
            folder=feedback._safe_dir(state(home)/'eval'); save(folder/(packet['digest']+'.json'),packet)
            emit({'packet':str(folder/(packet['digest']+'.json')),'notice':'Keep private_baseline and source hashes away from the blind reviewer.'})
        elif args.cmd=='eval-validate': emit(evalpack.validate(load(args.packet),load(args.run)))
        elif args.cmd=='schedule-plan': emit(schedule.plan(home,args.profile,args.cadence,args.timezone,args.active_timezone,args.export,args.native_version))
        elif args.cmd=='pending-resolve':
            p=staged(home,args.digest)
            if args.reason=='applied' and core.verify(home,p)['status']!='observed_after': raise ValueError('after digest not observed')
            emit(schedule.resolve_pending(home,args.digest,args.reason))
        elif args.cmd=='schedule-audit': emit(schedule.inspect_audit(home,args.digest))
        elif args.cmd=='schedule-setup': emit(schedule.deploy(home,load(args.plan),load(args.preflight)))
        elif args.cmd=='schedule-teardown-plan': emit(schedule.teardown_plan(home,load(args.plan),load(args.listing),args.observed_profile))
        elif args.cmd=='schedule-cleanup': emit(schedule.cleanup(home,load(args.plan),load(args.receipt),load(args.listing),args.observed_profile))
        elif args.cmd=='schedule-register': emit(schedule.register(home,load(args.plan),load(args.receipt),load(args.listing),args.observed_profile,args.active_timezone,load(args.native_record) if args.native_record else None))
    except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as exc:
        print('error: '+str(exc),file=sys.stderr); return 2
    return 0
if __name__=='__main__': sys.exit(main())
