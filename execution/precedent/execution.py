"""Trusted patch application and fail-closed macOS test execution."""
import json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path,PurePosixPath


def git(repo,*args):
    p=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(p.stderr.strip())
    return p.stdout if args and args[0]=='show' else p.stdout.strip()

def safe_path(root,name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '.git' in path.parts or not path.parts:raise ValueError('Unsafe patch path')
    dest=root.joinpath(*path.parts)
    if not dest.resolve().is_relative_to(root.resolve()):raise ValueError('Symlink escape')
    if any(p.is_symlink() for p in [dest,*dest.parents] if p!=root.parent):raise ValueError('Symlink not editable')
    return dest

def apply_files(root,files,allowed):
    if not isinstance(files,dict) or not files:raise ValueError('Expected nonempty files object')
    if not set(files)<=set(allowed):raise ValueError('Patch exceeds explicitly allowed files')
    prepared=[]
    for name,body in files.items():
        if not isinstance(body,str) or len(body.encode())>100000:raise ValueError('Candidate file quota')
        target=safe_path(root,name)
        if name.endswith('.py'):compile(body,name,'exec')
        prepared.append((target,body))
    for target,body in prepared:target.parent.mkdir(parents=True,exist_ok=True);target.write_text(body)

def run_tests(root,test_paths,timeout=25):
    if sys.platform!='darwin' or not Path('/usr/bin/sandbox-exec').exists():raise RuntimeError('No enforced test isolation backend')
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='precedent-test-') as temporary:
        stage=Path(temporary).resolve()
        script=stage/'runner.py'
        script.write_text('''import sys,unittest,runpy,resource
resource.setrlimit(resource.RLIMIT_CPU,(12,12))
resource.setrlimit(resource.RLIMIT_FSIZE,(2000000,2000000))
resource.setrlimit(resource.RLIMIT_NOFILE,(48,48))
sys.path.insert(0,sys.argv[1])
suite=unittest.TestSuite()
for path in sys.argv[2:]:
 ns=runpy.run_path(path,run_name='frozen_tests')
 for value in ns.values():
  if isinstance(value,type) and issubclass(value,unittest.TestCase) and value is not unittest.TestCase:
   suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(value))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.testsRun>0 and result.wasSuccessful() else 1)
''')
        # Resolve the running Python's base runtime; a venv executable alone
        # does not grant its framework library or standard library access.
        reads=[str(root.resolve()),str(stage),str(Path(sys.base_prefix).resolve()),'/System','/usr/lib',str(Path(sys.executable).resolve())]+[str(Path(p).resolve()) for p in test_paths]
        policy='(version 1)(deny default)(allow process-exec)(allow sysctl-read)(allow file-read-metadata)(allow file-read* (literal "/") (literal "/dev/null") (literal "/dev/urandom") '+' '.join('(subpath '+json.dumps(p)+')' for p in reads)+')'
        argv=['/usr/bin/sandbox-exec','-p',policy,sys.executable,'-I','-S',str(script),str(root.resolve()),*[str(Path(p).resolve()) for p in test_paths]]
        with tempfile.TemporaryFile() as output:
            p=subprocess.Popen(argv,cwd=stage,env={'PATH':'/usr/bin:/bin','HOME':str(stage),'TMPDIR':str(stage),'LANG':'C.UTF-8'},stdout=output,stderr=output,close_fds=True,start_new_session=True)
            reason=None
            while p.poll() is None:
                if time.monotonic()-started>timeout:reason='timeout'
                if os.fstat(output.fileno()).st_size>1000000:reason='output quota'
                if reason:os.killpg(p.pid,signal.SIGKILL);break
                time.sleep(.02)
            p.wait();output.seek(0);text=output.read(100000).decode(errors='replace')
        return {'passed':p.returncode==0 and reason is None,'exit':p.returncode,'reason':reason,'seconds':time.monotonic()-started,'output':text,'backend':'macos-seatbelt'}
