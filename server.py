import argparse
import json
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from demo import demo_messages, context_demo_messages, ownership_demo_messages
from engine import Memory
from wechat import sync
import wechat
import remote_model
import capture
import paper_summaries

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / 'private'
DEFAULT_DATA_ROOT = Path(sys.executable).resolve().parent / 'data' if getattr(sys, 'frozen', False) else DATA_ROOT
WEB_FILES = (
    'app.js',
    'todos.js',
    'capture-ui.js',
    'capture.css',
    'ui.js',
    'ui.css',
    'home.css',
    'home.js',
    'workspace.js',
    'motion.js',
    'intro.js',
    'papers.js',
    'styles/papers.css',
    'styles/brand.css',
    'assets/folio-logo.png',
    'styles/motion.css',
    'features/ruler.js',
    'styles/workspace-focus.css',
    'features/models.js',
    'features/todos.js',
    'features/navigation.js',
    'features/authorization.js',
    'features/wechat.js',
    'styles/tokens.css',
    'styles/base.css',
    'styles/shell.css',
    'styles/workspace.css',
    'styles/wechat.css',
    'styles/library.css',
    'styles/todo-widget.css',
)
TOKEN = secrets.token_urlsafe(32)
SYNC_LOCK = threading.Lock()
JOBS = {}
JOBS_LOCK = threading.Lock()


