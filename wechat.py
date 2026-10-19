"""Allowlisted local CLI reader. Captures private output; never prints chats."""
import hashlib
import json
import os
import re
import subprocess
import sys
import secrets
import threading
import time
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUTHORIZATION_ROOT = ROOT / 'private'
CONTACT_ALIASES_PATH = ROOT/'private'/'contact-aliases.json'
CLI_PYTHON = Path(sys.executable)
CLI_ENTRY = ROOT / 'wechat_entry.py'
PREVIEWS = {}
CHAT_CHOICES = {}
LOCK = threading.RLock()


def bridge(request):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    command = [str(CLI_PYTHON), '--wechat-bridge'] if getattr(sys, 'frozen', False) else [str(CLI_PYTHON), '-X', 'utf8', str(ROOT / 'wechat_bridge.py')]
    p = subprocess.run(command,
        input=json.dumps(request).encode('utf-8'), capture_output=True, timeout=120, env=env)
    if p.returncode:
        init_step = '双击“初始化微信.cmd”' if getattr(sys, 'frozen', False) else '在项目终端运行 python wechat_entry.py init'
        raise ValueError(f'微信读取失败，请确认电脑版微信已登录，并{init_step}完成初始化。')
    return json.loads(p.stdout.decode('utf-8-sig'))


def cleanup():
    now = time.monotonic()
    for cache, capacity in ((PREVIEWS, 100), (CHAT_CHOICES, 1000)):
        for key in list(cache):
            if cache[key]['expires'] < now:
                del cache[key]
        while len(cache) > capacity:
            del cache[next(iter(cache))]


def contact_aliases():
    """Human-confirmed identities only; names and IDs stay in private storage."""
    path=CONTACT_ALIASES_PATH
    if not path.exists():
        return []
    try:
        people=json.loads(path.read_text('utf-8'))['people']
        if not isinstance(people,list):
            raise ValueError()
        for person in people:
            if not isinstance(person,dict) or not isinstance(person.get('name'),str) or not person['name'].strip() or not isinstance(person.get('accounts'),list):
                raise ValueError()
            for account in person['accounts']:
                if not isinstance(account,dict) or not isinstance(account.get('username'),str) or not account['username'].strip() or account.get('role') not in ('current','previous'):
                    raise ValueError()
        return people
    except (ValueError,KeyError,TypeError):
        raise ValueError('本机联系人别名配置无效，请检查 private/contact-aliases.json') from None


def search_chats(query='', offset=0):
    if not isinstance(query, str) or len(query) > 100 or type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError('会话搜索参数无效')
    people=contact_aliases()
    aliases={a['username']:(p['name'],a['role']) for p in people for a in p['accounts']}
    matched=[p for p in people if not query.strip() or normalize(query) in normalize(p['name'])]
    extra=[a['username'] for role in ('current','previous') for p in matched for a in p['accounts'] if a['role']==role]
    result = bridge({'action':'contacts','query':query.strip(),'offset':offset,'extra_usernames':extra})
    with LOCK:
        cleanup()
        chats = []
        for chat in result['chats']:
            chat=dict(chat)
            original_name=chat['name']
            if chat['username'] in aliases:
                person,role=aliases[chat['username']]
                chat['name']=person+('（当前账号）' if role=='current' else '（旧账号）')
            ticket = secrets.token_urlsafe(24)
            CHAT_CHOICES[ticket] = {**chat, 'expires':time.monotonic()+3600}
            chats.append({'ticket':ticket,'name':chat['name'],'is_group':chat['is_group'],
                          'nickname':chat.get('nickname',''),'account_hint':'…'+chat['username'][-6:],
                          'wechat_name':original_name if chat['username'] in aliases else ''})
    return {'chats':chats, 'has_more':result['total']>offset+len(chats), 'next_offset':offset+len(chats)}


