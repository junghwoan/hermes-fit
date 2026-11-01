#!/usr/bin/env python3
"""Check an export's manifest, paths, required files, and common leak patterns."""
import hashlib, pathlib, re, sys, zipfile
required={'README.md','README.ko.md','LICENSE','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','docs/PLAN.md','docs/COMPATIBILITY.md','skills/hermes-fit/SKILL.md','skills/hermes-fit/scripts/hermes_fit.py','skills/hermes-fit/scripts/hfit/core.py','examples/demo.py','packaging/install_local.py','packaging/build_export.py'}
try:
    with zipfile.ZipFile(sys.argv[1]) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or not required<=set(names) or 'MANIFEST.sha256' not in names: raise ValueError('missing or duplicate entries')
        entries={}
        for line in z.read('MANIFEST.sha256').decode().splitlines():
            h,name=line.split('  ',1)
            if name in entries or not re.fullmatch(r'[0-9a-f]{64}',h): raise ValueError('invalid manifest')
            entries[name]=h
        if set(entries)!=set(names)-{'MANIFEST.sha256'}: raise ValueError('manifest coverage mismatch')
        for name,h in entries.items():
            path=pathlib.PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or any(x in path.parts for x in ('.git','__pycache__','evidence','node_modules')) or name.endswith(('.pyc','.log','.db')): raise ValueError('forbidden path: '+name)
            data=z.read(name)
            if hashlib.sha256(data).hexdigest()!=h: raise ValueError('digest mismatch: '+name)
            if re.search(rb'/ho'+rb'me/(?:vkworker|ubuntu)/|/Us'+rb'ers/[^/\s]+/',data): raise ValueError('machine path: '+name)
            if re.search(rb'\b(?:ghp_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b',data): raise ValueError('credential-shaped material: '+name)
    print('package checks passed:',len(entries),'files; heuristic leak scan only')
except (OSError,ValueError,KeyError,IndexError,zipfile.BadZipFile,UnicodeError) as exc:
    print('package check failed:',exc,file=sys.stderr); sys.exit(1)
