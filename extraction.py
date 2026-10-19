"""本地上下文抽取。输出均为候选，原始消息不变。"""
import re
from datetime import datetime, timedelta

EVENT_LABELS = {'promise': '承诺', 'request': '请求', 'conditional': '条件性承诺',
    'proposal': '提议', 'confirmation': '确认表达', 'change': '修改',
    'cancellation': '取消', 'completion': '完成候选', 'decision': '决定', 'fact': '事实'}

TASK_ROLES = {'mine', 'waiting', 'proposal', 'cancelled', 'unknown'}
CERTAINTIES = {'explicit', 'conditional', 'uncertain'}
UNKNOWN_OWNERS = {'', '待确认执行人', '待确认', '你', '您', '大家', '我们', '对方'}


def task_traits(item):
    """Compatible display metadata; never rewrite legacy or reviewed rows."""
    event, subject = item.get('event', ''), item.get('subject') or item.get('sender', '')
    if event == 'cancellation':
        role = 'cancelled'
    elif event in ('proposal', 'request'):
        role = 'proposal'
    elif item.get('kind') == 'task' and subject not in UNKNOWN_OWNERS:
        role = 'mine' if subject == '我' else 'waiting'
    else:
        role = 'unknown'
    certainty = 'conditional' if item.get('condition') else 'uncertain' if role in ('proposal', 'unknown') else 'explicit'
    return {'task_role': item.get('task_role') or role, 'certainty': item.get('certainty') or certainty}


def date_semantics(text, timestamp):
    date = resolve_date(text, timestamp)
    if not date:
        return None, 'associated'
    # Explicit action boundaries, not any occurrence of 前 (e.g. 活动前).
    if re.search(r'截止|最[迟晚]|之前|前(?:完成|提交|发送|发给|交付|给你)|(?:周|星期)[一二三四五六日天]前|\d[日号]前|(?:一起|统一)(?:提交|交付|完成)', text):
        return date, 'deadline'
    if re.search(r'活动|会议|演示|开放日|见面|开会|培训|发布会|内测', text):
        return date, 'event'
    return date, 'associated'


def schedule_value(text, date):
    match = re.search(r'(上午|下午|晚上|早上|中午|凌晨)?\s*(\d{1,2})(?:[:：](\d{2})|点(?:(\d{1,2})分?)?)', text)
    if not match:
        return date or ''
    period,hour,minute = match[1],int(match[2]),int(match[3] or match[4] or 0)
    if hour > 23 or minute > 59:
        return date or ''
    if period in ('下午','晚上','中午') and hour < 12:
        hour += 12
    elif period == '凌晨' and hour == 12:
        hour = 0
    clock = f'{hour:02}:{minute:02}'
    if not period and match[3] is None and hour < 12:
        clock += '（时段待确认）'
    return (date + ' ' if date else '日期待确认 ') + clock


def resolve_date(text, timestamp):
    base = datetime.fromisoformat(timestamp)
    text = re.sub(r'(?<!要)(?:不要|不能|不)(?:改到|改为|定在)[^，。；]*', '', text)
    # 只解析新值，跳过明确否定或被修改的旧日期。
    if re.search(r'(?:改到|改为|调整到|延期到|提前到)', text):
        text = re.split(r'(?:改到|改为|调整到|延期到|提前到)', text)[-1]
    elif re.search(r'(?:不要|不能|不改到|不定在)', text):
        return None
    text = re.sub(r'\d{1,2}月\d{1,2}[日号]?(?:不行|不可以|取消)', '', text)
    match = re.search(r'(?:(明年|今年|去年|\d{4}年))?(\d{1,2})月(\d{1,2})[日号]?', text)
    if match:
        year = base.year
        if match[1]:
            year += {'明年': 1, '今年': 0, '去年': -1}.get(match[1], 0)
            if match[1][0].isdigit():
                year = int(match[1][:-1])
        try:
            return datetime(year, int(match[2]), int(match[3])).date().isoformat()
        except ValueError:
            return None
    iso = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if iso:
        try:
            return datetime.strptime(iso[1], '%Y-%m-%d').date().isoformat()
        except ValueError:
            return None
    for word, days in [('大后天', 3), ('后天', 2), ('明天', 1), ('今天', 0)]:
        if word in text:
            return (base + timedelta(days=days)).date().isoformat()
    match = re.search(r'(下下周|下周|本周|这周|周|星期)([一二三四五六日天])', text)
    if match:
        day = '一二三四五六日'.index(match[2].replace('天', '日'))
        offset = day - base.weekday() + {'下下周': 14, '下周': 7}.get(match[1], 0)
        if match[1] in ('周', '星期') and offset < 0:
            offset += 7
        return (base + timedelta(days=offset)).date().isoformat()
    return None