def preview_messages(ticket, offset=0, filters=None, page=None):
    if not isinstance(ticket, str) or type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError('消息分页参数无效')
    if page is not None:
        if type(page) is not int or not 1 <= page <= 50000:
            raise ValueError('页码须为 1 到 50000 的整数')
        offset = (page-1)*20
    filters = filters or {}
    if not isinstance(filters, dict):
        raise ValueError('筛选参数无效')
    for key in ('query','sender','start','end'):
        if not isinstance(filters.get(key, ''), str) or len(filters.get(key, '')) > 200:
            raise ValueError('筛选参数无效')
    for key in ('start','end'):
        if filters.get(key):
            datetime.strptime(filters[key], '%Y-%m-%d')
    if filters.get('start') and filters.get('end') and filters['start'] > filters['end']:
        raise ValueError('开始日期不能晚于结束日期')
    if type(filters.get('mine', False)) is not bool:
        raise ValueError('发送者筛选无效')
    with LOCK:
        cleanup()
        chat = CHAT_CHOICES.get(ticket)
        if not chat:
            raise ValueError('会话选择已过期，请重新搜索')
    request={'action':'history','username':chat['username'],'offset':offset,'limit':20,'filters':filters,'exact_total':True}
    result = bridge(request)
    if result.get('username') != chat['username']:
        raise ValueError('会话身份核对失败')
    if result.get('failures'):
        raise ValueError(f"有 {len(result['failures'])} 项消息来源未能读取，无法确认完整性。请检查微信初始化后重试；本页未导入。")
    matched_total = result.get('matched_total',len(result['messages']))
    if type(matched_total) is not int or matched_total < 0:
        raise ValueError('无法确认消息总数，请重新读取')
    total_pages=(matched_total+19)//20
    actual_page=(offset//20)+1 if total_pages else 0
    if actual_page > total_pages and total_pages:
        actual_page=total_pages
        result=bridge({**request,'offset':(actual_page-1)*20})
        if result.get('username') != chat['username'] or result.get('failures'):
            raise ValueError('尾页读取失败，请重新选择会话')
    preview = secrets.token_urlsafe(24)
    with LOCK:
        PREVIEWS[preview] = {'messages':result['messages'], 'chat':chat['name'],
            'username':chat['username'], 'expires':time.monotonic()+3600}
        cleanup()
    return {**result,'username':None,'preview':preview,'chat':chat['name'],
            'page':actual_page,'page_size':20,'total_pages':total_pages}


def import_selected(memory, selections, data_root):
    if not isinstance(selections, list) or not 1 <= len(selections) <= 50:
        raise ValueError('请选择要导入的消息（最多 50 页）')
    messages, seen = [], set()
    with LOCK:
        cleanup()
        for selection in selections:
            if not isinstance(selection, dict) or not isinstance(selection.get('preview'), str):
                raise ValueError('消息选择无效')
            batch = PREVIEWS.get(selection['preview'])
            ids = selection.get('ids')
            if not batch or not isinstance(ids, list) or not ids or len(ids) > 100 or not all(isinstance(i,str) for i in ids):
                raise ValueError('消息预览已过期或选择无效，请重新读取')
            originals = {m['id']:m for m in batch['messages']}
            if any(mid not in originals for mid in ids):
                raise ValueError('只能导入已预览的消息')
            for mid in ids:
                if mid not in seen:
                    messages.append({**originals[mid], 'chat':batch['chat'], 'topic':batch['chat']})
                    seen.add(mid)
    batch_name = 'selected-' + secrets.token_hex(12) + '.json'
    for i, message in enumerate(messages):
        message['source'] = f'{batch_name}#messages/{i}'
    # Only selected messages are persisted, including original locators/quotes.
    data_root = Path(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / batch_name).write_text(json.dumps({'messages':messages},ensure_ascii=False,indent=2), 'utf-8')
    added = memory.ingest(sorted(messages, key=lambda m:(m['timestamp'],m['id'])))
    return {'selected':len(messages), 'added':added, 'duplicates':len(messages)-added}


def normalize(s):
    return unicodedata.normalize('NFKC', s).strip().casefold()


def run_cli(args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    # The packaged child process uses the same executable and UTF-8 pipe output.
    command = [str(CLI_PYTHON), '--wechat-cli'] if getattr(sys, 'frozen', False) else [str(CLI_PYTHON), '-X', 'utf8', str(CLI_ENTRY)]
    p = subprocess.run([*command, *args, '--format', 'json'], capture_output=True, env=env, timeout=120)
    if p.returncode:
        # CLI error output can contain identities; keep it private.
        log = AUTHORIZATION_ROOT / 'sync-error.txt'
        log.parent.mkdir(exist_ok=True)
        log.write_bytes(p.stderr)
        raise ValueError(f'本地微信读取失败。详细错误已保存在 {log}。')
    try:
        output = p.stdout.decode('utf-8-sig')
    except UnicodeDecodeError:
        output = p.stdout.decode('gb18030')
    return json.loads(output)


def _write_authorization_json(path,value):
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=AUTHORIZATION_ROOT,delete=False) as stream:
            temporary=stream.name;json.dump(value,stream,ensure_ascii=False,indent=2)
        os.replace(temporary,path)
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)


