"""Package only reviewed public source. Never recursively include private data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = [
    '.editorconfig',
    'start.cmd',
    'tests/__init__.py',
    'tools/__init__.py',
    'tools/check.py',
    'tests/test_startup.py',
    'tests/test_delivery.py',
    'tests/test_capture_ui.js',
    'tests/ui_preview.py',
    'DEVELOPMENT.md',
    'UI_UPGRADE.md',
    'README.md',
    '交付说明.md',
    'start.ps1',
    '.gitignore',
    'engine.py',
    'server.py',
    'folio.py',
    'demo.py',
    'wechat.py',
    'wechat_bridge.py',
    'tests/test_memory.py',
    'tests/test_context.py',
    'tests/test_ownership.py',
    'tests/test_remote_model.py',
    'tests/test_api.py',
    'extraction.py',
    'local_model.py',
    'remote_model.py',
    'tools/package_demo.py',
    'tools/build_release.py',
    'tools/verify_release.py',
    'capture.py',
    'capture_ocr.ps1',
    'tests/test_capture.py',
    'tests/test_extension.js',
    'web/capture-ui.js',
    'web/capture.css',
    'extension/manifest.json',
    'extension/background.js',
    'extension/capture.html',
    'extension/capture.css',
    'extension/capture.js',
    'extension/README.md',
    'extension/icon128.png',
    'web/index.html',
    'web/app.js',
    'web/motion.js',
    'web/intro.js',
    'web/papers.js',
    'paper_summaries.py',
    'tests/test_paper_summaries.py',
    'tests/test_papers.js',
    'tests/test_ruler.js',
    'web/assets/folio-logo.png',
    'extension/folio-logo.png',
    'tests/test_intro.js',
    'tests/test_motion.js',
    'web/todos.js',
    'web/ui.js',
    'web/ui.css',
    'web/home.js',
    'web/home.css',
    'tests/test_home.js',
    'tests/test_ui.js',
    'tests/test_todos.js',
    'wechat_entry.py',
    'requirements.txt',
    'tests/test_wechat.py',
    'vendor/NOTICE.md',
    'vendor/LICENSE-wechat-cli',
    'vendor/LICENSE-wechat-reference',
    'vendor/README-wechat-cli.md',
]

PUBLIC_FILES += sorted(p.relative_to(ROOT).as_posix() for folder in ('web/features', 'web/styles') for p in (ROOT/folder).glob('*') if p.is_file() and p.suffix in ('.js', '.css'))
PUBLIC_FILES += ['web/workspace.js']


def package(output_dir=ROOT / 'release'):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / '演示源码.zip'
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for relative in PUBLIC_FILES:
            archive.write(ROOT / relative, 'work-memory-assistant/' + relative)
        for path in sorted((ROOT / 'vendor' / 'wechat_cli').rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.c'):
                archive.write(path, 'work-memory-assistant/' + path.relative_to(ROOT).as_posix())
    with ZipFile(output_dir / 'Folio随手记扩展.zip', 'w', ZIP_DEFLATED) as archive:
        for relative in PUBLIC_FILES:
            if relative.startswith('extension/'):
                archive.write(ROOT / relative, relative)
    print('扩展加载包：Folio随手记扩展.zip')
    print('演示源码.zip：仅包含合成案例和公开源码，不含私有记录或授权名单。')


if __name__ == '__main__':
    package()