def classify(text):
    if re.search(r'[?？]|是否|能不能|能否|要不要|吗[。！!]?\s*$|引用|「|[\[【](图片|语音|视频|文件|表情)', text):
        return 'question'
    if re.search(r'不要|别再|取消|我(?:不|没|不会|不能|不再)|我来不了|我无法', text):
        return None
    if re.search(r'(?:已经|已)(?:.*)(?:提交|发出|发送|交付|完成|发给)|做完|搞定', text):
        return 'fact'
    if re.search(r'^(?:请|麻烦)?(?:你|您|大家)|(?:你|您)帮我|^请[^，。；]{1,8}负责', text):
        return 'question'
    if re.search(r'我(?:来|会|负责|答应)|我[^，。；]*(?:发给|整理|提交|补上)|由我|[^，。；]{1,10}负责', text):
        return 'task'
    if re.search(r'决定|定了|确定用|改用|先用|选用|方案采用|不再用', text):
        return 'decision'
    if re.search(r'确认|改到|改为|时间是|截止|安排在|定在', text):
        return 'fact'
    return None


def lexical_score(query, text):
    """中文字符二元片段与关键词，避免整句精确匹配；不是语义向量。"""
    def terms(value):
        value = re.sub(r'目前|现在|什么|哪些|为什么|怎么|时候|请问|我们|当时|一下|是否|还有|了吗', '', value.lower())
        words = re.findall(r'[a-z0-9_]+|[\u4e00-\u9fff]+', value)
        return {term for word in words for term in ([word] if len(word) <= 2 else [word[i:i+2] for i in range(len(word)-1)])}
    left, right = terms(query), terms(text)
    if not left:
        return 0.0
    return len(left & right) / len(left)


def topic_hint(text, context):
    match = re.search(r'[【\[]([^】\]]{2,30})[】\]]', text)
    if match and not re.search(r'图片|语音|文件|视频|表情', match[1]):
        return match[1].strip(), []
    match = re.search(r'(?:关于|针对|事项[：:]|项目[：:])([^，。；\n]{2,25})', text)
    if match:
        return match[1].strip(), []
    for previous in reversed(context):
        if previous.get('type', 'text') != 'text':
            continue
        match = re.search(r'[【\[]([^】\]]{2,30})[】\]]', previous['text'])
        if match and not re.search(r'图片|语音|文件|视频|表情', match[1]):
            return match[1].strip(), [previous['id']]
    return '', []


def extract_task_date_change(message, tasks):
    text=message['text']
    if message.get('type','text')!='text' or re.search(r'引用[：:]|「|^\[引用\]|不要|不能|不用|不改',text):
        return None
    if not re.search(r'提前|延后|延期|推迟|改到|改为|改成',text):
        return None
    if classify(text)=='fact' and not re.search(r'给我|给你|交付|提交|交给|发给|完成|整理',text):
        return None
    if re.search(r'开会|会议|见面|开幕|放假|外卖',text) and not re.search(r'给我|交付|提交|交给|发给|完成',text):
        return None
    date=resolve_date(text,message['timestamp'])
    if not date:
        return None
    eligible=[]
    for task in tasks:
        if task['chat']!=message['chat'] or task['status'] not in ('pending','confirmed') or not task.get('due') or task.get('date_kind')=='event':
            continue
        age=(datetime.fromisoformat(message['timestamp'])-datetime.fromisoformat(task['timestamp'])).total_seconds()
        traits=task_traits(task)
        if not 0<age<=72*3600 or traits['task_role'] not in ('mine','waiting') or traits['certainty']=='uncertain':
            continue
        if '给我' in text and ((message['sender']!='我' and task['subject']!='我') or (message['sender']=='我' and task['subject']=='我')):
            continue
        eligible.append(task)
    target=eligible[0] if len(eligible)==1 else None
    prefix=re.split(r'提前|延后|延期|推迟|改到|改为|改成',text,maxsplit=1)[0].strip(' ，,')
    if target and prefix and prefix not in ('时间','日期','交付时间','截止时间','交付日期') and prefix not in target['title']:
        target=None
    if target and (('提前' in text and date>=target['due']) or (re.search(r'延后|延期|推迟',text) and date<=target['due']) or date==target['due']):
        target=None
    return {'kind':'question','event':'change','field':'task_due_change','title':text[:500],
            'due':date,'value':target['due'] if target else '',
            'subject':target['subject'] if target else '待确认执行人','task_role':'proposal','certainty':'uncertain',
            'date_kind':target['date_kind'] if target else 'associated',
            'relation_suggestion':target['id'] if target else '',
            'evidence_ids':[message['id'],target['message_id']] if target else [message['id']],
            'reason':'对方或本人提出改期；需人工确认后才更新原承诺。' if target else '尚不能唯一确定对应的承诺或日期方向，请人工核对。',
            'topic_suggestion':target['topic'] if target else '', 'extraction_source':'context-task-date'}


