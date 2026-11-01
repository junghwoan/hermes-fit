"""Local issue ledger. Records are assertions, not proof of user or model identity."""
import contextlib
import fcntl
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from . import core, evalpack

FIELDS=('issue','revision','proposal','run','target','profile','user','after_digest')
def _safe_dir(path):
    path=Path(os.path.abspath(path)); cur=Path(path.anchor)
    for part in path.parts[1:]:
        cur=cur/part
        try:
            if stat.S_ISLNK(cur.lstat().st_mode): raise ValueError('symlink in state path')
        except FileNotFoundError: cur.mkdir(mode=0o700)
    if not cur.is_dir(): raise ValueError('state is not a directory')
    return cur

def _binding(b):
    if set(b)!=set(FIELDS): raise ValueError('invalid binding fields')
    if not all(isinstance(b[k],str) and b[k] for k in ('issue','proposal','run','target','profile','user','after_digest')): raise ValueError('missing binding')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',b['issue']) or not isinstance(b['revision'],int) or isinstance(b['revision'],bool) or b['revision']<0: raise ValueError('invalid issue or revision')
    if not re.fullmatch(r'[0-9a-f]{64}',b['proposal']) or not re.fullmatch(r'[0-9a-f]{64}',b['after_digest']): raise ValueError('invalid digest')
    if (b['target']!='memories/USER.md' and not re.fullmatch(r'skills/[a-z0-9][a-z0-9-]*/(?:SKILL\.md|references/[a-zA-Z0-9._-]+\.md)',b['target'])) or b['target'].startswith('skills/hermes-fit/'): raise ValueError('unsupported target')
    return dict(b)

