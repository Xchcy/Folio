import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from engine import Memory
from extraction import resolve_date, extract_events
from local_model import validate_events, model_name


def message(mid, text, sender='我', day='13', chat='合成协作'):
    return dict(id=mid, chat=chat, sender=sender, timestamp=f'2026-10-{day}T10:00:00', text=text, type='text')


class ContextTests(unittest.TestCase):
    def date_messages(self):
        return [dict(id='date-original',chat='合成改期会话',sender='我',timestamp='2026-10-17T20:05:08+08:00',text='我现在去整理，周五给你',type='text'),
                dict(id='date-request',chat='合成改期会话',sender='合成伙伴',timestamp='2026-10-17T21:31:28+08:00',text='提前一点，周三给我',type='text')]

    def test_task_date_request_is_pending_and_confirmation_updates_original_once(self):
        originals=self.date_messages()
        self.memory.ingest(originals)
        state=self.memory.state()
        change=next(m for m in state['memories'] if m['message_id']=='date-request')
        self.assertEqual((change['kind'],change['status'],change['due']),('question','pending','2026-10-21'))
        self.assertEqual(change['relation_suggestion'],'mem-date-original')
        self.assertEqual(set(change['evidence_ids']),{'date-original','date-request'})
        old=next(m for m in state['memories'] if m['id']=='mem-date-original')
        self.assertEqual(old['due'],'2026-10-23')
        self.memory.apply_task_date_change(change['id'])
        self.memory.apply_task_date_change(change['id'])
        state=self.memory.state()
        old=next(m for m in state['memories'] if m['id']=='mem-date-original')
        self.assertEqual((old['due'],old['status']),('2026-10-21','confirmed'))
        self.assertEqual(set(old['evidence_ids']),{'date-original','date-request'})
        self.assertEqual(len(state['reviews']),2)
        with self.assertRaises(ValueError):self.memory.review(change['id'],{'due':'2026-10-24'},'不能只改已应用请求')
        self.assertEqual({m['id']:m['text'] for m in state['messages']},{m['id']:m['text'] for m in originals})

    def test_ambiguous_task_date_request_never_guesses_or_reads_other_chat(self):
        older,request=self.date_messages()
        other={**older,'id':'date-other','text':'我负责整理报价，周五给你'}
        self.memory.ingest([older,other,request])
        change=next(m for m in self.memory.state()['memories'] if m['message_id']=='date-request')
        self.assertEqual(change['relation_suggestion'],'')
        with self.assertRaises(ValueError):self.memory.apply_task_date_change(change['id'])

    def test_date_change_rejects_stale_and_dismissed_requests(self):
        self.memory.ingest(self.date_messages())
        self.memory.review('mem-date-original',{'due':'2026-10-22'},'另有人工修改')
        with self.assertRaises(ValueError):self.memory.apply_task_date_change('mem-date-request')
        self.assertEqual(next(m for m in self.memory.state()['memories'] if m['id']=='mem-date-original')['due'],'2026-10-22')
        self.memory.review('mem-date-request',{'status':'dismissed'},'忽略请求')
        with self.assertRaises(ValueError):self.memory.apply_task_date_change('mem-date-request')

    def test_date_request_does_not_link_other_chats_negation_or_quoted_speech(self):
        older,request=self.date_messages()
        self.memory.ingest([older,{**request,'chat':'另一个合成会话'}])
        change=next(m for m in self.memory.state()['memories'] if m['message_id']=='date-request')
        self.assertEqual(change['relation_suggestion'],'')
        for index,text in enumerate(['不要提前，周三给我','引用：提前一点，周三给我','提前一点，周三开会']):
            self.memory.ingest([{**request,'id':f'negative-{index}','text':text}])
            self.assertFalse(any(m['message_id']==f'negative-{index}' and m['field']=='task_due_change' for m in self.memory.state()['memories']))

    def test_multiple_ambiguous_changes_do_not_link_to_each_other(self):
        older,request=self.date_messages()
        self.memory.ingest([older,{**older,'id':'other','text':'我负责报价，周五给你'},request,
                            {**request,'id':'request-again','timestamp':'2026-10-17T21:40:00+08:00'}])
        changes=[m for m in self.memory.state()['memories'] if m['field']=='task_due_change']
        self.assertEqual(len(changes),2)
        self.assertTrue(all(not m['relation_suggestion'] for m in changes))

    def test_named_unrelated_work_does_not_reuse_only_available_task(self):
        older,request=self.date_messages()
        self.memory.ingest([older,{**request,'text':'报价提前一点，周三给我'}])
        change=next(m for m in self.memory.state()['memories'] if m['message_id']=='date-request')
        self.assertEqual(change['relation_suggestion'],'')

    def test_organize_backfills_previously_imported_unrecognized_date_request(self):
        with patch('engine.extract_task_date_change',return_value=None):
            self.memory.ingest(self.date_messages())
        self.assertFalse(any(m['message_id']=='date-request' for m in self.memory.state()['memories']))
        self.memory.analyze()
        self.assertTrue(any(m['message_id']=='date-request' for m in self.memory.state()['memories']))
        self.memory.review('mem-date-request',{'status':'dismissed'},'忽略')
        self.memory.analyze()
        self.assertEqual(next(m for m in self.memory.state()['memories'] if m['id']=='mem-date-request')['status'],'dismissed')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.tmp.name) / 'memory.sqlite3')
        self.env = patch.dict(os.environ, {'MEMORY_LOCAL_MODEL': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_date_corrections(self):
        cases = [('明年1月5日交付', '2026-12-25T10:00:00', '2027-01-05'),
            ('下下周二', '2026-10-13T10:00:00', '2026-10-27'),
            ('10月19日不行，改到10月22日', '2026-10-13T10:00:00', '2026-10-22'),
            ('确认不要改到10月19日', '2026-10-13T10:00:00', None),
            ('2027年2月29日', '2026-10-13T10:00:00', None)]
        for text, stamp, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(resolve_date(text, stamp), expected)

    def test_conditional_request_negation(self):
        conditional = extract_events(message('a', '如果预算够，我来整理材料。'))
        self.assertEqual(len(conditional), 1)
        self.assertEqual(conditional[0]['event'], 'conditional')
        self.assertIn('预算够', conditional[0]['condition'])
        request = extract_events(message('b', '你帮我整理一下材料。'))
        self.assertEqual(request[0]['kind'], 'question')
        self.assertEqual(request[0]['subject'], '待确认执行人')
        negative = extract_events(message('c', '确认不要改到10月19日。'))
        self.assertEqual(negative[0]['event'], 'cancellation')
        self.assertIsNone(negative[0]['due'])

    def test_multiple_events_and_owner(self):
        self.memory.ingest([message('a', '我负责文案，小李负责设计，周五一起提交。')])
        items = self.memory.state()['memories']
        self.assertEqual(len(items), 2)
        self.assertEqual({m['subject'] for m in items}, {'我', '小李'})
        self.assertEqual(len(self.memory.ask('我还有哪些承诺')['items']), 1)

    def test_completion_requires_review(self):
        self.memory.ingest([message('a', '我负责提交材料。', day='12'), message('b', '我已经提交了。')])
        items = self.memory.state()['memories']
        completion = next(m for m in items if m['event'] == 'completion')
        self.assertEqual(completion['relation_suggestion'], 'mem-a')
        self.assertEqual(completion['status'], 'pending')
        self.assertEqual(self.memory.ask('我的未完成承诺')['evidence_ids'], ['a'])

    def test_context_confirmation_has_two_sources(self):
        self.memory.ingest([message('a', '演示安排在10月19日。', day='12'), message('b', '好，就按刚才说的时间。')])
        reply = next(m for m in self.memory.state()['memories'] if m['message_id'] == 'b')
        self.assertEqual(set(reply['evidence_ids']), {'a', 'b'})
        self.assertEqual(reply['due'], '2026-10-19')
        self.assertEqual(reply['status'], 'pending')

    def test_context_does_not_cross_chat_or_old_window(self):
        first = message('a', '演示安排在10月19日。', day='01')
        self.assertFalse(extract_events(message('b', '好，就按刚才说的时间。'), [first]))

    def test_same_timestamp_cannot_use_later_message(self):
        self.memory.ingest([message('a', '好，就按刚才说的时间。'), message('b', '确认演示安排在10月19日。')])
        with self.memory.connect() as db:
            db.execute('UPDATE messages SET analyzed_version=0')
        self.memory.analyze()
        self.assertFalse(any(m['message_id'] == 'a' for m in self.memory.state()['memories']))
        first = message('a', '演示安排在10月19日。', day='12', chat='另一个合成群')
        self.assertFalse(extract_events(message('b', '好，就按刚才说的时间。'), [first]))

    def test_topic_suggestion_is_not_auto_merge(self):
        self.memory.ingest([message('a', '【社区开放日】确认演示安排在10月19日。', day='12'), message('b', '我来整理邀请文案。')])
        items = self.memory.state()['memories']
        self.assertTrue(all(m['topic_suggestion'] == '社区开放日' for m in items))
        self.assertTrue(all(m['topic'] == '合成协作' for m in items))
        self.memory.review('mem-b', {'topic': '社区开放日'}, '采用事项建议')
        self.assertEqual(next(m for m in self.memory.state()['memories'] if m['id'] == 'mem-b')['status'], 'pending')

    def test_batch_group_preserves_status_and_audit(self):
        self.memory.ingest([message('a', '【社区开放日】确认演示安排在10月19日。', day='12'), message('b', '我来整理邀请文案。')])
        result = self.memory.group_topic('合成协作', '社区开放日')
        self.assertEqual(result['moved'], 2)
        state = self.memory.state()
        self.assertTrue(all(m['topic'] == '社区开放日' and m['status'] == 'pending' for m in state['memories']))
        self.assertEqual(len(state['reviews']), 2)
        self.assertTrue(all(m['chat'] == '合成协作' for m in state['messages']))

    def test_pending_change_does_not_override_confirmed(self):
        self.memory.ingest([message('a', '确认演示定在10月19日。', day='12')])
        self.memory.review('mem-a', {'status': 'confirmed'}, '核对时间')
        self.memory.ingest([message('b', '演示改到10月22日。')])
        state = self.memory.state()
        self.assertEqual(len(state['conflicts']), 1)
        self.assertEqual(self.memory.ask('现在的时间')['evidence_ids'], ['a'])
        self.memory.review('mem-b', {'status': 'confirmed', 'supersedes': 'mem-a'}, '核对改期')
        self.assertFalse(self.memory.state()['conflicts'])
        self.assertEqual(self.memory.ask('现在的时间')['evidence_ids'], ['b'])

    def test_pending_decision_cannot_replace_confirmed(self):
        self.memory.ingest([message('a', '决定选用表格，因为已经熟悉。', day='12')])
        self.memory.review('mem-a', {'status': 'confirmed'}, '确认')
        self.memory.ingest([message('b', '决定改用页面，因为需要留痕。')])
        self.assertEqual(self.memory.ask('为什么选这个方案')['evidence_ids'], ['a'])

    def test_reanalysis_preserves_reviewed_and_is_idempotent(self):
        self.memory.ingest([message('a', '我来整理材料。')])
        self.memory.review('mem-a', {'title': '人工核对后的标题', 'status': 'completed'}, '已经完成')
        self.memory.analyze()
        self.memory.analyze()
        items = self.memory.state()['memories']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], '人工核对后的标题')
        self.assertEqual(items[0]['status'], 'completed')

    def test_chinese_fragment_search(self):
        self.memory.ingest([message('a', '我来整理邀请文案。')])
        self.assertEqual(self.memory.ask('邀请文案有什么记录')['evidence_ids'], ['a'])

    def test_model_validates_evidence_and_never_confirms(self):
        msg = message('a', '我负责整理材料。')
        event = {'kind': 'task', 'event': 'promise', 'title': '整理材料', 'subject': '我',
            'status': 'confirmed', 'evidence': [{'id': 'a', 'quote': '我负责整理材料'}]}
        valid = validate_events({'events': [event]}, msg, [])
        self.assertNotIn('status', valid[0])
        event['evidence'][0]['quote'] = '我负责付款'
        with self.assertRaises(ValueError):
            validate_events({'events': [event]}, msg, [])

    def test_model_failure_falls_back_explicitly(self):
        with patch('engine.extract_with_model', side_effect=ValueError('fake')):
            self.memory.ingest([message('a', '我负责整理材料。')])
        self.assertEqual(self.memory.state()['memories'][0]['extraction_source'], 'rules-model-fallback')

    def test_cloud_model_name_rejected(self):
        with patch.dict(os.environ, {'MEMORY_LOCAL_MODEL': 'model-cloud'}):
            with self.assertRaises(ValueError):
                model_name()

    def test_legacy_schema_migration(self):
        path = Path(self.tmp.name) / 'legacy.sqlite3'
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE memories(id TEXT PRIMARY KEY,message_id TEXT,topic TEXT,kind TEXT,title TEXT,status TEXT,due TEXT,reason TEXT,field TEXT,value TEXT,supersedes TEXT)')
            db.commit()
        legacy = Memory(path)
        legacy.ingest([message('a', '我负责整理材料。')])
        self.assertEqual(legacy.state()['memories'][0]['evidence_ids'], ['a'])


if __name__ == '__main__':
    unittest.main()
