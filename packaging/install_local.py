#!/usr/bin/env python3
"""Install a complete local skill into an explicitly selected disposable home."""
import argparse, hashlib, io, json, marshal, os, pathlib, shutil, stat, sys, importlib.util, struct, types
ROOT=pathlib.Path(__file__).resolve().parents[1]
def check(path):
    path=pathlib.Path(os.path.abspath(path)); cur=pathlib.Path(path.anchor)
    for part in path.parts[1:]:
        cur/=part
        try:
            if stat.S_ISLNK(cur.lstat().st_mode): raise ValueError('symlink path refused')
        except FileNotFoundError: pass
    return path
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
# Caches are untrusted input. Bound reads and recursive comparisons; never execute them.
MAX_CACHE_BYTES=8*1024*1024
MAX_CONSTANT_DEPTH=100

def same_constant(actual,expected,depth=0):
    if depth>MAX_CONSTANT_DEPTH or type(actual) is not type(expected): return False
    if isinstance(expected,types.CodeType):
        fields=('co_argcount','co_posonlyargcount','co_kwonlyargcount','co_nlocals','co_stacksize','co_flags','co_code','co_names','co_varnames','co_freevars','co_cellvars','co_name','co_qualname','co_filename','co_firstlineno','co_linetable','co_exceptiontable')
        for name in fields:
            if getattr(actual,name,None)!=getattr(expected,name,None): return False
        return same_constant(actual.co_consts,expected.co_consts,depth+1)
    if isinstance(expected,tuple):
        return len(actual)==len(expected) and all(same_constant(a,b,depth+1) for a,b in zip(actual,expected))
    if isinstance(expected,frozenset):
        remaining=list(actual)
        for value in expected:
            match=next((i for i,item in enumerate(remaining) if same_constant(item,value,depth+1)),None)
            if match is None: return False
            remaining.pop(match)
        return not remaining
    if isinstance(expected,float): return struct.pack('!d',actual)==struct.pack('!d',expected)
    if isinstance(expected,complex): return struct.pack('!dd',actual.real,actual.imag)==struct.pack('!dd',expected.real,expected.imag)
    return actual==expected

def generated_cache(source,cache):
    # The caller has already verified that the manifest-owned source is unchanged.
    try:
        if cache!=pathlib.Path(importlib.util.cache_from_source(str(source))): return False
        check(cache)
        fd=os.open(cache,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode): return False
            raw=f.read(MAX_CACHE_BYTES+1)
        if len(raw)<17 or len(raw)>MAX_CACHE_BYTES or raw[:4]!=importlib.util.MAGIC_NUMBER: return False
        data=source.read_bytes(); flags=struct.unpack('<I',raw[4:8])[0]
        if flags==0:
            st=source.stat(); header=struct.pack('<II',int(st.st_mtime)&0xffffffff,len(data)&0xffffffff)
        elif flags in (1,3): header=importlib.util.source_hash(data)
        else: return False
        if raw[8:16]!=header: return False
        expected=compile(data,str(source),'exec',dont_inherit=True)
        stream=io.BytesIO(raw[16:]); actual=marshal.load(stream)
        if stream.read(1): return False
        return isinstance(actual,types.CodeType) and same_constant(actual,expected)
    except (OSError,ValueError,TypeError,SyntaxError,EOFError,OverflowError,RecursionError,MemoryError): return False

def main():
    p=argparse.ArgumentParser(); p.add_argument('action',choices=('install','uninstall')); p.add_argument('--hermes-home',required=True); a=p.parse_args()
    try:
        home=check(a.hermes_home)
        if not home.is_dir(): raise ValueError('home must already exist')
        target=check(home/'skills/hermes-fit'); state=check(home/'hermes-fit'); manifest=check(state/'install-manifest.json')
        if a.action=='install':
            if target.exists() or manifest.exists(): raise ValueError('installation collision')
            source=ROOT/'skills/hermes-fit'; files=sorted(x for x in source.rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix!='.pyc')
            if not (source/'SKILL.md').is_file(): raise ValueError('missing payload')
            for path in files:
                if path.is_symlink(): raise ValueError('symlink in payload')
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True); state.mkdir(mode=0o700,exist_ok=True); target.mkdir(mode=0o700)
            records={}
            for path in files:
                rel=path.relative_to(source); dest=target/rel; dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as out: out.write(path.read_bytes())
                records[str(rel)]=h(dest)
            fd=os.open(manifest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: json.dump(records,f,sort_keys=True)
            print('installed locally; no schedule created')
        else:
            if not manifest.is_file(): raise ValueError('installation manifest missing')
            monitor=check(home/'scripts/hermes_fit_monitor.py'); schedules=check(state/'schedules')
            if monitor.exists() or (schedules.exists() and any(schedules.iterdir())):
                raise ValueError('schedule or monitor remains; use schedule-teardown-plan, native remove/list, then schedule-cleanup before uninstall')
            records=json.loads(manifest.read_text()); preserved=[]
            if not isinstance(records,dict): raise ValueError('invalid manifest')
            for rel,expected in records.items():
                if not isinstance(rel,str) or pathlib.PurePosixPath(rel).is_absolute() or '..' in pathlib.PurePosixPath(rel).parts: raise ValueError('invalid manifest')
                try: path=check(target/rel)
                except ValueError: continue
                if path.is_file() and h(path)==expected and path.suffix=='.py':
                    cache=pathlib.Path(importlib.util.cache_from_source(str(path)))
                    if cache.exists() and generated_cache(path,cache): cache.unlink()
            for rel,expected in records.items():
                try: path=check(target/rel)
                except ValueError:
                    preserved.append(rel); continue
                if path.is_file() and h(path)==expected: path.unlink()
                elif path.exists(): preserved.append(rel)
            for directory in sorted((x for x in target.rglob('*') if x.is_dir() and not x.is_symlink()),key=lambda x:len(x.parts),reverse=True):
                try: directory.rmdir()
                except OSError: pass
            if target.exists():
                for path in target.rglob('*'):
                    if path.is_file() or path.is_symlink():
                        rel=str(path.relative_to(target))
                        if rel not in preserved: preserved.append(rel)
            try: target.rmdir()
            except OSError: pass
            manifest.unlink(); print('preserved edited or unknown files:',json.dumps(sorted(preserved)))
        return 0
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc: print('error:',exc,file=sys.stderr); return 2
if __name__=='__main__': sys.exit(main())
