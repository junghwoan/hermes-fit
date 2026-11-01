#!/usr/bin/env python3
"""Fingerprint a selected export. First call establishes baseline; no network calls."""
import argparse, fcntl, hashlib, os, pathlib, stat, sys, tempfile

def safe(path,missing=False):
    path=pathlib.Path(os.path.abspath(path)); cur=pathlib.Path(path.anchor)
    for part in path.parts[1:]:
        cur/=part
        try:
            if stat.S_ISLNK(cur.lstat().st_mode): raise ValueError('symlink path refused')
        except FileNotFoundError:
            if not missing: raise
    return path

def main():
    p=argparse.ArgumentParser(); p.add_argument('export'); p.add_argument('--state'); args=p.parse_args()
    try:
        export=safe(args.export)
        if not export.is_file(): raise ValueError('export must be a regular file')
        line='hermes-fit export sha256='+hashlib.sha256(export.read_bytes()).hexdigest()+'\n'
        if args.state:
            state=safe(args.state,True); state.mkdir(mode=0o700,parents=True,exist_ok=True); safe(state)
            lock=safe(state/'lock',True); fd=os.open(lock,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'r+') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX)
                pending=safe(state/'pending',True); previous=safe(state/'fingerprint',True)
                if pending.exists() and previous.is_file(): line=previous.read_text()
                else:
                    fd,tmp=tempfile.mkstemp(dir=state,prefix='.fingerprint-')
                    try:
                        with os.fdopen(fd,'w') as out: out.write(line); out.flush(); os.fsync(out.fileno())
                        os.replace(tmp,previous)
                    finally:
                        if os.path.exists(tmp): os.unlink(tmp)
        sys.stdout.write(line); return 0
    except (OSError,ValueError) as exc: print('error:',exc,file=sys.stderr); return 2
if __name__=='__main__': sys.exit(main())
