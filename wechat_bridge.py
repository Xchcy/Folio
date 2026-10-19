"""Read-only adapter for bundled CLI; uses existing local configuration.

Web requests resolve exact conversation identities before calling this bridge.
Never serializes keys, initializes CLI, or reads process memory.
"""
import hashlib
import heapq
import json
import re
import sqlite3
import sys
from contextlib import closing, ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
from wechat_cli.core.context import AppContext
from wechat_cli.core.contacts import get_contact_names
from wechat_cli.core.messages import (_load_name2id_maps, _resolve_sender_label,
    _format_message_text, decompress_content, _is_safe_msg_table_name)


def history(username, limit, offset, filters=None, exact_total=False):
    filters = filters or {}
    filtered=bool(filters.get('query') or filters.get('sender') or filters.get('mine'))
    app = AppContext()
    names = get_contact_names(app.cache, app.decrypted_dir)
    # Resolve by the exact contact identity. Discovery must not silently omit
    # failed shards (the upstream resolver suppresses those errors).
    ctx = {'username':username, 'display_name':names.get(username,username),
           'is_group':'@chatroom' in username}
    table_name = 'Msg_' + hashlib.md5(username.encode()).hexdigest()
    candidates = {k.replace('\\','/') for k in app.msg_db_keys}
    candidates.update(p.relative_to(app.db_dir).as_posix()
        for p in (Path(app.db_dir) / 'message').glob('*.db')
        if re.fullmatch(r'(?:biz_)?message_\d+\.db',p.name))
    entries, failures, sources = [], [], []
    if not candidates:
        failures.append('NoMessageDatabase')
    scanned = matched = total = in_range = 0
    dates = []
    clauses, params = [], []
    for key, op in [('start', '>='), ('end', '<')]:
        if filters.get(key):
            date = datetime.fromisoformat(filters[key]).replace(tzinfo=timezone(timedelta(hours=8)))
            if key == 'end':
                date += timedelta(days=1)
            clauses.append('create_time ' + op + ' ?')
            params.append(int(date.timestamp()))
    where = 'WHERE ' + ' AND '.join(clauses) if clauses else ''
    heap = []
    def push(row, index):
        if row:
            table = sources[index]['table']
            heapq.heappush(heap,(-row[2],table['database'], -row[0], index,row))
    with ExitStack() as stack:
        for rel in sorted(candidates):
            try:
                path = app.cache.get(rel)
                if not path:
                    raise ValueError('消息数据库不可读')
                uri = Path(path).resolve().as_uri() + '?mode=ro'
                db = stack.enter_context(closing(sqlite3.connect(uri,uri=True)))
                if not db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',table_name)).fetchone():
                    continue
                table = {'database':Path(path).name,'table_name':table_name,'is_group':ctx['is_group']}
                ids = _load_name2id_maps(db)
                if not _is_safe_msg_table_name(table_name):
                    raise ValueError('消息表名无效')
                count, first, last = db.execute(f'SELECT count(*),min(create_time),max(create_time) FROM [{table_name}]').fetchone()
                total += count
                if count:
                    dates.extend([first,last])
                in_range += db.execute(f'SELECT count(*) FROM [{table_name}] {where}',params).fetchone()[0]
                cursor = db.execute(f'''SELECT local_id, local_type, create_time,
                    real_sender_id, message_content, WCDB_CT_message_content
                    FROM [{table_name}] {where}
                    ORDER BY create_time DESC, local_id DESC''',params)
                index = len(sources)
                sources.append({'table':table,'ids':ids,'cursor':cursor})
                push(cursor.fetchone(),index)
            except Exception as e:
                failures.append(type(e).__name__)
        # Merge sorted shard cursors, filtering before pagination. Memory use
        # is bounded by the number of shards plus one result page.
        while heap:
            _,_,_,index,row = heapq.heappop(heap)
            source = sources[index]
            table,ids = source['table'],source['ids']
            scanned += 1
            if not filtered:
                # Deep page navigation does not require parsing every earlier
                # message. Count and skip cursor rows before formatting.
                matched += 1
                if matched <= offset:
                    push(source['cursor'].fetchone(),index)
                    continue
                if matched > offset + limit:
                    break
            try:
                local_id, local_type, ts, sender_id, content, ct = row
                raw = decompress_content(content, ct)
                raw = raw if isinstance(raw, str) else '(无法解压)'
                sender, text = _format_message_text(local_id, local_type, raw, table['is_group'],
                    username, ctx['display_name'], names, app.display_name_fn)
                label = _resolve_sender_label(sender_id, sender, table['is_group'], username,
                    ctx['display_name'], names, ids, app.display_name_fn)
                label = '我' if label == 'me' else label or '未知发送者'
                passes = ((not filters.get('query') or filters['query'].casefold() in text.casefold()) and
                    (not filters.get('sender') or filters['sender'].casefold() in label.casefold()) and
                    (not filters.get('mine') or label == '我'))
                if not passes:
                    push(source['cursor'].fetchone(),index)
                    continue
                if filtered:
                    matched += 1
                if matched <= offset:
                    push(source['cursor'].fetchone(),index)
                    continue
                if matched > offset + limit:
                    if not (exact_total and filtered):
                        break
                    push(source['cursor'].fetchone(),index)
                    continue
                identity = [username, table['database'], table['table_name'], str(local_id)]
                mid = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
                reference = None
                if 'refermsg' in raw:
                    # Preserve quoted XML privately. Quoted content is never
                    # independently attributed to the current sender.
                    import xml.etree.ElementTree as ET
                    try:
                        ref = ET.fromstring(raw).find('.//refermsg')
                        if ref is not None:
                            reference = {k: ref.findtext(k, '') for k in ('svrid', 'displayname', 'content')}
                    except ET.ParseError:
                        pass
                entries.append(dict(id=mid, chat=ctx['display_name'], sender=label,
                    timestamp=datetime.fromtimestamp(ts, timezone(timedelta(hours=8))).isoformat(), text=text,
                    original_timestamp=ts,
                    type='text' if (local_type & 0xffffffff) == 1 else 'reference' if reference else 'media',
                    reference=reference, locator={'database':table['database'],'table':table['table_name'],'local_id':local_id},
                    source='wechat-local', raw_type=local_type))
            except Exception as e:
                failures.append(type(e).__name__)
            push(source['cursor'].fetchone(),index)
    has_more = matched > offset + limit
    page=entries
    zone=timezone(timedelta(hours=8))
    return {'username':username, 'messages':page, 'failures':failures,
            'has_more':has_more, 'next_offset':offset+len(page), 'scanned':scanned,
            'total':total,'in_range':in_range,'matched_total':None if has_more and filtered and not exact_total else matched if filtered else in_range,
            'date_start':datetime.fromtimestamp(min(dates),zone).isoformat() if dates else None,
            'date_end':datetime.fromtimestamp(max(dates),zone).isoformat() if dates else None,
            'database_count':len(candidates),'table_count':len(sources),'complete':not failures}


def main():
    request = json.load(sys.stdin)
    if request['action'] == 'contacts':
        from wechat_cli.core.contacts import get_contact_full
        app = AppContext()
        contacts = get_contact_full(app.cache, app.decrypted_dir)
        q = request.get('query', '').casefold()
        extra=request.get('extra_usernames',[])
        result = {'chats':[{'username':c['username'], 'name':c.get('remark') or c.get('nick_name') or c['username'],
            'nickname':c.get('nick_name',''),
            'is_group':'@chatroom' in c['username']} for c in contacts
            if not q or c['username'] in extra or any(q in str(c.get(k, '')).casefold() for k in ('remark','nick_name','username'))]}
        priorities={username:i for i,username in enumerate(extra)}
        if priorities:
            result['chats'].sort(key=lambda c:priorities.get(c['username'],len(priorities)))
        result['total'] = len(result['chats'])
        result['chats'] = result['chats'][request.get('offset', 0):request.get('offset', 0)+100]
    else:
        result = history(request['username'], request['limit'], request['offset'], request.get('filters'),request.get('exact_total',False))
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
