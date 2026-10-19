"""Windows bundle entry point; child modes keep WeChat processing local."""
import os
import sys
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))


def main():
    if sys.argv[1:2] == ['--wechat-bridge']:
        import wechat_bridge
        wechat_bridge.main()
        return 0
    if sys.argv[1:2] == ['--wechat-cli']:
        from wechat_cli.main import cli
        sys.argv.pop(1)
        cli()
        return 0
    if getattr(sys, 'frozen', False):
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        if '--no-browser' in sys.argv:
            sys.argv.remove('--no-browser')
        else:
            sys.argv.append('--open-browser')
    from server import main as serve
    return serve()


if __name__ == '__main__':
    raise SystemExit(main())
