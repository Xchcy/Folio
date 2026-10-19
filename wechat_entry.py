"""Bundled CLI entry point; no sibling source checkout is required."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from wechat_cli.main import cli
if __name__ == '__main__':
    cli()
