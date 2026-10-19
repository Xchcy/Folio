"""Build an allowlisted Windows bundle and source archive without private data."""
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from package_demo import package


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'release'


def main():
    if sys.platform != 'win32':
        raise SystemExit('Windows bundle must be built on Windows.')
    RELEASE.mkdir(exist_ok=True)
    target = RELEASE / ('Folio-交付-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    target.mkdir()
    with tempfile.TemporaryDirectory(prefix='folio-build-', dir=RELEASE) as temp:
        stage = Path(temp)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                   '--onedir', '--console', '--name', 'Folio',
                   '--paths', str(ROOT / 'vendor'),
                   '--add-data', f'{ROOT / "web"};web',
                   '--add-data', f'{ROOT / "capture_ocr.ps1"};.',
                   '--hidden-import', 'wechat_cli.keys.scanner_windows',
                   '--distpath', str(stage / 'dist'),
                   '--workpath', str(stage / 'build'),
                   '--specpath', str(stage), str(ROOT / 'folio.py')]
        subprocess.run(command, cwd=ROOT, check=True)
        shutil.copytree(stage / 'dist' / 'Folio', target / 'Folio-Windows')
        package(stage)
        shutil.copy2(stage / '演示源码.zip', target / 'Folio-公开源码.zip')
        shutil.copy2(stage / 'Folio随手记扩展.zip', target / 'Folio-随手记扩展.zip')
    shutil.copy2(ROOT / '交付说明.md', target / 'README.md')
    (target / 'Folio-Windows' / 'README.md').write_bytes((ROOT / '交付说明.md').read_bytes())
    (target / 'Folio-Windows' / '启动 Folio.cmd').write_bytes(
        b'@echo off\r\ncd /d "%~dp0"\r\n"Folio.exe"\r\nif errorlevel 1 pause\r\n')
    (target / 'Folio-Windows' / '初始化微信.cmd').write_bytes(
        b'@echo off\r\ncd /d "%~dp0"\r\n"Folio.exe" --wechat-cli init\r\npause\r\n')
    archive = target.with_suffix('.zip')
    with ZipFile(archive, 'w', ZIP_DEFLATED) as output:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                output.write(path, target.name + '/' + path.relative_to(target).as_posix())
    print(archive)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
