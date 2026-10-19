"""Offline evidence-first memory engine. No external service is contacted."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from extraction import resolve_date, classify, extract_events, extract_task_date_change, lexical_score, EVENT_LABELS, task_traits, TASK_ROLES, CERTAINTIES
from local_model import extract_with_model, model_name
import paper_summaries

KINDS = {'decision': '决定', 'fact': '事实', 'task': '承诺', 'question': '待确认'}
STATES = {'pending', 'confirmed', 'completed', 'dismissed'}


class Memory:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, chat TEXT, sender TEXT, timestamp TEXT,
                text TEXT, type TEXT, topic TEXT, source TEXT);
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, message_id TEXT REFERENCES messages(id),
                topic TEXT, kind TEXT, title TEXT, status TEXT DEFAULT 'pending',
                due TEXT, reason TEXT, field TEXT, value TEXT, supersedes TEXT);
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY, memory_id TEXT, timestamp TEXT,
                before_json TEXT, after_json TEXT, note TEXT);
            CREATE TABLE IF NOT EXISTS paper_summaries (
                entity_key TEXT PRIMARY KEY, fingerprint TEXT, summary TEXT, model TEXT, created_at TEXT);
            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(memories)')}
            extras = {'evidence_ids': "TEXT DEFAULT '[]'", 'event': "TEXT DEFAULT ''",
                'condition': "TEXT DEFAULT ''", 'subject': "TEXT DEFAULT ''",
                'topic_suggestion': "TEXT DEFAULT ''", 'relation_suggestion': "TEXT DEFAULT ''",
                'extraction_source': "TEXT DEFAULT 'legacy'", 'date_kind': "TEXT DEFAULT 'associated'",
                'task_role': "TEXT DEFAULT ''", 'certainty': "TEXT DEFAULT ''"}
            for name, definition in extras.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE memories ADD COLUMN {name} {definition}')
            message_columns = {r[1] for r in db.execute('PRAGMA table_info(messages)')}
            if 'analyzed_version' not in message_columns:
                db.execute('ALTER TABLE messages ADD COLUMN analyzed_version INTEGER DEFAULT 0')
            db.execute('CREATE INDEX IF NOT EXISTS message_context ON messages(chat,timestamp,id)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, messages, curated=False):
        inserted = 0
        with self.connect() as db:
            for m in messages:
                required = ('chat', 'sender', 'timestamp', 'text')
                if any(not isinstance(m.get(k), str) for k in required):
                    raise ValueError('消息需要会话、发送者、时间和文本')
                datetime.fromisoformat(m['timestamp'])
                mid = m.get('id') or hashlib.sha256(json.dumps([m[k] for k in required], ensure_ascii=False).encode()).hexdigest()[:24]
                topic = m.get('topic') or m['chat']
                row = db.execute('INSERT OR IGNORE INTO messages(id,chat,sender,timestamp,text,type,topic,source) VALUES (?,?,?,?,?,?,?,?)',
                    (mid, m['chat'], m['sender'], m['timestamp'], m['text'], m.get('type', 'text'), topic, m.get('source', 'import')))
                if row.rowcount == 0:
                    continue
                inserted += 1
                spec = m.get('memory') if curated else None
                if spec:
                    reason_match = re.search(r'(?:因为|原因是|考虑到)(.+)', m['text'])
                    self._save_event(db, {**m, 'id': mid, 'topic': topic}, {
                        **spec, 'title': spec.get('title', m['text'][:150]),
                        'due': resolve_date(m['text'], m['timestamp']),
                        'reason': spec.get('reason') or (reason_match[1] if reason_match else ''),
                        'subject': m['sender'], 'evidence_ids': [mid], 'extraction_source': 'curated'}, 0)
                elif not curated:
                    self._extract_message(db, {**m, 'id': mid, 'topic': topic})
                db.execute('UPDATE messages SET analyzed_version=1 WHERE id=?', (mid,))
        return inserted

    def _extract_message(self, db, message):
        change=self._task_date_change(db,message)
        if change:
            self._save_event(db,{**message,'topic':change['topic_suggestion'] or message['topic']},change,0)
            return 1
        context = [dict(r) for r in db.execute('''SELECT * FROM messages WHERE chat=? AND id<>? AND
            (timestamp<? OR (timestamp=? AND rowid<(SELECT rowid FROM messages WHERE id=?)))
            ORDER BY timestamp DESC,rowid DESC LIMIT 12''',
            (message['chat'], message['id'], message['timestamp'], message['timestamp'], message['id']))][::-1]
        try:
            events = extract_with_model(message, context)
        except Exception:
            # 服务不可用或输出不合格时明确标记回退，不记录可能含私有原文的异常。
            events = extract_events(message, context)
            for event in events:
                event['extraction_source'] = 'rules-model-fallback'
        if events is None:
            events = extract_events(message, context)
        for index, event in enumerate(events):
            self._save_event(db, message, event, index)
        return len(events)

    def _save_event(self, db, message, event, index):
        mid = 'mem-' + message['id'] + (f'-{index+1}' if index else '')
        previous = db.execute('SELECT * FROM memories WHERE id=?', (mid,)).fetchone()
        if previous and (previous['status'] != 'pending' or previous['extraction_source'] == 'curated' or
                db.execute('SELECT 1 FROM reviews WHERE memory_id=? LIMIT 1', (mid,)).fetchone()):
            return False
        relation = event.get('relation_suggestion','') if event.get('field')=='task_due_change' else ''
        candidates = db.execute('''SELECT memories.*, messages.timestamp FROM memories JOIN messages
            ON memories.message_id=messages.id WHERE messages.timestamp<? AND memories.status<>'dismissed'
            ORDER BY messages.timestamp DESC LIMIT 100''', (message['timestamp'],)).fetchall()
        for candidate in ([] if event.get('field')=='task_due_change' else candidates):
            if relation:
                break
            shared = candidate['topic'] == message['topic'] or (event.get('topic_suggestion') and
                event['topic_suggestion'] in (candidate['topic'], candidate['topic_suggestion']))
            if not shared:
                continue
            is_completion = event.get('event') == 'completion' and candidate['kind'] == 'task' and candidate['subject'] in ('', event.get('subject'))
            is_change = event.get('event') in ('change', 'confirmation', 'cancellation') and candidate['kind'] == event['kind'] and event.get('field') and candidate['field'] == event['field']
            is_cancellation = event.get('event') == 'cancellation' and lexical_score(event['title'], candidate['title']) >= 0.2
            if is_change or is_cancellation or (is_completion and lexical_score(event['title'], candidate['title']) >= 0.2):
                relation = candidate['id']
                break
        fields = ['id', 'message_id', 'topic', 'kind', 'title', 'status', 'due', 'reason', 'field', 'value', 'supersedes',
                  'evidence_ids', 'event', 'condition', 'subject', 'topic_suggestion', 'relation_suggestion', 'extraction_source',
                  'date_kind', 'task_role', 'certainty']
        values = [mid, message['id'], message['topic'], event['kind'], event['title'], event.get('status', 'pending'),
            event.get('due'), event.get('reason', ''), event.get('field', ''), event.get('value', ''), event.get('supersedes', ''),
            json.dumps(event.get('evidence_ids', [message['id']]), ensure_ascii=False), event.get('event', ''),
            event.get('condition', ''), event.get('subject', message['sender']), event.get('topic_suggestion', ''), relation,
            event.get('extraction_source', 'context-rules'), event.get('date_kind', 'associated'),
            event.get('task_role', ''), event.get('certainty', '')]
        sql = 'INSERT INTO memories (' + ','.join(fields) + ') VALUES (' + ','.join('?' for _ in fields) + ')'
        sql += ' ON CONFLICT(id) DO UPDATE SET ' + ','.join(f'{k}=excluded.{k}' for k in fields[2:])
        db.execute(sql, values)
        return True

    def _task_date_change(self, db, message):
        tasks=[dict(r) for r in db.execute('''SELECT memories.*,messages.chat,messages.timestamp
            FROM memories JOIN messages ON memories.message_id=messages.id
            WHERE memories.kind='task' AND messages.chat=? AND messages.timestamp<?
            AND memories.status IN ('pending','confirmed') AND memories.due IS NOT NULL
            ORDER BY messages.timestamp DESC LIMIT 100''',(message['chat'],message['timestamp']))]
        return extract_task_date_change(message,tasks)

    def analyze(self):
        with self.connect() as db:
            try:
                limit = 25 if model_name() else 200
            except ValueError:
                limit = 200
            messages = [dict(r) for r in db.execute("SELECT * FROM messages WHERE source<>'synthetic' AND analyzed_version<1 ORDER BY timestamp,id LIMIT ?", (limit,))]
            events = sum(self._extract_message(db, message) for message in messages)
            db.executemany('UPDATE messages SET analyzed_version=1 WHERE id=?', [(message['id'],) for message in messages])
            missing=[dict(r) for r in db.execute('''SELECT * FROM messages WHERE source<>'synthetic'
                AND NOT EXISTS(SELECT 1 FROM memories WHERE memories.message_id=messages.id)
                AND (text LIKE '%提前%' OR text LIKE '%改到%' OR text LIKE '%改为%' OR text LIKE '%改成%'
                     OR text LIKE '%延期%' OR text LIKE '%延后%' OR text LIKE '%推迟%') ORDER BY timestamp,id''')]
            recovered=0
            for message in missing:
                change=self._task_date_change(db,message)
                if change:
                    recovered+=int(self._save_event(db,{**message,'topic':change['topic_suggestion'] or message['topic']},change,0))
            events+=recovered
            remaining = db.execute("SELECT count(*) FROM messages WHERE source<>'synthetic' AND analyzed_version<1").fetchone()[0]
        return {'messages': len(messages)+recovered, 'candidates': events, 'remaining': remaining, 'recovered_date_changes':recovered,
                'note': '人工修改、已确认记录及合成标注均保留。新识别内容仍待确认。'}

    def group_topic(self, source_topic, target_topic):
        if not isinstance(source_topic, str) or not isinstance(target_topic, str) or not target_topic.strip() or len(target_topic) > 100:
            raise ValueError('事项名称无效')
        moved = 0
        with self.connect() as db:
            rows = db.execute("SELECT * FROM memories WHERE topic=? AND topic_suggestion=? AND status<>'dismissed'", (source_topic, target_topic)).fetchall()
            for row in rows:
                before = dict(row)
                after = {**before, 'topic': target_topic}
                db.execute('UPDATE memories SET topic=? WHERE id=?', (target_topic, row['id']))
                db.execute('INSERT INTO reviews(memory_id,timestamp,before_json,after_json,note) VALUES (?,?,?,?,?)',
                    (row['id'], datetime.now().astimezone().isoformat(), json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False),
                     '人工批量采用事项建议，原始来源及确认状态不变'))
                moved += 1
        return {'moved': moved, 'topic': target_topic}

    def analyze_demo_model(self):
        from demo import context_demo_messages
        from remote_model import extract_demo
        rows = context_demo_messages()
        # 固定合成源；外部结果不读取或覆盖真实库。
        self.ingest(rows)
        extracted = saved = 0
        for index, message in enumerate(rows):
            events = extract_demo(message, rows[:index])
            extracted += len(events)
            with self.connect() as db:
                for event_index, event in enumerate(events):
                    event['extraction_source'] = 'remote-demo-model'
                    stored = db.execute('SELECT topic FROM messages WHERE id=?', (message['id'],)).fetchone()
                    saved += bool(self._save_event(db, {**message, 'topic': stored['topic']}, event, event_index))
        return {'messages': len(rows), 'candidates': extracted, 'saved': saved, 'remaining': 0,
                'note': '仅调用内置合成数据。人工修改、已确认记忆保持不变。'}

    def state(self):
        with self.connect() as db:
            messages = [dict(r) for r in db.execute('SELECT * FROM messages ORDER BY timestamp,id')]
            memories = [dict(r) for r in db.execute('''SELECT memories.*, messages.timestamp, messages.sender,
                messages.chat, messages.text, messages.topic AS source_topic FROM memories JOIN messages ON message_id=messages.id
                ORDER BY messages.timestamp, memories.id''')]
            reviews = [dict(r) for r in db.execute('SELECT * FROM reviews ORDER BY id DESC')]
            summaries={r['entity_key']:dict(r) for r in db.execute('SELECT * FROM paper_summaries')}
        reviewed_ids = {r['memory_id'] for r in reviews}
        for item in memories:
            try:
                item['evidence_ids'] = json.loads(item['evidence_ids']) or [item['message_id']]
            except (ValueError, TypeError):
                item['evidence_ids'] = [item['message_id']]
            item['event_label'] = '改期请求' if item['field']=='task_due_change' else EVENT_LABELS.get(item['event'], '')
            item['reviewed'] = item['id'] in reviewed_ids
            item.update(task_traits(item))
        paper_summaries.attach(memories,summaries,'memory')
        paper_summaries.attach(messages,summaries,'message')
        topics = sorted(set(m['topic'] for m in messages) | set(m['topic'] for m in memories))
        engine = '上下文识别 · 人工确认'
        try:
            if model_name():
                engine = '本机模型已配置 · 输出仍需确认'
        except ValueError:
            engine = '模型配置无效 · 已回退本地识别'
        return {'messages': messages, 'memories': memories, 'topics': topics, 'reviews': reviews,
                'engine': engine, 'conflicts': self._conflicts(memories),
                'counts': {'messages': len(messages), 'pending': sum(m['status'] == 'pending' for m in memories)}}

    @staticmethod
    def active_version(items):
        confirmed = sorted((m for m in items if m['status'] == 'confirmed'), key=lambda m:(m['timestamp'], m['id']))
        if not confirmed:
            return None
        baseline = confirmed[0]
        for item in confirmed[1:]:
            # A new confirmation cannot silently overwrite a manually selected
            # baseline. Replacing it requires the explicit version link.
            if item.get('supersedes') == baseline['id']:
                baseline = item
        return baseline

    @staticmethod
    def _conflicts(memories):
        groups = {}
        for item in memories:
            if item['kind'] not in ('fact', 'decision', 'question') or item['status'] == 'dismissed' or not item['field'] or not item['value']:
                continue
            groups.setdefault((item['topic'], 'fact' if item['kind']=='question' else item['kind'], item['field']), []).append(item)
        results = []
        for (topic, _, field), items in groups.items():
            baseline = Memory.active_version([m for m in items if m['kind'] != 'question'])
            if not baseline:
                continue
            for item in items:
                if item['timestamp'] > baseline['timestamp'] and item['value'] != baseline['value'] and item['supersedes'] != baseline['id'] and item['id'] != baseline['id']:
                    results.append({'topic': topic, 'field': field, 'before': baseline['id'], 'after': item['id'],
                        'note': '可能是修改或不同事项，请核对原文后确认。'})
        return results

    def apply_task_date_change(self, mid):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM memories WHERE id=?',(mid,)).fetchone()
            if not row or row['field']!='task_due_change' or not row['relation_suggestion']:
                raise ValueError('尚未唯一关联原承诺，请先核对原话和对应任务')
            change=dict(row)
            if change['status']=='confirmed':
                return {'id':mid,'task_id':change['relation_suggestion'],'already_applied':True}
            if change['status']!='pending' or not change['due']:
                raise ValueError('只有待确认的改期请求可以应用')
            task=db.execute('''SELECT memories.*,messages.chat FROM memories JOIN messages ON memories.message_id=messages.id
                               WHERE memories.id=?''',(change['relation_suggestion'],)).fetchone()
            source=db.execute('SELECT chat FROM messages WHERE id=?',(change['message_id'],)).fetchone()
            if not task or task['kind']!='task' or task['status'] not in ('pending','confirmed') or task['chat']!=source['chat']:
                raise ValueError('原承诺已失效或不属于此会话，请重新核对')
            before=dict(task);before.pop('chat')
            traits=task_traits(before)
            if traits['task_role'] not in ('mine','waiting') or traits['certainty']=='uncertain':
                raise ValueError('原承诺的执行人或确定性仍待核对')
            if before['due']!=change['value'] or before['subject']!=change['subject']:
                raise ValueError('原承诺的日期或执行人已改变，请重新核对，未覆盖现有记录')
            datetime.strptime(change['due'],'%Y-%m-%d')
            evidence=list(dict.fromkeys([*json.loads(before['evidence_ids']),before['message_id'],*json.loads(change['evidence_ids'])]))
            db.execute("UPDATE memories SET due=?,date_kind=?,status='confirmed',evidence_ids=? WHERE id=?",
                       (change['due'],change['date_kind'],json.dumps(evidence,ensure_ascii=False),before['id']))
            db.execute("UPDATE memories SET status='confirmed' WHERE id=?",(mid,))
            stamp=datetime.now().astimezone().isoformat()
            for previous in (before,change):
                after=dict(db.execute('SELECT * FROM memories WHERE id=?',(previous['id'],)).fetchone())
                note=f"人工确认改期：{change['value']} → {change['due']}；原承诺及改期原话保留"
                db.execute('INSERT INTO reviews(memory_id,timestamp,before_json,after_json,note) VALUES (?,?,?,?,?)',
                           (previous['id'],stamp,json.dumps(previous,ensure_ascii=False),json.dumps(after,ensure_ascii=False),note))
        return {'id':mid,'task_id':before['id'],'due':change['due'],'already_applied':False}

    def review(self, mid, changes, note):
        allowed = {'title', 'status', 'topic', 'due', 'reason', 'kind', 'field', 'value', 'supersedes', 'subject', 'date_kind', 'task_role', 'certainty'}
        if not changes or not set(changes) <= allowed:
            raise ValueError('修改字段不支持')
        if any(v is not None and not isinstance(v, str) for v in changes.values()):
            raise ValueError('修改内容必须是文本')
        if changes.get('status', 'pending') not in STATES:
            raise ValueError('状态无效')
        if changes.get('kind', 'fact') not in KINDS:
            raise ValueError('记忆类型无效')
        if changes.get('date_kind', 'associated') not in ('associated', 'event', 'deadline'):
            raise ValueError('日期类型无效')
        if changes.get('task_role', 'unknown') not in TASK_ROLES or changes.get('certainty', 'uncertain') not in CERTAINTIES:
            raise ValueError('任务归属或确定性无效')
        if changes.get('due'):
            datetime.strptime(changes['due'], '%Y-%m-%d')
        with self.connect() as db:
            row = db.execute('SELECT * FROM memories WHERE id=?', (mid,)).fetchone()
            if not row:
                raise ValueError('找不到这条记忆')
            before = dict(row)
            if before['field']=='task_due_change' and before['status']!='confirmed' and changes.get('status')=='confirmed':
                raise ValueError('请使用“确认改期并更新原承诺”，避免只确认请求却未更新日期')
            if before['field']=='task_due_change' and before['status']=='confirmed' and any(
                    k in changes and changes[k]!=before[k] for k in ('due','date_kind','value','field','kind','subject','status')):
                raise ValueError('已应用的改期保留为历史；后续调整请修改原承诺或核对新的改期请求')
            if 'due' in changes and 'value' not in changes and before['kind'] == 'fact' and re.match(r'^\d{4}-\d{2}-\d{2}', before['value'] or '') and changes['due']:
                changes = {**changes, 'value': changes['due'] + before['value'][10:]}
            # An owner correction updates classification too, never retains stale
            # "mine" metadata from the previous extraction.
            if 'subject' in changes and 'task_role' not in changes:
                changes = {**changes, 'task_role': task_traits({**before, **changes, 'task_role':''})['task_role']}
            if changes.get('kind', before['kind']) == 'task' and changes.get('task_role') in ('mine','waiting') and changes.get('certainty') in ('explicit','conditional') and before['event'] in ('request','proposal','cancellation'):
                changes = {**changes, 'event':'conditional' if before['condition'] else 'promise'}
            elif changes.get('task_role') in ('proposal','cancelled'):
                changes = {**changes, 'event':'proposal' if changes['task_role']=='proposal' else 'cancellation'}
            target = {**before, **changes}
            role = task_traits(target)['task_role']
            if target['kind'] == 'task':
                if role == 'mine' and target['subject'] != '我':
                    raise ValueError('我的承诺需要执行人为我')
                if role == 'waiting' and target['subject'] in ('', '我', '待确认执行人', '你', '您', '大家', '我们', '对方'):
                    raise ValueError('等别人需要填写明确执行人')
                if changes.get('status') in ('confirmed', 'completed') and (role in ('unknown', 'proposal', 'cancelled') or target['certainty'] == 'uncertain'):
                    raise ValueError('请先核对执行人及表达性质，再采用为任务')
            if target['supersedes']:
                previous = db.execute('SELECT * FROM memories WHERE id=?', (target['supersedes'],)).fetchone()
                if not previous or previous['id'] == mid or previous['topic'] != target['topic'] or previous['kind'] != target['kind'] or not target['field'] or previous['field'] != target['field']:
                    raise ValueError('历史版本必须是同一事项、同一类型和同一事实名称的记录')
                prev_time = db.execute('SELECT timestamp FROM messages WHERE id=?', (previous['message_id'],)).fetchone()[0]
                cur_time = db.execute('SELECT timestamp FROM messages WHERE id=?', (before['message_id'],)).fetchone()[0]
                if prev_time >= cur_time:
                    raise ValueError('历史版本必须早于当前消息')
            db.execute('UPDATE memories SET ' + ','.join(k + '=?' for k in changes) + ' WHERE id=?', [*changes.values(), mid])
            after = dict(db.execute('SELECT * FROM memories WHERE id=?', (mid,)).fetchone())
            db.execute('INSERT INTO reviews(memory_id,timestamp,before_json,after_json,note) VALUES (?,?,?,?,?)',
                (mid, datetime.now().astimezone().isoformat(), json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), note or '人工修改'))
        return after

    def ask(self, question, topic=None, as_of=None):
        state = self.state()
        if as_of:
            datetime.strptime(as_of, '%Y-%m-%d')
            # Roll back reviews made after the selected date. Original messages
            # are immutable; revisions have their own knowledge timestamp.
            by_id = {m['id']: m for m in state['memories']}
            for r in state['reviews']:
                if r['timestamp'][:10] > as_of and r['memory_id'] in by_id:
                    by_id[r['memory_id']].update(json.loads(r['before_json']))
        items = [m for m in state['memories'] if m['status'] != 'dismissed' and (not topic or m['topic'] == topic or m['source_topic'] == topic)
                 and (not as_of or m['timestamp'][:10] <= as_of)]
        intent = 'reason' if re.search('为什么|原因', question) else 'tasks' if re.search('答应|承诺|未完成|待办|要做|没做完', question) else 'time' if re.search('时间|几点|何时|什么时候|日期', question) else 'recap' if re.search('聊到哪里|聊了什么|回顾|进展|变化|联系.*前', question) else 'search'
        if intent == 'reason':
            candidates = [m for m in items if m['kind'] == 'decision']
            selected = ([m for m in candidates if m['status'] == 'confirmed'] or candidates)[-1:]
            text = '尚无决定证据，请查看原文或补充记录。'
            if selected:
                m = selected[0]
                text = m['title'] + ('。记录中的原因（可人工修正）：' + m['reason'] if m['reason'] else '。原文没有明确说明原因，需向当事人确认。')
        elif intent == 'tasks':
            # Only "我" denotes the local user; other speakers' promises remain theirs.
            selected = [m for m in items if m['kind'] == 'task' and task_traits(m)['task_role'] == 'mine' and m.get('event') not in ('completion', 'cancellation') and m['status'] not in ('completed', 'dismissed')]
            text = '以下承诺没有经人工确认的完成状态：' if selected else '当前范围内没有识别到我的未完成承诺；这不证明所有承诺均已完成。'
        elif intent == 'time':
            candidates = [m for m in items if m['kind'] == 'fact' and m['due']]
            confirmed = [m for m in candidates if m['status'] == 'confirmed']
            pool = confirmed or candidates
            grouped = {}
            for m in pool:
                grouped.setdefault((m['topic'], m['field'] or m['id']), []).append(m)
            selected = [self.active_version(group) or group[-1] for group in grouped.values()]
            text = '没有找到可支持时间的证据。'
            if selected:
                m = selected[0]
                text = (('最近一条已人工确认的时间记录：' if confirmed else '最近一条时间候选，仍待确认：') + m['title']) if len(selected) == 1 else '此事项包含多个时间记录。按事实名称列出各自的最新记录，请核对具体事项：'
                if len(set(x['field'] or x['title'] for x in candidates)) > 1 and not all(x['field'] for x in candidates):
                    text += '。此会话可能涉及不同事项，请在原文中核对。'
        elif intent == 'recap':
            selected = items[-8:]
            text = '最近的工作记录如下，提议和完成候选仍需核对：' if selected else '当前范围内没有可回顾的工作记忆。'
        else:
            ranked = sorted(((lexical_score(question, ' '.join([m['title'], m['text'], m['reason'], m['field'], m['topic']])), m) for m in items), key=lambda pair: (pair[0], pair[1]['timestamp']), reverse=True)
            selected = [m for score, m in ranked if score >= 0.2][:8]
            text = '找到以下相关记录：' if selected else '目前没有足够证据回答。可选择具体事项，或使用「时间」「为什么」「承诺」提问。'
        source_ids = {m['id'] for m in state['messages'] if not as_of or m['timestamp'][:10] <= as_of}
        evidence_ids = list(dict.fromkeys(e for m in selected for e in
            (json.loads(m['evidence_ids']) if isinstance(m['evidence_ids'], str) else m['evidence_ids']) if e in source_ids))
        return {'text': text, 'items': selected, 'evidence_ids': evidence_ids,
                'uncertain': any(m['status'] == 'pending' for m in selected) or not selected,
                'scope': topic or '全部事项', 'as_of': as_of, 'method': '上下文记忆与中文片段检索，未使用远程模型'}
