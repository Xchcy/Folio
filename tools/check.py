"""Run all project checks from any working directory, without touching user data."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    node = shutil.which('node')
    if not node:
        raise SystemExit('Node.js is required for development checks, but not for starting the app.')
    temp = ROOT / 'private' / 'test-temp'
    temp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'TEMP': str(temp), 'TMP': str(temp), 'MEMORY_LOCAL_MODEL': ''}
    commands = [[sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
                [node, '--test', *[str(p) for p in sorted((ROOT / 'tests').glob('test_*.js'))]]]
    commands += [[node, '--check', str(p)] for folder in ('web', 'extension')
                 for p in sorted((ROOT / folder).rglob('*.js'))]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    print('All tests, JavaScript syntax and isolated delivery packaging passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
