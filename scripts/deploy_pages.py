"""Build and publish the static site to GitHub Pages' gh-pages branch.

Requires Git and an authenticated GitHub CLI (gh). Only the temporary checkout
is cleared; source files and local changes in the main checkout are untouched.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REMOTE = 'https://github.com/jinwar/GPGN436_FinalProject_Demo.git'


def git(*args, cwd):
    return subprocess.run(['git', '-c', 'credential.helper=',
                           '-c', 'credential.helper=!gh auth git-credential', *args],
                          cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


subprocess.run([sys.executable, str(ROOT / 'scripts/build_site.py')], check=True)
with tempfile.TemporaryDirectory(prefix='gpgn-pages-') as temp:
    checkout = Path(temp)
    exists = git('ls-remote', '--heads', REMOTE, 'gh-pages', cwd=ROOT)
    if exists:
        git('clone', '--depth', '1', '--branch', 'gh-pages', REMOTE, '.', cwd=checkout)
    else:
        git('init', '-b', 'gh-pages', cwd=checkout)
        git('remote', 'add', 'origin', REMOTE, cwd=checkout)
    for child in checkout.iterdir():
        if child.name != '.git':
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    shutil.copytree(ROOT / '_site', checkout, dirs_exist_ok=True)
    git('add', '--all', cwd=checkout)
    if git('status', '--porcelain', cwd=checkout):
        revision = git('rev-parse', '--short', 'HEAD', cwd=ROOT)
        git('commit', '-m', f'Publish browser demos from {revision}', cwd=checkout)
        git('push', 'origin', 'gh-pages', cwd=checkout)
    print('Published https://jinwar.github.io/GPGN436_FinalProject_Demo/')
