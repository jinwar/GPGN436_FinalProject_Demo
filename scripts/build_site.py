"""Build a static site using the authoritative Python solver sources."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '_site'
if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(ROOT / 'web', OUT)
for name in ('acoustic', 'aquifer'):
    shutil.copy2(ROOT / name / f'{name}.py', OUT / f'{name}.py')
(OUT / '.nojekyll').touch()
print(f'Built {OUT}')
