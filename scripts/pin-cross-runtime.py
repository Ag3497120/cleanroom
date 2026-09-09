"""Test the locally compiled Cross runtime, then pin its exact bytes."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1]
binary=root/'cross/build/cross'
before=hashlib.sha256(binary.read_bytes()).hexdigest()
subprocess.run(['ctest','--test-dir',str(binary.parent),'--output-on-failure'],check=True)
after=hashlib.sha256(binary.read_bytes()).hexdigest()
if before!=after:raise SystemExit('Runtime changed during validation')
target=root/'core/src/verantyx/cross-build.json'
target.write_text(json.dumps({'runtime_sha256':after})+'\n')
print('Registered the tested local Cross build.')
