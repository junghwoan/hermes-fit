"""Local, deliberately conservative preparation and native-write planning."""
import datetime as dt
import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

VERSION = '0.1.0-beta.1'

def digest(data): return hashlib.sha256(data).hexdigest()
def canonical(obj): return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
def stamp(value):
    try: result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError): raise ValueError('invalid RFC3339 timestamp')
    if result.tzinfo is None or result.utcoffset() is None: raise ValueError('timestamp requires offset')
    return result

_PATTERNS = [
 ('pem',r'-----BEGIN [^-]+-----[\s\S]*?-----END [^-]+-----'),
 ('url_credentials',r'(?i)\bhttps?://[^\s/@:]+:[^\s/@]+@[^\s/]+'),
 ('bearer',r'(?i)\bBearer\s+[^\s]+'),
 ('assignment',r'(?i)\b(?:password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+'),
 ('key',r'\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|AKIA[A-Z0-9]{16})\b'),
 ('jwt',r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'),
 ('email',r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b'),
 ('phone',r'(?<!\w)(?:\+\d{1,3}[ -]?)?(?:\d{2,4}[ -]){2,3}\d{3,4}(?!\w)'),
 ('long_token',r'\b[A-Za-z0-9+/=_-]{32,}\b')]
def redact(text):
    for kind, pattern in _PATTERNS: text = re.sub(pattern, '[REDACTED:'+kind+']', text)
    return text

LEXICON = {'style_correction':['too verbose','shorter','too long','간결','너무 길','말투'], 'unnecessary_ask':['stop asking','unnecessary approval','묻지 마','물어보지'], 'failure_to_execute':['did not execute','didn\'t do','실행하지','안 했'], 'context_miss':['forgot context','missed context','맥락','잊었'], 'unsupported_completion':['not done','not completed','완료하지','완료 안'], 'positive':['great','thank you','좋아요','고마워'], 'explicit_preference':['i prefer','always prefer','선호','원해요']}
def categories(text):
    lower=text.lower().replace('’',"'"); found=[]
    for category, words in LEXICON.items():
        if any(w in lower for w in words):
            if category=='positive' and re.search(r'\b(?:not|never|isn.t|wasn.t)\b|안\s*좋|별로',lower): continue
            found.append(category)
    return found

def quoted_text(text):
    # An apostrophe within a word is punctuation, not a quotation boundary.
    return bool(re.search(r'```|(^|\n)\s*>|[“”"]|(?<!\w)[\'‘][^\n]*?[\'’]',text))

def prepare(header, turns, seed='0', author=None):
    required={'schema','profile','range','tz','budget','single_user_confirmed','source','fidelity'}
    allowed=required|{'hermes_home_id'}
    if set(header)-allowed or not required <= set(header) or header['schema']!='hermes-fit/turns-v1': raise ValueError('unsupported header')
    if not isinstance(header['profile'],str) or not header['profile'] or not isinstance(header['single_user_confirmed'],bool) or not header['tz'] or header['fidelity'] not in ('summary','verbatim'): raise ValueError('invalid header')
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try: ZoneInfo(header['tz'])
    except (ZoneInfoNotFoundError,ValueError,TypeError): raise ValueError('invalid timezone')
    start,end=stamp(header['range']['start']),stamp(header['range']['end'])
    if start>=end: raise ValueError('invalid range')
    fields={'session_id','turn_id','ts','role','author_id','content','tool_call_id','synthetic'}
    cleaned=[]; ids={}; tools={}
    for t in turns:
        if set(t)!=fields or t['role'] not in ('user','assistant','system','tool') or not all(isinstance(t[k],str) and t[k] for k in ('session_id','turn_id')) or not isinstance(t['content'],str) or not isinstance(t['synthetic'],bool): raise ValueError('invalid turn')
        if not start<=stamp(t['ts'])<end: raise ValueError('turn outside range')
        if t['author_id'] is not None and (not isinstance(t['author_id'],str) or not t['author_id']): raise ValueError('invalid author')
        if t['tool_call_id'] is not None and (not isinstance(t['tool_call_id'],str) or not t['tool_call_id']): raise ValueError('invalid tool id')
        key=(t['session_id'],t['turn_id']); tk=(t['session_id'],t['tool_call_id'])
        if key in ids:
            if ids[key]!=t: raise ValueError('conflicting replay identifier')
            continue
        if t['tool_call_id'] and tk in tools:
            if tools[tk]['content']!=t['content'] or tools[tk]['role']!=t['role']: raise ValueError('conflicting tool replay')
            continue
        ids[key]=t
        if t['tool_call_id']: tools[tk]=t
        cleaned.append(t.copy())
    users=[t for t in cleaned if t['role']=='user']; authors={t['author_id'] for t in users}
    if author:
        if None in authors: raise ValueError('missing author prevents safe selection')
        selected_sessions={t['session_id'] for t in users if t['author_id']==author}
        if not selected_sessions: raise ValueError('selected author has no turns')
        if any(t['session_id'] in selected_sessions and t['author_id']!=author for t in users): raise ValueError('mixed-author session cannot be safely isolated')
        users=[t for t in users if t['author_id']==author]
        cleaned=[t for t in cleaned if t['session_id'] in selected_sessions]
    elif len(authors)>1 or (None in authors and not header['single_user_confirmed']): raise ValueError('ambiguous author attribution')
    selected_author=author or (next(iter(authors)) if len(authors)==1 else None)
    author_binding={'kind':'author_id','sha256':digest(canonical(selected_author))} if selected_author else {'kind':'single_user_confirmed'}
    sessions={t['session_id'] for t in cleaned}; budget=header['budget']
    if any(not isinstance(budget.get(k),int) or isinstance(budget[k],bool) or budget[k]<0 for k in ('max_sessions','max_user_turns')): raise ValueError('invalid budget')
    if len(sessions)>budget['max_sessions'] or len(users)>budget['max_user_turns']: raise ValueError('budget exceeded')
    grouped={}
    for t in cleaned: grouped.setdefault(t['session_id'],[]).append(t)
    out={'train':[],'heldout':[]}; counts={}; session_counts={}; train_sessions=set(); train_users=0
    for session, items in grouped.items():
        partition='heldout' if int(digest((seed+'\0'+session).encode())[:8],16)%5==0 else 'train'
        for i,t in enumerate(items):
            if t['role']!='user': continue
            if partition=='train': train_sessions.add(session); train_users+=1
            text=redact(t['content']); quoted=quoted_text(text)
            for cat in categories(text):
                eid='E-'+digest(canonical([session,t['turn_id'],cat]))[:12]
                def nearby(step):
                    j=i+step
                    while 0<=j<len(items):
                        if items[j]['role']=='assistant': return redact(items[j]['content'])[:300]
                        j+=step
                    return None
                item={'id':eid,'session_id':'S-'+digest(session.encode())[:16],'turn_id':'T-'+digest((session+'\0'+t['turn_id']).encode())[:16],'category':cat,'text':text,'previous_assistant':nearby(-1),'next_assistant':nearby(1),'quoted':quoted,'source_fidelity':header['fidelity'],'label':'candidate signal, not semantic understanding'}
                out[partition].append(item)
                if partition=='train': counts[cat]=counts.get(cat,0)+1; session_counts.setdefault(cat,set()).add(session)
    out['counts']={'sessions':len(train_sessions),'user_turns':train_users,'matches':counts,'sessions_per_category':{k:len(v) for k,v in session_counts.items()}}
    out['total_denominators']={'sessions':len(sessions),'user_turns':len(users)}; out['author_binding']=author_binding
    out['seed']=seed; out['report']={'schema':'hermes-fit/report-v1','proposals':[],'reason':'No changes proposed; review candidate signals and counterevidence in context.'}
    return out

def safe_path(home, rel, create=False):
    root=Path(os.path.abspath(home)); path=PurePosixPath(rel)
    if path.is_absolute() or any(x in ('..','.') for x in path.parts) or '\\' in rel: raise ValueError('unsafe path')
    parts=path.parts
    memory=parts==('memories','USER.md')
    skill=(len(parts)==3 and parts[0]=='skills' and parts[2]=='SKILL.md') or (len(parts)==4 and parts[0]=='skills' and parts[2]=='references' and parts[3].endswith('.md'))
    if not memory and (not skill or not re.fullmatch(r'[a-z0-9][a-z0-9-]*',parts[1]) or parts[1]=='hermes-fit'): raise ValueError('forbidden target')
    cur=Path(root.anchor)
    for part in root.parts[1:]+parts:
        if cur.exists():
            names=[p.name for p in cur.iterdir() if p.name.casefold()==part.casefold()]
            if names and part not in names: raise ValueError('case collision')
        cur=cur/part
        try:
            if stat.S_ISLNK(cur.lstat().st_mode): raise ValueError('symlink forbidden')
        except FileNotFoundError: pass
    return cur

def target_path(home,target):
    kind=target.get('kind')
    if kind=='user_memory':
        if target.get('memory_target')!='user' or target.get('relpath','memories/USER.md')!='memories/USER.md': raise ValueError('unsupported memory target')
        rel='memories/USER.md'
    elif kind=='skill_md':
        rel=target.get('relpath','')
        if rel=='memories/USER.md': raise ValueError('unsupported skill target')
    else: raise ValueError('unsupported target')
    return safe_path(home,rel)

def _occurrences(text,span):
    return sum(text.startswith(span,i) for i in range(len(text)-len(span)+1)) if span else 0

def _change(p,before):
    op=p['op']; kind=p['target']['kind']; text=before.decode('utf-8')
    if len(op)!=1: raise ValueError('one operation required')
    if 'replace' in op and kind=='skill_md':
        old=op['replace'].get('old'); new=op['replace'].get('new')
        if not isinstance(old,str) or not old or not isinstance(new,str) or _occurrences(text,old)!=1: raise ValueError('unique old text required')
        return text.replace(old,new,1)
    if 'create' in op and kind=='skill_md':
        new=op['create'].get('new')
        if not isinstance(new,str) or not new.strip(): raise ValueError('create requires content')
        front=re.match(r'\A---\s*\r?\n(.*?)\r?\n---(?:\r?\n|$)',new,re.S)
        if not front: raise ValueError('new skill requires frontmatter')
        names=re.findall(r'^name:[ \t]*(.+)$',front.group(1),re.M); descriptions=re.findall(r'^description:[ \t]*(.+)$',front.group(1),re.M)
        expected=PurePosixPath(p['target']['relpath']).parts[1]
        if len(names)!=1 or names[0].strip().strip("\"'")!=expected or len(descriptions)!=1 or not descriptions[0].strip(): raise ValueError('new skill needs matching name and description')
        return new
    if kind=='user_memory':
        entries=[x.strip() for x in text.split('\n§\n') if x.strip()]
        if '\n§\n'.join(entries)!=text or len(set(entries))!=len(entries): raise ValueError('memory is not in canonical entry format')
        if 'memory_add' in op:
            new=op['memory_add'].get('text')
            if not isinstance(new,str) or not new.strip() or new!=new.strip() or '\n§\n' in new or new in entries: raise ValueError('invalid memory add')
            return '\n§\n'.join(entries+[new])
        if 'memory_replace' in op:
            old=op['memory_replace'].get('old_text'); new=op['memory_replace'].get('text')
            if not isinstance(old,str) or not old.strip() or not isinstance(new,str) or not new.strip() or '\n§\n' in new or '\n§\n' in old or _occurrences(text,old)!=1: raise ValueError('invalid memory patch')
            return text.replace(old,new,1)
    raise ValueError('unsupported operation')

def stage(home,p,evidence):
    if not isinstance(p,dict) or p.get('origin') not in ('interactive','scheduled'): raise ValueError('invalid proposal')
    target=p.get('target',{}); path=target_path(home,target)
    if not target.get('profile'): raise ValueError('profile required')
    exists=path.exists()
    if exists and not path.is_file(): raise ValueError('target not a file')
    op=p.get('op',{}); creating='create' in op
    if creating:
        if target['kind']!='skill_md' or path.name!='SKILL.md' or exists or path.parent.exists(): raise ValueError('create target already exists')
    elif not exists and not (target['kind']=='user_memory' and 'memory_add' in op): raise ValueError('target missing')
    if exists and path.stat().st_size>1024*1024: raise ValueError('target exceeds size limit')
    before=path.read_bytes() if exists else b''
    if digest(before)!=p.get('baseline_digest'): raise ValueError('stale baseline')
    after=_change(p,before)
    if len(after.encode('utf-8'))>1024*1024: raise ValueError('result exceeds size limit')
    before_text=before.decode('utf-8')
    # Lexical preservation is deliberately conservative; it is not a semantic proof.
    if 'replace' in op or 'memory_replace' in op:
        sensitive=r'(?i)approval|approv(?:e|ed)|permission|consent|security|safety|credential|password|payment|external|destructive|승인|허가|동의|보안|안전|인증|비밀번호|결제|외부|삭제'
        after_sentences={x.strip() for x in re.split(r'(?<=[.!?])|[\r\n]+',after)}
        for sentence in re.split(r'(?<=[.!?])|[\r\n]+',before_text):
            if re.search(sensitive,sentence) and sentence.strip() not in after_sentences: raise ValueError('safeguard text must be preserved verbatim')
    if after==before_text: raise ValueError('no-op change')
    if 'replace' in op: inverse=op['replace']['new']
    elif 'memory_add' in op: inverse=op['memory_add']['text']
    elif 'memory_replace' in op: inverse=op['memory_replace']['text']
    else: inverse=None
    if inverse is not None and (not inverse or _occurrences(after,inverse)!=1): raise ValueError('inverse text must be unique')
    if not p.get('reason') or not p.get('evidence_ids') or not p.get('preserved_behaviors') or not p.get('eval_plan',{}).get('guardrail_case_ids'): raise ValueError('missing evidence or guardrails')
    if not isinstance(evidence,dict) or not isinstance(evidence.get('items'),list): raise ValueError('training evidence required')
    if not re.fullmatch(r'[0-9a-f]{64}',str(evidence.get('run_id',''))) or evidence.get('profile')!=target['profile']: raise ValueError('evidence run or profile mismatch')
    items=evidence['items']; by_id={x.get('id'):x for x in items if isinstance(x,dict)}
    if len(by_id)!=len(items) or any(i not in by_id or by_id[i].get('quoted') is not False for i in p['evidence_ids']): raise ValueError('unbound or quoted evidence')
    if any(i not in by_id for i in p.get('counterevidence_ids',[])): raise ValueError('unbound counterevidence')
    counts=evidence.get('counts',{}); denominator=p.get('denominator',{})
    if any(denominator.get(k)!=counts.get(k) or not isinstance(counts.get(k),int) or counts[k]<1 for k in ('sessions','user_turns')): raise ValueError('denominator mismatch')
    selected=[by_id[i] for i in p['evidence_ids']]
    scope=p.get('applicability',{}).get('scope','')
    if scope=='global':
        if len({i.get('session_id') for i in selected if i.get('session_id')})<2 or not any(i.get('category')=='explicit_preference' for i in selected): raise ValueError('global scope needs explicit preference and two sessions')
        if any(re.search(r'(?i)\b(?:this task|this request|only here|this time)\b|이번\s*(?:작업|요청)|이\s*작업에서만',i.get('text','')) for i in selected if i.get('category')=='explicit_preference'): raise ValueError('task-scoped preference cannot justify global scope')
    elif not (scope.startswith('task:') and len(scope)>5 or scope.startswith('skill:') and len(scope)>6): raise ValueError('invalid scope')
    if target['kind']=='user_memory' and scope!='global': raise ValueError('memory is global; task-scoped evidence cannot justify it')
    preservation=' '.join(p['preserved_behaviors']).lower()
    if scope=='global' or any(i.get('category')=='unnecessary_ask' for i in selected):
        required=(('destructive','삭제','파괴'),('external','외부'),('credential','자격 증명','인증 정보'),('payment','결제'),('approval','승인'))
        if not all(any(term in preservation for term in group) for group in required) or not re.search(r'\b(?:retain|keep|preserve|require|requires|approval for)\b|유지|필요|받',preservation): raise ValueError('preserve sensitive-action approvals explicitly')
    added=after if creating or 'memory_add' in op else (op.get('replace') or op.get('memory_replace')) .get('new',(op.get('memory_replace') or {}).get('text',''))
    if re.search(r"(?i)\b(?:do not|don't|dont|never|stop|avoid)\s+(?:ever\s+)?(?:ask|request|seek|require|obtain)\b|\b(?:no|skip|bypass|waive|disable|without)\s+(?:the\s+)?approval\b|승인(?:을|이|은|도)?\s*(?:없이|생략|묻지|필요\s*없)",added+' '+preservation): raise ValueError('approval weakening or unscoped never ask')
    result=dict(p); result['target']=dict(target,relpath='memories/USER.md') if target['kind']=='user_memory' else dict(target); result['baseline_exists']=exists; result['run_id']=evidence['run_id']; result['author_binding']=evidence.get('author_binding'); result['evidence_digest']=digest(canonical(evidence)); result['predicted_after_digest']=digest(after.encode()); result.pop('id',None); result['id']=digest(canonical(result))
    return result

def verify(home,p):
    expected=p.get('id'); unsigned=dict(p); unsigned.pop('id',None)
    if expected!=digest(canonical(unsigned)): raise ValueError('proposal digest mismatch')
    path=target_path(home,p['target']); exists=path.exists()
    if exists and not path.is_file(): raise ValueError('target not a file')
    if exists and path.stat().st_size>1024*1024: raise ValueError('target exceeds size limit')
    actual=digest(path.read_bytes()) if exists else digest(b'')
    status='observed_after' if exists and actual==p['predicted_after_digest'] else 'observed_before' if exists==p['baseline_exists'] and actual==p['baseline_digest'] and not ('create' in p['op'] and path.parent.exists()) else 'conflict'
    return {'status':status,'actual_digest':actual,'exists':exists,'observation':'disk digest only; native call and approval are unverified; memory prompt loading requires fresh-context check'}

def rollback_plan(home,p):
    observation=verify(home,p); conflict=observation['status']!='observed_after'
    if 'create' in p['op'] and not conflict:
        target=target_path(home,p['target']); conflict=any(x.name!='SKILL.md' for x in target.parent.iterdir())
    if conflict: return {'status':'rollback_conflict','inverse_preview':native_plan(p,inverse=True)}
    return {'status':'ready','call':native_plan(p,inverse=True),'note':'Live approval required; exact digest observed, not locked. Native deletion may archive.'}

def native_plan(p,inverse=False):
    op=p['op']; parts=PurePosixPath(p['target']['relpath']).parts
    if p['target']['kind']=='user_memory':
        if 'memory_add' in op:
            txt=op['memory_add']['text']; args={'target':'user','action':'remove','old_text':txt} if inverse else {'target':'user','action':'add','content':txt}
        else:
            old=op['memory_replace']['old_text']; new=op['memory_replace']['text']; args={'target':'user','action':'patch','old_text':new if inverse else old,'content':old if inverse else new}
        return {'tool':'memory','arguments':args,'expected_target':p['target'],'proposal_digest':p['id'],'note':'Confirm native target and profile; live approval and native gates required. USER.md is never written by this helper.'}
    if 'create' in op: call={'action':'delete','name':parts[1]} if inverse else {'action':'create','name':parts[1],'content':op['create']['new']}
    else:
        old=op['replace']['old']; new=op['replace']['new']; call={'action':'patch','name':parts[1],'old_string':new if inverse else old,'new_string':old if inverse else new}
        if len(parts)>3: call['file_path']='/'.join(parts[2:])
    return {'tool':'skill_manage','arguments':{'operations':[call]},'expected_target':p['target'],'proposal_digest':p['id'],'note':'Before calling, confirm the native resolved path and profile match the expected target; skills.create_dir or name resolution may differ. Live approval and native gates required.'}