class Store:
    def __init__(self,path): self.path=_safe_dir(path)
    @contextlib.contextmanager
    def locked(self):
        path=self.path/'lock'
        fd=os.open(path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'r+') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            yield
    def _path(self,issue):
        if not isinstance(issue,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',issue): raise ValueError('invalid issue')
        p=self.path/(issue+'.json')
        if p.is_symlink(): raise ValueError('symlink ledger')
        return p
    def _read(self,issue):
        p=self._path(issue)
        if not p.is_file(): raise ValueError('unknown issue')
        return json.loads(p.read_text())
    def _write(self,issue,data):
        p=self._path(issue); fd,tmp=tempfile.mkstemp(dir=self.path,prefix='.write-')
        try:
            with os.fdopen(fd,'w') as f:
                json.dump(data,f,ensure_ascii=False,sort_keys=True); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,p)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    def start(self,binding):
        b=_binding(binding)
        if b['revision']!=0: raise ValueError('initial revision must be zero')
        with self.locked():
            if self._path(b['issue']).exists(): raise ValueError('issue exists')
            for path in self.path.glob('*.json'):
                if path.is_symlink(): raise ValueError('symlink ledger')
                data=json.loads(path.read_bytes())
                for revision in data.get('revisions',[]):
                    previous=revision['binding']
                    if all(previous[k]==b[k] for k in ('target','profile','user')) and (previous['proposal']==b['proposal'] or previous['run']==b['run']):
                        raise ValueError('binding already belongs to an issue')
            self._write(b['issue'],{'schema':'hermes-fit/feedback-v1','max_rounds':2,'revisions':[{'binding':b,'parent':None,'feedback':None,'observation':'caller asserted binding; native execution not attested'}]})
    def record(self,entry):
        if set(entry)!=set(FIELDS)|{'feedback_id','rating','reason'}: raise ValueError('invalid feedback fields')
        b=_binding({k:entry[k] for k in FIELDS})
        if entry['rating'] not in ('better','same','worse') or not isinstance(entry['reason'],str) or not isinstance(entry['feedback_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',entry['feedback_id']): raise ValueError('invalid explicit feedback')
        with self.locked():
            data=self._read(b['issue']); current=data['revisions'][-1]
            if current['binding']!=b: raise ValueError('binding mismatch')
            if current['feedback'] or any(r['feedback'] and r['feedback']['id']==entry['feedback_id'] for r in data['revisions']): raise ValueError('duplicate or replayed feedback')
            current['feedback']={'id':entry['feedback_id'],'rating':entry['rating'],'reason':core.redact(entry['reason'])[:2000]}
            self._write(b['issue'],data)
    def _plan(self,data):
        cur=data['revisions'][-1]; fb=cur['feedback']; remaining=max(0,data['max_rounds']-cur['binding']['revision'])
        preserved=[r['feedback']['reason'] for r in data['revisions'] if r['feedback'] and r['feedback']['rating']=='better' and r['feedback']['reason']]
        if data.get('stopped'): status=data['stopped']
        elif fb is None: status='unknown'
        elif fb['rating']=='better': status='satisfied'
        elif remaining==0: status='budget_exhausted'
        elif not fb['reason'].strip(): status='insufficient_evidence'
        else: status='needs_cause_review'
        return {'status':status,'remaining_rounds':remaining,'binding':cur['binding'],'preserved':preserved,'requires_new_approval':status=='needs_cause_review','observations':data.get('observations',[]),'note':'Feedback is a user-reported observation, not causality or an independent evaluation.'}
    def plan(self,issue):
        with self.locked(): return self._plan(self._read(issue))
    def revise(self,issue,binding,cause,evidence,guardrails):
        b=_binding(binding)
        with self.locked():
            data=self._read(issue); plan=self._plan(data); prev=plan['binding']
            if plan['status']!='needs_cause_review': raise ValueError('iteration stopped')
            if b['issue']!=issue or b['revision']!=prev['revision']+1 or b['user']!=prev['user'] or b['profile']!=prev['profile'] or b['target']!=prev['target'] or b['proposal']==prev['proposal'] or b['run']==prev['run']: raise ValueError('revision binding mismatch')
            if cause!='instruction' or not isinstance(evidence,list) or not evidence or not all(isinstance(x,str) and x.startswith('E-') for x in evidence): raise ValueError('instruction cause and evidence required')
            # A string flag cannot be accepted as a test. The packet must bind to this proposal.
            if not isinstance(guardrails,dict) or guardrails.get('proposal')!=b['proposal']: raise ValueError('bound recheck required')
            try:
                outcome=evalpack.validate(guardrails.get('packet',{}),guardrails.get('run',{}))
            except ValueError as exc:
                if str(exc)=='guardrail regression or unverified guardrail':
                    data['stopped']='guardrail_regression'; self._write(issue,data)
                raise
            if guardrails['packet'].get('proposal')!=b['proposal']: raise ValueError('proposal/recheck mismatch')
            hashes=guardrails['packet']['source_hashes']
            if hashes['candidate']!=b['after_digest'] or hashes['baseline']!=prev['after_digest']: raise ValueError('evaluated content does not match revision chain')
            if outcome['status']!='complete': raise ValueError('insufficient heldout')
            data['revisions'].append({'binding':b,'parent':prev['proposal'],'feedback':None,'cause':cause,'evidence':evidence,'recheck':outcome,'observation':'caller supplied recheck; independence and application not attested'})
            self._write(issue,data)
    def observe(self,entry):
        if set(entry)!=set(FIELDS)|{'task_id','observation'}: raise ValueError('invalid observation fields')
        b=_binding({k:entry[k] for k in FIELDS})
        if not isinstance(entry['task_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',entry['task_id']) or not isinstance(entry['observation'],str) or not entry['observation'].strip(): raise ValueError('invalid task observation')
        with self.locked():
            data=self._read(b['issue'])
            if data['revisions'][-1]['binding']!=b: raise ValueError('binding mismatch')
            events=data.setdefault('observations',[])
            if any(e['task_id']==entry['task_id'] for e in events): raise ValueError('duplicate task')
            events.append({'task_id':entry['task_id'],'revision':b['revision'],'observation':core.redact(entry['observation'])[:2000],'kind':'caller-reported comparable task; not causality'})
            self._write(b['issue'],data)
    def stop(self,issue,reason):
        if reason not in ('no_change','insufficient_evidence','guardrail_regression'): raise ValueError('invalid stop reason')
        with self.locked():
            data=self._read(issue); data['stopped']=reason; self._write(issue,data)
    def approval(self,issue,origin):
        raise ValueError('helper cannot mint approvals; use native gates and live user approval')
