"""Synthetic regressions for ownership, dates, revisions and local model output."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import Memory
from extraction import extract_events
from local_model import validate_events


def msg(mid, text, sender='我', stamp='2026-10-13T10:00:00+08:00'):
    return dict(id=mid,chat='核对测试（合成）',topic='核对测试',sender=sender,timestamp=stamp,text=text,type='text')


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{'MEMORY_LOCAL_MODEL':''});env.start();self.addCleanup(env.stop)
        self.memory=Memory(Path(self.temp.name)/'memory.sqlite3')

    def item(self, text, sender='我'):
        self.memory.ingest([msg('a',text,sender)])
        return self.memory.state()['memories'][0]

    def test_other_speakers_first_person_is_waiting(self):
        item=self.item('我来整理报价，明天发给你。','小李')
        self.assertEqual((item['subject'],item['task_role'],item['certainty']),('小李','waiting','explicit'))
        self.assertFalse(self.memory.ask('我的未完成承诺')['items'])

    def test_request_does_not_become_mine(self):
        item=self.item('你帮我整理报价。','小李')
        self.assertEqual((item['subject'],item['task_role'],item['certainty']),('待确认执行人','proposal','uncertain'))

    def test_adopted_task_remains_findable_from_original_source_after_topic_move(self):
        item=self.item('我负责提交演示材料。')
        self.memory.review(item['id'],{'topic':'演示准备'},'人工归入事项')
        self.memory.review(item['id'],{'status':'confirmed'},'采用任务')
        current=self.memory.state()['memories'][0]
        self.assertEqual(current.get('source_topic'),'核对测试')
        for topic in ['核对测试','演示准备']:
            result=self.memory.ask('我的未完成承诺',topic)
            self.assertEqual([m['id'] for m in result['items']],[item['id']])
        self.assertEqual(current['status'],'confirmed')

    def test_temporal_prefix_is_not_an_assignee(self):
        item=self.item('周五我负责提交材料。')
        self.assertEqual((item['subject'],item['task_role']),('我','mine'))

    def test_named_request_is_not_a_promise(self):
        item=self.item('请小李负责提交材料。')
        self.assertEqual((item['task_role'],item['certainty']),('proposal','uncertain'))

    def test_conditional_is_not_unqualified(self):
        item=self.item('如果预算够，我来整理材料。')
        self.assertEqual(item['certainty'],'conditional')
        self.assertTrue(item['condition'])

    def test_waiting_without_a_promise_stays_uncertain(self):
        item=self.item('等小李回复报价。')
        self.assertEqual((item['subject'],item['task_role'],item['certainty']),('小李','waiting','uncertain'))
        with self.assertRaises(ValueError):self.memory.review(item['id'],{'status':'confirmed'},'无依据')

    def test_proposal_and_cancellation_are_not_my_task(self):
        for text,role in [('要不要我来整理材料？','proposal'),('不用再整理材料了。','cancelled')]:
            items=extract_events(msg(role,text))
            self.assertEqual(items[0]['task_role'],role)
            self.assertNotEqual(items[0]['kind'],'task')

    def test_event_elsewhere_is_not_a_task_date(self):
        item=self.item('10月19日活动开幕。我负责准备材料。')
        task=next(m for m in self.memory.state()['memories'] if m['kind']=='task')
        self.assertIsNone(task['due'])

    def test_event_is_not_a_deadline(self):
        item=self.item('我负责准备10月19日的演示。')
        self.assertEqual((item['due'],item['date_kind']),('2026-10-19','event'))

    def test_original_time_and_explicit_deadline(self):
        self.memory.ingest([msg('old','我明天之前提交材料。',stamp='2025-12-31T22:00:00+08:00')])
        item=self.memory.state()['memories'][0]
        self.assertEqual((item['due'],item['date_kind']),('2026-01-01','deadline'))

    def test_context_relative_date_uses_prior_original_time(self):
        self.memory.ingest([msg('old','确认演示安排在明天。',stamp='2026-10-12T22:00:00+08:00'),msg('reply','好，就按刚才说的时间。')])
        item=next(m for m in self.memory.state()['memories'] if m['message_id']=='reply')
        self.assertEqual(item['due'],'2026-10-13')

    def test_proposal_surfaces_conflict_without_overwrite(self):
        self.memory.ingest([msg('old','确认演示安排在10月19日。',stamp='2026-10-12T10:00:00+08:00')])
        self.memory.review('mem-old',{'status':'confirmed','due':'2026-10-20'},'人工核对正确日期')
        self.memory.ingest([msg('new','要不要把演示改到10月22日？')])
        self.assertEqual(self.memory.ask('目前的时间')['evidence_ids'],['old'])
        self.assertEqual(self.memory.state()['conflicts'][0]['after'],'mem-new')
        self.assertEqual(next(m for m in self.memory.state()['memories'] if m['id']=='mem-old')['value'],'2026-10-20')

    def test_confirm_without_version_link_does_not_replace_baseline(self):
        self.memory.ingest([msg('old','确认演示安排在10月19日。',stamp='2026-10-12T10:00:00+08:00')])
        self.memory.review('mem-old',{'status':'confirmed'},'确认')
        self.memory.ingest([msg('new','演示改到10月22日。')])
        self.memory.review('mem-new',{'status':'confirmed'},'还未核对版本关系')
        self.assertEqual(self.memory.ask('目前的时间')['evidence_ids'],['old'])
        self.assertTrue(self.memory.state()['conflicts'])
        self.memory.review('mem-new',{'supersedes':'mem-old'},'核对后明确替代')
        self.assertEqual(self.memory.ask('目前的时间')['evidence_ids'],['new'])

    def test_same_day_time_proposal_is_a_conflict(self):
        self.memory.ingest([msg('old','确认演示安排在10月19日14:00。',stamp='2026-10-12T10:00:00+08:00')])
        self.memory.review('mem-old',{'status':'confirmed'},'确认')
        self.memory.ingest([msg('new','要不要改到10月19日下午3点？')])
        self.assertTrue(self.memory.state()['conflicts'])
        values={m['value'] for m in self.memory.state()['memories']}
        self.assertEqual(values,{'2026-10-19 14:00','2026-10-19 15:00'})

    def test_owner_edit_and_audit_survive_reanalysis(self):
        item=self.item('我负责准备材料。')
        self.memory.review(item['id'],{'subject':'小李','task_role':'waiting','certainty':'explicit','date_kind':'event'},'已核对实际执行人')
        with self.memory.connect() as db:db.execute('UPDATE messages SET analyzed_version=0')
        self.memory.analyze()
        state=self.memory.state();item=state['memories'][0]
        self.assertEqual((item['subject'],item['task_role'],item['date_kind']),('小李','waiting','event'))
        self.assertEqual(len(state['reviews']),1)
        self.assertFalse(self.memory.ask('我的未完成承诺')['items'])

    def test_model_cannot_invent_date_or_self_owner(self):
        source=msg('a','我负责整理材料，明天发给你。','小李')
        event={'kind':'task','event':'promise','subject':'我','title':'整理材料','due':'2026-10-14','evidence':[{'id':'a','quote':source['text']}]}
        cleaned=validate_events({'events':[event]},source,[])[0]
        self.assertEqual((cleaned['subject'],cleaned['task_role']),('小李','waiting'))
        event['due']='2099-01-01'
        with self.assertRaises(ValueError):validate_events({'events':[event]},source,[])

    def test_new_columns_are_additive_and_never_rewrite_messages(self):
        source=msg('a','我负责准备材料。');self.memory.ingest([source])
        Memory(self.memory.path)
        self.assertEqual(self.memory.state()['messages'][0]['text'],source['text'])
        self.assertEqual(len(self.memory.state()['messages']),1)


if __name__=='__main__':unittest.main()
