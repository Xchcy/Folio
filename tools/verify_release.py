"""Exercise the actual outer ZIP with disposable data and no real WeChat access."""
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        path = attrs.get('src') if tag in ('script', 'img') else attrs.get('href') if tag in ('link', 'image') else None
        if path and path.startswith('/'):
            self.paths.append(path)


def verify(archive_path):
    archive_path = Path(archive_path).resolve()
    with tempfile.TemporaryDirectory(prefix='folio-delivery-') as temporary:
        root = Path(temporary)
        with ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            members = archive.namelist()
            assert all(not any(part in ('private', 'data', '.venv', '.git') for part in Path(name).parts) for name in members)
            folder = Path(members[0]).parts[0]
            source_bytes = archive.read(f'{folder}/Folio-公开源码.zip')
            assert archive.read(f'{folder}/README.md').startswith(b'# Folio')
            archive.extractall(root)
        with ZipFile(BytesIO(source_bytes)) as source:
            assert source.testzip() is None
            names = source.namelist()
            assert 'work-memory-assistant/folio.py' in names
            assert 'work-memory-assistant/交付说明.md' in names
            assert all(not any(part in ('private', 'data', '.venv', '.git') for part in Path(name).parts) for name in names)
        app = root / folder / 'Folio-Windows'
        exe = app / 'Folio.exe'
        assert exe.is_file() and (app / '_internal' / 'web' / 'index.html').is_file()
        cli = subprocess.run([exe, '--wechat-cli', '--help'], cwd=root, capture_output=True, timeout=30)
        assert cli.returncode == 0 and b'init' in cli.stdout, cli.stderr
        process = subprocess.Popen([exe, '--no-browser', '--port', '0'], cwd=root,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            line = process.stdout.readline().decode('utf-8', errors='replace')
            address = re.search(r'http://127\.0\.0\.1:\d+', line)
            assert address, line
            base = address.group(0)
            with urlopen(base, timeout=10) as response:
                page = response.read().decode('utf-8')
            resources = Resources()
            resources.feed(page)
            for path in resources.paths:
                with urlopen(base + path, timeout=10) as response:
                    assert response.status == 200 and response.read(), path
            with urlopen(base + '/api/state?mode=demo', timeout=10) as response:
                assert json.load(response)['memories']
            with urlopen(base + '/api/state?mode=private', timeout=10) as response:
                assert not json.load(response)['messages']
            assert (app / 'data' / 'private.sqlite3').is_file()
            assert not (root / 'private').exists()
        finally:
            process.terminate()
            process.wait(timeout=10)
            process.stdout.close()
        print(f'Verified outer ZIP, source ZIP, bundled CLI, {len(resources.paths)} page assets, demo API and isolated data.')


if __name__ == '__main__':
    verify(sys.argv[1])
