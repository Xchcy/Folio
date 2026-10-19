"""Verify that the delivered source starts and serves its complete frontend."""
from contextlib import redirect_stdout
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urljoin
from urllib.request import urlopen
from zipfile import ZipFile

from tools.package_demo import package


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        path = attrs.get('src') if tag in ('script', 'img') else attrs.get('href') if tag in ('link', 'image') else None
        if path and path.startswith('/'):
            self.paths.append(path)


class DeliveryTests(unittest.TestCase):
    def test_extracted_source_starts_and_serves_all_frontend_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            with redirect_stdout(io.StringIO()):
                package(temp)
            destination = Path(temp) / '源码交付验证'
            with ZipFile(Path(temp) / '演示源码.zip') as archive:
                self.assertFalse(any('/private/' in p or p.endswith(('.sqlite3', '.env')) for p in archive.namelist()))
                self.assertTrue(archive.read('work-memory-assistant/start.ps1').startswith(b'\xef\xbb\xbf'))
                archive.extractall(destination)
            root = destination / 'work-memory-assistant'
            env = {**os.environ, 'MEMORY_LOCAL_MODEL': ''}
            process = subprocess.Popen(
                [sys.executable, '-X', 'utf8', 'server.py', '--port', '0', '--data-dir', str(root / 'private')],
                cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            lines = queue.Queue()
            reader = threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True)
            reader.start()
            try:
                try:
                    startup = lines.get(timeout=30)
                except queue.Empty:
                    self.fail('Extracted delivery did not start within 30 seconds.')
                match = re.search(r'http://127\.0\.0\.1:\d+', startup)
                self.assertIsNotNone(match, startup)
                base = match.group(0)
                with urlopen(base, timeout=5) as response:
                    parser = Resources()
                    parser.feed(response.read().decode('utf-8'))
                pending, checked = list(parser.paths), set()
                while pending:
                    path = pending.pop()
                    if path in checked:
                        continue
                    checked.add(path)
                    with urlopen(base + path, timeout=5) as response:
                        payload = response.read()
                        expected = 'javascript' if path.endswith('.js') else 'image/png' if path.endswith('.png') else 'css'
                        self.assertIn(expected, response.headers['Content-Type'], path)
                    relative = 'web/' + path.lstrip('/')
                    self.assertEqual(payload, (root / relative).read_bytes(), path)
                    if path.endswith('.js'):
                        text = payload.decode('utf-8')
                        pending.extend(urljoin(path, ref) for ref in re.findall(r'^import .*? from [\'"](.+?)[\'"]', text, re.M))
                self.assertIn('/features/wechat.js', checked)
                self.assertIn('/styles/tokens.css', checked)
                self.assertIn('/assets/folio-logo.png', checked)
                self.assertIn('/intro.js', checked)
                with urlopen(base + '/api/state?mode=demo', timeout=5) as response:
                    self.assertGreater(len(json.load(response)['memories']), 0)
            finally:
                process.terminate()
                process.wait(timeout=10)
                reader.join(timeout=5)
                process.stdout.close()