def revoke_chats(names):
    if not isinstance(names,list) or not names or not all(isinstance(n,str) and n.strip() for n in names):
        raise ValueError('请选择要取消授权的会话')
    with LOCK:
        granted=authorized_chats()['chats']
        current=[c['name'] for c in granted]
        removed=set(names)&set(current)
        if removed:
            mapping=json.loads((AUTHORIZATION_ROOT/'authorized-chats.json').read_text('utf-8')) if (AUTHORIZATION_ROOT/'authorized-chats.json').exists() else {}
            usernames={mapping[n] for n in removed if mapping.get(n)}
            _write_authorization_json(AUTHORIZATION_ROOT/'allowed-names.json',[n for n in current if n not in removed])
            # Discard pending previews/identity tickets for the revoked accounts.
            # Saved messages and memories are independent of these read grants.
            for cache in (PREVIEWS,CHAT_CHOICES):
                for ticket,item in list(cache.items()):
                    if item.get('username') in usernames:del cache[ticket]
    return {'revoked':len(removed),'note':f'已取消 {len(removed)} 个会话的授权。已导入的原文和记忆保留；重新读取需再次选择授权。'}


def authorize_chats(tickets):
    """Grant only identities explicitly selected from a live WeChat listing.

    Contact tickets, never client-supplied names or usernames, own selection.
    No history is read while granting access.
    """
    if not isinstance(tickets,list) or not tickets or len(tickets)>50 or not all(isinstance(t,str) for t in tickets):
        raise ValueError('请选择1至50个微信会话')
    with LOCK:
        cleanup()
        choices=[CHAT_CHOICES.get(t) for t in dict.fromkeys(tickets)]
        if any(not c or c['expires']<=time.monotonic() for c in choices):
            raise ValueError('会话选择已过期，请重新搜索并选择')
        AUTHORIZATION_ROOT.mkdir(parents=True,exist_ok=True)
        names_path=AUTHORIZATION_ROOT/'allowed-names.json'
        mapping_path=AUTHORIZATION_ROOT/'authorized-chats.json'
        names=json.loads(names_path.read_text('utf-8')) if names_path.exists() else []
        mapping=json.loads(mapping_path.read_text('utf-8')) if mapping_path.exists() else {}
        if not isinstance(names,list) or not all(isinstance(n,str) for n in names) or not isinstance(mapping,dict) or not all(isinstance(v,str) for v in mapping.values()):
            raise ValueError('原授权配置格式无效，请核对后重试')
        selected=[]
        for choice in choices:
            username=choice['username']
            name=next((n for n in names if mapping.get(n)==username),None)
            if name is None:
                name=choice['name']
                if name in names and mapping.get(name)!=username:
                    name=choice['name']+'（账号尾号 '+username[-6:]+'）'
                suffix=1
                while name in names and mapping.get(name)!=username:
                    suffix+=1;name=choice['name']+f'（独立账号{suffix}）'
                if name not in names:names.append(name)
                mapping[name]=username
            selected.append(name)
        # Commit identities before grants: an interrupted write can leave an
        # unused mapping, but cannot grant a name with an unrelated identity.
        for path,value in ((mapping_path,mapping),(names_path,names)):
            _write_authorization_json(path,value)
    return {'selected':list(dict.fromkeys(selected)),'note':'已保存勾选会话的授权，尚未读取聊天消息。'}


