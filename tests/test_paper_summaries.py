import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import Memory
import paper_summaries as papers


class PaperSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.memory=Memory(self.root/'memory.sqlite3')
        env=patch.dict(os.environ,{'MEMORY_LOCAL_MODEL':''});env.start();self.addCleanup(env.stop)
        self.memory.ingest([dict(id='paper-a',chat='合成纸条',sender='我',timestamp='2026-10-17T10:00:00+08:00',text='我负责整理材料，周五给你。')])

    def test_summary_cache_does_not_change_original_and_invalidates_after_review(self):
        papers.configure(self.root,'synthetic-local-model')
        before=self.memory.state()
        with patch.object(papers,'summarize_batch',side_effect=lambda items,model:{m['key']:'整理材料并于周五交付，仍待确认。' for m in items}) as model:
            self.assertEqual(papers.generate(self.memory,self.root,'合成纸条','timeline')['saved'],1)
            self.assertEqual(papers.generate(self.memory,self.root,'合成纸条','timeline')['saved'],0)
            self.assertEqual(model.call_count,1)
            papers.configure(self.root,'other-local-model')
            self.assertEqual(papers.generate(self.memory,self.root,'合成纸条','timeline')['saved'],1)
            self.assertEqual(model.call_count,2)
        item=self.memory.state()['memories'][0]
        self.assertEqual(item['paper_summary_method'],'local-ai')
        self.assertEqual(item['title'],before['memories'][0]['title'])
        self.assertEqual(self.memory.state()['messages'],before['messages'])
        self.memory.review(item['id'],{'due':'2026-10-21'},'人工核对')
        self.assertEqual(self.memory.state()['memories'][0]['paper_summary_method'],'local-excerpt')

    def test_no_model_never_calls_a_provider_or_claims_ai_summary(self):
        with patch.object(papers,'summarize_batch') as provider:
            with self.assertRaises(ValueError):papers.generate(self.memory,self.root,'合成纸条','timeline')
            provider.assert_not_called()
        self.assertEqual(self.memory.state()['memories'][0]['paper_summary_method'],'local-excerpt')
        with patch.dict(os.environ,{'MEMORY_LOCAL_MODEL':'not-a-local-cloud-model'}):
            self.assertEqual(papers.settings(self.root)['model'],'')

    def test_validates_sentence_evidence_and_pending_state(self):
        item={**self.memory.state()['memories'][0],'key':'one'}
        for summary in ['已完成材料交付。','改为2099-01-01交付。','整理材料。然后完成。','x'*91]:
            with self.subTest(summary=summary),self.assertRaises(ValueError):
                papers.validate_summaries({'summaries':[{'id':'one','summary':summary}]},[item])
        self.assertEqual(papers.validate_summaries({'summaries':[{'id':'one','summary':'计划整理材料，仍待确认。'}]},[item])['one'],'计划整理材料，仍待确认。')
        for record,summary in [({**item,'field':'task_due_change'},'交付日期已改为周三。'),
                               ({**item,'text':'不用再整理材料'},'整理材料。'),
                               ({**item,'condition':'预算足够'},'负责交付材料。')]:
            with self.assertRaises(ValueError):papers.validate_summaries({'summaries':[{'id':'one','summary':summary}]},[record])

    def test_raw_messages_are_separate_and_stale_generation_cannot_replace_current_summary(self):
        papers.configure(self.root,'synthetic-local-model')
        def change_during_generation(items,model):
            self.memory.review('mem-paper-a',{'due':'2026-10-21'},'并行人工修改')
            return {m['key']:'旧摘要。' for m in items}
        with patch.object(papers,'summarize_batch',side_effect=change_during_generation):
            self.assertEqual(papers.generate(self.memory,self.root,'合成纸条','timeline')['saved'],0)
        self.assertEqual(self.memory.state()['memories'][0]['paper_summary_method'],'local-excerpt')
        with patch.object(papers,'summarize_batch',side_effect=lambda items,model:{m['key']:'原话涉及整理材料。' for m in items}):
            self.assertEqual(papers.generate(self.memory,self.root,'合成纸条','messages')['saved'],1)
        self.assertEqual(self.memory.state()['messages'][0]['paper_summary_method'],'local-ai')

    def test_endpoint_is_fixed_to_loopback_without_proxies(self):
        item={**self.memory.state()['memories'][0],'key':'one'}
        response=unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'message':{'content':json.dumps({'summaries':[{'id':'one','summary':'整理材料，仍待确认。'}]})}}).encode()
        with patch.object(papers,'build_opener') as opener:
            opener.return_value.open.return_value=response
            papers.summarize_batch([item],'synthetic-model')
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url,'http://127.0.0.1:11434/api/chat')
        for name in ['provider-cloud','https://outside.example','']:
            with self.assertRaises(ValueError):papers.configure(self.root,name)
