import importlib.util, importlib._bootstrap_external, io, marshal, pathlib, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fit_installer',ROOT/'packaging/install_local.py')
installer=importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)

class CacheOwnership(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); root=pathlib.Path(self.temp.name).resolve(); self.source=root/'owned.py'; self.source.write_text('def f():\n    return 12\n')
  self.cache=pathlib.Path(importlib.util.cache_from_source(str(self.source))); self.cache.parent.mkdir()
  self.code=compile(self.source.read_bytes(),str(self.source),'exec',dont_inherit=True); st=self.source.stat()
  self.header=bytes(importlib._bootstrap_external._code_to_timestamp_pyc(self.code,int(st.st_mtime),st.st_size)[:16])
 def tearDown(self): self.temp.cleanup()
 def write(self,code,version=2): self.cache.write_bytes(self.header+marshal.dumps(code,version))
 def test_equivalent_alternate_marshal_version_is_owned(self):
  self.write(self.code); self.assertNotEqual(self.cache.read_bytes(),bytes(importlib._bootstrap_external._code_to_timestamp_pyc(self.code,int(self.source.stat().st_mtime),self.source.stat().st_size)))
  self.assertTrue(installer.generated_cache(self.source,self.cache))
 def test_bad_header_trailing_wrong_code_and_nested_filename_are_preserved(self):
  self.write(self.code); valid=self.cache.read_bytes()
  for raw in (b'BAD!'+valid[4:],valid[:8]+b'\x00'*8+valid[16:],valid+b'extra',self.header+marshal.dumps(compile('x=4',str(self.source),'exec'),2)):
   self.cache.write_bytes(raw); self.assertFalse(installer.generated_cache(self.source,self.cache))
  nested=next(c for c in self.code.co_consts if hasattr(c,'co_code')); changed=nested.replace(co_filename='other.py'); constants=tuple(changed if c is nested else c for c in self.code.co_consts)
  self.write(self.code.replace(co_consts=constants)); self.assertFalse(installer.generated_cache(self.source,self.cache))
 def test_hash_header_and_unrecognized_flags(self):
  data=self.source.read_bytes(); self.cache.write_bytes(bytes(importlib._bootstrap_external._code_to_hash_pyc(self.code,importlib.util.source_hash(data),checked=True))[:16]+marshal.dumps(self.code,2))
  self.assertTrue(installer.generated_cache(self.source,self.cache)); bad=bytearray(self.cache.read_bytes()); bad[8]^=1; self.cache.write_bytes(bad); self.assertFalse(installer.generated_cache(self.source,self.cache))
  bad=bytearray(self.header+marshal.dumps(self.code,2)); bad[4]=5; self.cache.write_bytes(bad); self.assertFalse(installer.generated_cache(self.source,self.cache))
 def test_wrong_path_and_oversized_data_are_preserved(self):
  self.write(self.code); other=self.cache.with_name('other.pyc'); other.write_bytes(self.cache.read_bytes())
  self.assertFalse(installer.generated_cache(self.source,other))
  self.cache.write_bytes(self.header+b'x'*(installer.MAX_CACHE_BYTES+1)); self.assertFalse(installer.generated_cache(self.source,self.cache))
 def test_install_help_alternate_cache_uninstall_reinstall(self):
  import subprocess, sys
  with tempfile.TemporaryDirectory() as tmp:
   home=pathlib.Path(tmp).resolve()
   def install(action): return subprocess.run([sys.executable,'-I',str(ROOT/'packaging/install_local.py'),action,'--hermes-home',str(home)],capture_output=True,text=True)
   first=install('install'); self.assertEqual(first.returncode,0,first.stderr)
   cli=home/'skills/hermes-fit/scripts/hermes_fit.py'; help_run=subprocess.run([sys.executable,'-I',str(cli),'--help'],capture_output=True,text=True); self.assertEqual(help_run.returncode,0,help_run.stderr)
   caches=list((cli.parent/'hfit/__pycache__').glob('*.pyc')); self.assertGreater(len(caches),0)
   different=0
   for cache in caches:
    raw=cache.read_bytes(); original=marshal.loads(raw[16:]); source=pathlib.Path(importlib.util.source_from_cache(str(cache)))
    fresh=compile(source.read_bytes(),str(source),'exec',dont_inherit=True)
    self.assertEqual(original,fresh); self.assertEqual(original.co_filename,fresh.co_filename)
    replacement=None
    for code in (original,fresh):
     for version in range(marshal.version+1):
      try: candidate=marshal.dumps(code,version)
      except (ValueError,TypeError): continue
      stream=io.BytesIO(candidate); restored=marshal.load(stream)
      self.assertEqual(restored,original); self.assertEqual(restored.co_filename,original.co_filename); self.assertEqual(stream.read(),b'')
      if candidate!=raw[16:]: replacement=candidate; break
     if replacement is not None: break
    if replacement is not None:
     cache.write_bytes(raw[:16]+replacement); self.assertEqual(cache.read_bytes()[:16],raw[:16]); different+=1
   self.assertGreater(different,0,'no distinct supported serialization was generated')
   removed=install('uninstall'); self.assertEqual(removed.returncode,0,removed.stderr); self.assertFalse((home/'skills/hermes-fit').exists(),removed.stdout)
   again=install('install'); self.assertEqual(again.returncode,0,again.stderr)
 def test_edited_manifest_source_keeps_its_cache(self):
  import subprocess, sys
  with tempfile.TemporaryDirectory() as tmp:
   home=pathlib.Path(tmp).resolve(); command=[sys.executable,'-I',str(ROOT/'packaging/install_local.py')]
   self.assertEqual(subprocess.run(command+['install','--hermes-home',str(home)],capture_output=True).returncode,0)
   cli=home/'skills/hermes-fit/scripts/hermes_fit.py'; subprocess.run([sys.executable,'-I',str(cli),'--help'],capture_output=True,check=True)
   source=cli.parent/'hfit/core.py'; cache=pathlib.Path(importlib.util.cache_from_source(str(source))); self.assertTrue(cache.exists())
   source.write_bytes(source.read_bytes()+b'\n# edited\n')
   result=subprocess.run(command+['uninstall','--hermes-home',str(home)],capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
   self.assertTrue(source.exists()); self.assertTrue(cache.exists()); self.assertIn(cache.name,result.stdout)
