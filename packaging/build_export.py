#!/usr/bin/env python3
"""Build a deterministic source archive with a SHA-256 manifest."""
import hashlib, pathlib, sys, zipfile
root=pathlib.Path(__file__).resolve().parents[1]
allowed=('README.md','README.ko.md','LICENSE','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','docs','skills','examples','tests','packaging','.github')
files=[]
for name in allowed:
    base=root/name
    if not base.exists(): continue
    for p in ([base] if base.is_file() else base.rglob('*')):
        if p.is_symlink(): raise SystemExit('symlink forbidden: '+str(p.relative_to(root)))
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'):
            files.append(p)
files.sort(key=lambda p:p.relative_to(root).as_posix())
manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n' for p in files)
with zipfile.ZipFile(sys.argv[1],'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for path,data in [(p.relative_to(root).as_posix(),p.read_bytes()) for p in files]+[('MANIFEST.sha256',manifest.encode())]:
        info=zipfile.ZipInfo(path,(1980,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16
        z.writestr(info,data)
print('archive files:',len(files),'manifest sha256:',hashlib.sha256(manifest.encode()).hexdigest())
