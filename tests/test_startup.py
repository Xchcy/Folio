"""Check the launcher using the same parser as Windows PowerShell users."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def test_busy_port_returns_failure_with_a_readable_message(self):
        import server
        output = io.StringIO()
        with patch('sys.argv', ['server.py', '--port', '8775']), \
             patch.object(server, 'DATA_ROOT'), patch.object(server, 'store'), \
             patch.object(server.remote_model, 'load_config'), \
             patch.object(server.capture, 'resume_pending'), \
             patch.object(server, 'ThreadingHTTPServer', side_effect=OSError('address in use')), \
             redirect_stdout(output):
            self.assertEqual(server.main(), 1)
        self.assertIn('8775', output.getvalue())
        self.assertIn('--port', output.getvalue())

    def test_windows_powershell_can_identify_utf8(self):
        for path in ROOT.glob('*.ps1'):
            with self.subTest(script=path.name):
                self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'),
                                'Save PowerShell scripts as UTF-8 with BOM for Chinese text.')

    @unittest.skipUnless(shutil.which('powershell.exe'), 'Windows PowerShell is unavailable')
    def test_windows_powershell_parses_launcher(self):
        command = '''$errors=$null; $tokens=$null;
        [System.Management.Automation.Language.Parser]::ParseFile(
            $env:STARTUP_SCRIPT_PATH,[ref]$tokens,[ref]$errors) > $null;
        if ($errors.Count) { $errors | ForEach-Object { $_.Message }; exit 1 }'''
        for path in ROOT.glob('*.ps1'):
            with self.subTest(script=path.name):
                result = subprocess.run(
                    ['powershell.exe', '-NoProfile', '-Command', command],
                    env={**os.environ, 'STARTUP_SCRIPT_PATH': str(path)},
                    capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
