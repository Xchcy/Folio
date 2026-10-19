import json
import tempfile
import unittest
from pathlib import Path
from demo import demo_messages
from engine import Memory, resolve_date, classify


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Memory(Path(self.tmp.name) / 'test.sqlite3')
        self.m.ingest(demo_messages(), curated=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_proposal_does_not_override_confirmed_time(self):
        result = self.m.ask('目前确认的时间是什么', '社区开放日')
        self.assertEqual(result['evidence_ids'], ['08'])
        self.assertIn('19日', result['text'])

    def test_historical_time(self):
        result = self.m.ask('时间是什么', '社区开放日', '2026-10-10')
        self.assertEqual(result['evidence_ids'], ['04'])

    def test_reason_with_source(self):
        result = self.m.ask('为什么选这个方案', '社区开放日')
        self.assertEqual(result['evidence_ids'], ['06'])
        self.assertIn('修改历史', result['text'])

    def test_acknowledgement_does_not_finish_tasks(self):
        result = self.m.ask('我答应了哪些事未完成', '社区开放日')
        self.assertEqual(set(result['evidence_ids']), {'07', '09'})

    def test_relative_date_based_on_source(self):
        self.assertEqual(resolve_date('下周二给你', '2026-10-10T10:22:00'), '2026-10-13')
        self.assertEqual(resolve_date('明天给你', '2026-12-31T23:00:00'), '2027-01-01')
        self.assertIsNone(resolve_date('2月30日', '2026-10-10T10:22:00'))

    def test_question_and_quoted_text_not_commitment(self):
        self.assertEqual(classify('我来做可以吗？'), 'question')
        self.assertEqual(classify('引用：我负责提交'), 'question')
        self.assertEqual(classify('我来做可以吗'), 'question')
        self.assertIsNone(classify('我不会提交这个文件'))
        self.assertIsNone(classify('我来不了'))

    def test_other_person_promise_not_mine(self):
        self.m.ingest([dict(id='other',chat='协作',sender='同事',timestamp='2026-10-13T12:00:00',text='我负责发材料',topic='社区开放日')])
        result = self.m.ask('我还有哪些承诺', '社区开放日')
        self.assertNotIn('other', result['evidence_ids'])

    def test_review_preserves_original_and_audit(self):
        self.m.review('mem-09', {'title':'邀请文案已核对', 'status':'completed'}, '核对交付')
        state = self.m.state()
        self.assertEqual(len(state['reviews']), 1)
        self.assertEqual(next(x['text'] for x in state['messages'] if x['id']=='09'), '我来更新邀请文案，明天把新版本发给你。')
        self.assertEqual(self.m.ask('我还有哪些承诺', '社区开放日')['evidence_ids'], ['07'])

    def test_historical_query_rolls_back_future_reviews(self):
        self.m.review('mem-09', {'status':'completed'}, '已交付')
        # The revision is recorded after 2026-10-11 in this environment.
        with self.m.connect() as db:
            db.execute("UPDATE reviews SET timestamp='2026-10-13T10:00:00+08:00'")
        self.assertIn('09', self.m.ask('我有哪些承诺', '社区开放日', '2026-10-11')['evidence_ids'])

    def test_dedup_preserves_distinct_platform_ids(self):
        self.assertEqual(self.m.ingest(demo_messages(), curated=True), 0)
        msg=dict(chat='协作',sender='我',timestamp='2026-10-13T12:00:00',text='我来整理资料')
        self.assertEqual(self.m.ingest([{**msg,'id':'same-text-a'},{**msg,'id':'same-text-b'}]), 2)

    def test_evidence_integrity(self):
        state=self.m.state()
        ids={m['id'] for m in state['messages']}
        self.assertTrue(all(m['message_id'] in ids for m in state['memories']))

    def test_import_cannot_self_confirm(self):
        self.m.ingest([dict(id='unsafe',chat='协作',sender='我',timestamp='2026-10-13T12:00:00',text='我来整理资料',memory={'kind':'task','status':'completed'})])
        item=next(m for m in self.m.state()['memories'] if m['message_id']=='unsafe')
        self.assertEqual(item['status'],'pending')

    def test_cannot_link_unrelated_history(self):
        with self.assertRaises(ValueError):
            self.m.review('mem-08', {'supersedes':'mem-01'}, '非法关联')

    def test_atomic_import_validation(self):
        before=len(self.m.state()['messages'])
        with self.assertRaises(ValueError):
            self.m.ingest([dict(chat='协作',sender='我',timestamp='2026-10-13T12:00:00',text='我来整理资料'), {'text':'缺少字段'}])
        self.assertEqual(len(self.m.state()['messages']), before)

    def test_no_evidence_no_invention(self):
        result=self.m.ask('预算是多少', '社区开放日')
        self.assertFalse(result['evidence_ids'])
        self.assertTrue(result['uncertain'])


if __name__ == '__main__':
    unittest.main()
