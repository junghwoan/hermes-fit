import hashlib, pathlib, subprocess, sys, tempfile, unittest, zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
class DistributionTests(unittest.TestCase):
    def run_cmd(self,*args): return subprocess.run([sys.executable,*map(str,args)],capture_output=True,text=True)
    def test_install_collision_and_preserve_edit(self):
        with tempfile.TemporaryDirectory() as d:
            home=pathlib.Path(d).resolve()/'home'; home.mkdir(); script=ROOT/'packaging/install_local.py'
            self.assertEqual(self.run_cmd(script,'install','--hermes-home',home).returncode,0)
            self.assertNotEqual(self.run_cmd(script,'install','--hermes-home',home).returncode,0)
            target=home/'skills/hermes-fit/SKILL.md'; target.write_text('user changed')
            self.assertEqual(self.run_cmd(script,'uninstall','--hermes-home',home).returncode,0)
            self.assertEqual(target.read_text(),'user changed')
    def test_repro_export_and_install(self):
        with tempfile.TemporaryDirectory() as d:
            d=pathlib.Path(d).resolve(); script=ROOT/'packaging/build_export.py'; a=d/'a.zip'; b=d/'b.zip'
            self.assertEqual(self.run_cmd(script,a).returncode,0); self.assertEqual(self.run_cmd(script,b).returncode,0)
            self.assertEqual(hashlib.sha256(a.read_bytes()).digest(),hashlib.sha256(b.read_bytes()).digest())
            checked=self.run_cmd(ROOT/'packaging/check_package.py',a); self.assertEqual(checked.returncode,0,checked.stderr)
            with zipfile.ZipFile(a) as z: z.extractall(d/'export')
            home=d/'home'; home.mkdir()
            self.assertEqual(self.run_cmd(d/'export/packaging/install_local.py','install','--hermes-home',home).returncode,0)
            p=subprocess.run([sys.executable,'-I',str(home/'skills/hermes-fit/scripts/hermes_fit.py'),'--help'],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
    def test_install_parent_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve(); (root/'real').mkdir(); (root/'link').symlink_to(root/'real',target_is_directory=True)
            p=self.run_cmd(ROOT/'packaging/install_local.py','install','--hermes-home',root/'link')
            self.assertNotEqual(p.returncode,0)

if __name__=='__main__': unittest.main()