def store(mode):
    if mode not in ('demo', 'private'):
        raise ValueError('数据空间无效')
    memory = Memory(DATA_ROOT / (mode + '.sqlite3'))
    if mode == 'demo':
        memory.ingest(demo_messages(), curated=True)
        memory.ingest(context_demo_messages())
        memory.ingest(ownership_demo_messages())
    return memory


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, value, content_type='application/json; charset=utf-8'):
        payload = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {'error': '仅允许本机访问'})
        parts = urlsplit(self.path)
        try:
            if parts.path == '/api/state':
                mode = parse_qs(parts.query).get('mode', ['demo'])[0]
                data = store(mode).state()
                data.update(mode=mode, token=TOKEN)
                data['paper_ai_model']=paper_summaries.settings(DATA_ROOT)['model']
                return self.send(200, data)
            if parts.path == '/api/paper-models':
                return self.send(200,paper_summaries.available(DATA_ROOT))
            if parts.path == '/api/job':
                job_id = parse_qs(parts.query).get('id', [''])[0]
                with JOBS_LOCK:
                    result = JOBS.get(job_id)
                return self.send(200, result) if result else self.send(404, {'error': '任务不存在'})
            if parts.path == '/api/capture-connection':
                return self.send(200, {'token': TOKEN, 'name': 'Folio', 'version': 1})
            if parts.path == '/api/captures':
                return self.send(200, {'items': capture.list_items(store('private'), deleted=parse_qs(parts.query).get('deleted', ['0'])[0]=='1')})
            if parts.path == '/api/capture-item':
                return self.send(200, capture.record(capture.get(store('private'), parse_qs(parts.query).get('id', [''])[0])))
            if parts.path == '/api/capture-image':
                item = capture.get(store('private'), parse_qs(parts.query).get('id', [''])[0])
                if not item['image']:
                    return self.send(404, {'error': '原图尚未保存'})
                return self.send(200, item['image'], item['mime'])
            if parts.path == '/api/model-config':
                return self.send(200, remote_model.settings())
            files = {'/': 'index.html', **{'/'+name: name for name in WEB_FILES}}
            if parts.path not in files:
                return self.send(404, {'error': '页面不存在'})
            file = ROOT / 'web' / files[parts.path]
            ct = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css', 'png': 'image/png'}[file.suffix[1:]]
            self.send(200, file.read_bytes(), ct if file.suffix == '.png' else ct + '; charset=utf-8')
        except ValueError as e:
            self.send(400, {'error': str(e)})

    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-Memory-Token') != TOKEN:
            return self.send(403, {'error': '请刷新本机页面后重试'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            route = urlsplit(self.path).path
            limit = 6_000_000 if route in ('/api/capture', '/api/capture-attach') else 2_000_000
            if size > limit or size < 1:
                raise ValueError('输入大小不支持')
            data = json.loads(self.rfile.read(size))
            memory = store(data.get('mode', 'demo'))
            route = urlsplit(self.path).path
            if route == '/api/capture':
                memory = store('private')
                result = capture.save(memory, data)
                if result['saved']:
                    capture.enqueue(memory, result['id'])
            elif route in ('/api/capture-delete', '/api/capture-restore'):
                result = capture.set_deleted(store('private'), data.get('ids'), deleted=route=='/api/capture-delete')
            elif route == '/api/capture-edit':
                result = capture.edit(store('private'), data['id'], data.get('changes', {}))
            elif route == '/api/capture-promote':
                result = capture.promote(store('private'), data['id'])
            elif route == '/api/capture-retry':
                memory = store('private')
                item = capture.get(memory, data['id'])
                if item['deleted_at']:
                    raise ValueError('记录已移入最近删除，请先恢复')
                if item['manual']:
                    raise ValueError('已人工修改，自动重整不会覆盖；可直接转为待办')
                capture.enqueue(memory, data['id'])
                result = {'queued': True}
            elif route == '/api/capture-attach':
                result = capture.attach(store('private'), data['id'], data.get('image_data', ''))
            elif route == '/api/model-config':
                result = remote_model.configure(data.get('base_url'), data.get('model'), data.get('api_key', ''), data.get('clear', False))
            elif route == '/api/paper-model':
                result = paper_summaries.configure(DATA_ROOT,data.get('model'))
            elif route == '/api/model-test':
                result = remote_model.test_connection()
            elif route == '/api/ask':
                q = data.get('question', '')
                if not isinstance(q, str) or len(q) > 1000:
                    raise ValueError('问题最多 1000 字')
                result = memory.ask(q, data.get('topic'), data.get('as_of'))
            elif route == '/api/review':
                result = memory.review(data['id'], data['changes'], data.get('note', ''))
            elif route == '/api/task-date-change':
                result = memory.apply_task_date_change(data['id'])
            elif route == '/api/group':
                result = memory.group_topic(data.get('source_topic'), data.get('target_topic'))
            elif route in ('/api/analyze', '/api/model-analyze', '/api/paper-summaries'):
                if route=='/api/paper-summaries' and (not isinstance(data.get('topic',''),str) or data.get('view','timeline') not in ('timeline','tasks','waiting','completed','pending','messages','reviews')):
                    raise ValueError('请选择有效事项和视图')
                if route == '/api/model-analyze' and data.get('mode') != 'demo':
                    raise ValueError('外部模型仅用于合成演示空间')
                if not SYNC_LOCK.acquire(blocking=False):
                    raise ValueError('整理或读取正在进行，请稍候')
                job_id = secrets.token_urlsafe(16)
                with JOBS_LOCK:
                    # 只保留有限个完成任务，内容均为计数。
                    for old in list(JOBS)[:-19]:
                        if JOBS[old]['status'] != 'running':
                            del JOBS[old]
                    JOBS[job_id] = {'status': 'running'}
                def analyze_job():
                    try:
                        if route=='/api/paper-summaries':
                            result=paper_summaries.generate(memory,DATA_ROOT,data.get('topic',''),data.get('view','timeline'))
                        else:
                            result=memory.analyze_demo_model() if route=='/api/model-analyze' else memory.analyze()
                        report = {'status':'completed','result':result}
                    except ValueError as error:
                        report = {'status': 'failed', 'error': str(error)}
                    except Exception:
                        report = {'status': 'failed', 'error': '本机整理失败，请稍后重试'}
                    finally:
                        SYNC_LOCK.release()
                    with JOBS_LOCK:
                        JOBS[job_id] = report
                threading.Thread(target=analyze_job, daemon=True).start()
                result = {'job_id': job_id}
            elif route == '/api/import':
                if not isinstance(data.get('messages'), list):
                    raise ValueError('请选择 JSON 消息数组')
                result = {'added': memory.ingest(data['messages'])}
            elif route in ('/api/wechat/chats', '/api/wechat/authorize', '/api/wechat/revoke', '/api/wechat/authorized', '/api/wechat/messages', '/api/wechat/import'):
                if data.get('mode') != 'private':
                    raise ValueError('微信记录只可导入本机私有空间')
                if not SYNC_LOCK.acquire(blocking=False):
                    raise ValueError('读取或整理正在进行，请稍候')
                try:
                    if route.endswith('/revoke'):
                        result = wechat.revoke_chats(data.get('chats'))
                    elif route.endswith('/authorize'):
                        result = wechat.authorize_chats(data.get('tickets'))
                    elif route.endswith('/authorized'):
                        result = wechat.authorized_chats()
                    elif route.endswith('/chats'):
                        result = wechat.search_chats(data.get('query', ''), data.get('offset', 0))
                    elif route.endswith('/messages'):
                        result = wechat.preview_messages(data.get('ticket'), data.get('offset', 0), data.get('filters'),data.get('page'))
                    else:
                        result = wechat.import_selected(memory, data.get('selections'), DATA_ROOT)
                finally:
                    SYNC_LOCK.release()
            elif route == '/api/sync':
                if data.get('mode') != 'private':
                    raise ValueError('微信记录只可导入本机私有空间')
                if not SYNC_LOCK.acquire(blocking=False):
                    raise ValueError('读取正在进行，请稍候')
                try:
                    if not isinstance(data.get('chats'),list) or not data['chats']:
                        raise ValueError('请先选择要读取的已授权会话')
                    result = sync(memory,selected=data['chats'])
                finally:
                    SYNC_LOCK.release()
            else:
                return self.send(404, {'error': '操作不存在'})
            self.send(200, result)
        except (ValueError, KeyError, TypeError) as e:
            self.send(400, {'error': str(e)})
        except Exception:
            self.send(500, {'error': '本地操作失败，请检查本机服务或读取日志'})


def main():
    global DATA_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA_ROOT, help='本机数据目录')
    parser.add_argument('--open-browser', action='store_true', help='启动后打开本机页面')
    args = parser.parse_args()
    DATA_ROOT = args.data_dir.resolve()
    if getattr(sys, 'frozen', False):
        wechat.AUTHORIZATION_ROOT = DATA_ROOT
        wechat.CONTACT_ALIASES_PATH = DATA_ROOT / 'contact-aliases.json'
    remote_model.load_config(DATA_ROOT / 'model-config.json')
    store('demo')
    capture.resume_pending(store('private'))
    try:
        http = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError:
        print(f'无法使用端口 {args.port}。请关闭已有服务，或用 --port 指定其他端口。', flush=True)
        return 1
    print(f'Folio · 个人工作记忆助手：http://127.0.0.1:{http.server_port}（仅本机）', flush=True)
    if args.open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f'http://127.0.0.1:{http.server_port}/#home')).start()
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