def extract_events(message, context=()):
    if message.get('type', 'text') != 'text':
        return []
    text = message['text']
    # 带引文的消息不据此建立当前说话人的承诺。
    if re.search(r'引用[：:]|「|^\[引用\]', text):
        return []
    context = [p for p in context if p['chat'] == message['chat'] and p['timestamp'] <= message['timestamp'] and
               0 <= (datetime.fromisoformat(message['timestamp']) - datetime.fromisoformat(p['timestamp'])).total_seconds() <= 72*3600][-12:]
    hint, hint_sources = topic_hint(text, context)
    clauses = []
    for sentence in re.split(r'[。；\n]', text):
        conditional = re.search(r'(?:如果|假如|只要|等到|等)(.+?)(?:[，,]|再|就)', sentence)
        condition = conditional[0].rstrip('，,再就') if conditional else ''
        clauses.extend((c.strip(' ，。；'), condition) for c in
            re.split(r'[，,](?=(?:我|你|您|小[\u4e00-\u9fff]{1,3})(?:来|会|负责|帮))', sentence) if c.strip(' ，。；'))
    result = []
    for clause, condition in clauses:
        clause = re.sub(r'^[【\[][^】\]]+[】\]]', '', clause).strip()
        if not clause:
            continue
        kind = classify(clause)
        waiting = re.match(r'^(?:我(?:在)?等|等待|等)((?:小|老)[\u4e00-\u9fff]{1,2}|[A-Za-z][\w.-]{0,20})(?:回复|发来|提供|确认|提交|交付)', clause)
        completion = bool(re.search(r'(?:已经|已).*?(?:提交|发出|发送|交付|完成|发给)|做完|搞定', clause))
        cancel = bool(re.search(r'取消|不再(?:用|做)|不用(?:再)?|不做了|不要改到|不要定在', clause))
        if waiting:
            kind, event = 'task', 'request'
        elif cancel:
            kind, event = 'question', 'cancellation'
        elif completion:
            kind, event = 'fact', 'completion'
        elif kind == 'task' and re.search(r'要不要|是否|可以考虑|建议|不如|打算|考虑|计划', clause):
            kind, event = 'question', 'proposal'
        elif kind == 'task':
            event = 'conditional' if condition else 'promise'
        elif kind == 'question':
            event = 'request' if re.search(r'你|您|请|麻烦', clause) and not re.search(r'要不要|是否', clause) else 'proposal'
        elif kind == 'decision':
            event = 'decision'
        elif kind == 'fact':
            event = 'change' if re.search(r'改到|改为|调整到|延期到|提前到', clause) else 'confirmation'
        else:
            event = 'fact'
        extra_evidence = []
        # 对明确指回上文的回复形成候选，保留两条证据；不自动确认。
        if kind is None and re.search(r'就按|按刚才|按上面|按之前|先保留', clause):
            prior = next((p for p in reversed(context) if p.get('type', 'text') == 'text' and
                (resolve_date(p['text'], p['timestamp']) or classify(p['text']) == 'decision')), None)
            if prior:
                kind, event = ('fact' if resolve_date(prior['text'], prior['timestamp']) else 'decision'), 'confirmation'
                extra_evidence = [prior['id']]
                clause = clause + '（所指上文：' + prior['text'][:100] + '）'
        if not kind:
            continue
        owner_clause = re.sub(r'^(?:(?:下下周|下周|本周|这周|周|星期)[一二三四五六日天](?:之前|前)?|今天|明天|后天|\d{1,2}月\d{1,2}[日号]?)(?:之前|前)?\s*', '', clause)
        owner = re.search(r'(?:^|[，,])\s*([^，。；]{1,8}?)负责', owner_clause)
        subject = message['sender']
        if owner and owner[1] not in ('我', '由我'):
            subject = owner[1]
        if event == 'request':
            subject = '待确认执行人'
        if waiting:
            subject = waiting[1]
        date, date_kind = date_semantics(clause, message['timestamp'])
        if extra_evidence:
            prior = next(p for p in context if p['id'] == extra_evidence[0])
            date, date_kind = date_semantics(prior['text'], prior['timestamp'])
        # Only an explicitly shared submission deadline belongs to every task.
        # An event date elsewhere in the message is not a task deadline.
        if kind == 'task' and not date:
            common = re.search(r'[，,]([^，。；\n]*(?:一起|统一|都在)[^。；\n]*(?:提交|交付|完成))', text)
            if common:
                date, _ = date_semantics(common[1], message['timestamp'])
                date_kind = 'deadline' if date else 'associated'
        reason = re.search(r'(?:因为|原因是|考虑到)(.+)', clause)
        value = schedule_value(prior['text'] if extra_evidence else clause,date)
        field = '时间安排' if value and kind in ('fact','question') and event != 'completion' else '采用方案' if kind == 'decision' else ''
        item = {'kind': kind, 'title': clause[:500], 'event': event, 'condition': condition,
            'subject': subject, 'due': date, 'reason': reason[1] if reason else '', 'field': field,
            'value': value, 'topic_suggestion': hint,
            'evidence_ids': list(dict.fromkeys([message['id'], *extra_evidence, *hint_sources])),
            'extraction_source': 'context-rules', 'date_kind': date_kind}
        item.update(task_traits(item))
        if waiting:
            item.update(task_role='waiting',certainty='uncertain')
        result.append(item)
    return result[:12]