def authorized_chats():
    """List existing grants without reading contacts or any message history."""
    path = AUTHORIZATION_ROOT / 'allowed-names.json'
    if not path.exists():
        return {'chats':[],'note':'尚未配置已授权会话。可继续使用从微信选择导入。'}
    names = json.loads(path.read_text('utf-8'))
    if not isinstance(names,list) or not all(isinstance(n,str) and n.strip() for n in names):
        raise ValueError('授权会话名单格式无效')
    mapping_path = AUTHORIZATION_ROOT / 'authorized-chats.json'
    mapping = json.loads(mapping_path.read_text('utf-8')) if mapping_path.exists() else {}
    return {'chats':[{'name':n,'account_hint':'…'+mapping[n][-6:] if isinstance(mapping.get(n),str) else '',
                     'resolved':bool(mapping.get(n))} for n in dict.fromkeys(names)],
            'note':'只读取勾选的已授权会话，每个会话最近最多400条。尚未核对身份的会话会先唯一匹配，重名时跳过。'}


def sync(memory, pages=4, page_size=100, selected=None):
    listed = authorized_chats()
    allowed_names = [c['name'] for c in listed['chats']]
    if selected is not None:
        if not isinstance(selected,list) or not selected or not all(isinstance(n,str) and n in allowed_names for n in selected):
            raise ValueError('请勾选至少一个已有授权的会话')
        allowed_names = list(dict.fromkeys(selected))
    if not allowed_names:
        raise ValueError('尚未配置授权会话名单。演示空间可直接使用合成案例。')
    private = Path(memory.path).parent
    private.mkdir(exist_ok=True)
    mapping_path = AUTHORIZATION_ROOT / 'authorized-chats.json'
    mapping = json.loads(mapping_path.read_text('utf-8')) if mapping_path.exists() else {}
    counts = []
    for name in allowed_names:
        if name not in mapping:
            candidates = run_cli(['contacts', '--query', name, '--limit', '1000'])
            exact = [c for c in candidates if any(normalize(c.get(k, '')) == normalize(name) for k in ('nick_name', 'remark'))]
            ids = {c['username'] for c in exact}
            if len(ids) != 1:
                counts.append({'name': name, 'status': '需确认：没有唯一同名会话', 'matches': len(ids), 'added': 0, 'complete': False})
                continue
            mapping[name] = next(iter(ids))
            mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), 'utf-8')
        messages = []
        complete, window_limited = True, False
        for page in range(pages):
            data = bridge({'action':'history', 'username':mapping[name], 'limit':page_size, 'offset':page*page_size})
            if data.get('username') != mapping[name]:
                raise ValueError('返回的会话身份与授权会话不一致')
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            batch = hashlib.sha256(mapping[name].encode()).hexdigest()[:12] + '-' + stamp + '.json'
            (private / batch).write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
            if data.get('failures'):
                complete = False
                break
            for index, message in enumerate(data.get('messages', [])):
                messages.append({**message, 'chat':name, 'topic':name, 'source':f'{batch}#messages/{index}'})
            if len(data.get('messages', [])) < page_size:
                break
        else:
            window_limited = data.get('has_more', True)
        ids = list({m['id'] for m in messages})
        query = 'SELECT count(*) FROM memories WHERE message_id IN (' + ','.join('?' for _ in ids) + ')'
        with memory.connect() as db:
            before = db.execute(query, ids).fetchone()[0] if ids else 0
        added = memory.ingest(sorted(messages, key=lambda m:(m['timestamp'],m['id'])))
        with memory.connect() as db:
            candidates = (db.execute(query, ids).fetchone()[0] if ids else 0) - before
        counts.append({'name': name, 'status': '已刷新；新增候选待确认，已有采用记录保留' if complete else '部分读取失败，已导入此前成功读取的页；未完整刷新',
                       'complete':complete, 'window_limited':window_limited, 'fetched':len(messages), 'added':added,
                       'duplicates':len(messages)-added, 'candidates':candidates,
                       'latest':max((m['timestamp'] for m in messages),default=None)})
    return {'chats': counts, 'limit': pages * page_size, 'refreshed_at':datetime.now().astimezone().isoformat(),
            'note': '本次为最近消息窗口。按会话、数据库、表和本地消息编号去重；原始批次保留引用信息与原始类型。'}
