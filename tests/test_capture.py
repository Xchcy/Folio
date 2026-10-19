import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import capture
from engine import Memory

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')
class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.memory=Memory(Path(self.tmp.name)/'private.sqlite3')
        self.model=patch('capture.model_name',return_value='');self.model.start();self.addCleanup(self.model.stop)
    def save(self,**kwargs):return capture.save(self.memory,kwargs)['id']
    def test_delete_restore_keeps_linked_tasks_and_original_evidence(self):
        cid=self.save(text='需求原文',note='我负责整理方案')
        capture.process(self.memory,cid)
        before=self.memory.state()
        self.assertTrue(before['memories'])
        self.assertEqual(capture.set_deleted(self.memory,[cid])['changed'],1)
        self.assertEqual(capture.list_items(self.memory),[])
        self.assertEqual(capture.list_items(self.memory,deleted=True)[0]['id'],cid)
        self.assertEqual(self.memory.state(),before)
        self.assertEqual(capture.get(self.memory,cid)['text'],'需求原文')
        self.assertEqual(capture.set_deleted(self.memory,[cid])['changed'],0)
        capture.set_deleted(self.memory,[cid],deleted=False)
        self.assertEqual(capture.list_items(self.memory)[0]['id'],cid)
        self.assertEqual(self.memory.state(),before)

    def test_delete_batch_is_atomic_and_rejects_invalid_ids(self):
        a=self.save(text='甲');b=self.save(text='乙')
        for ids in ([],[a,'missing'],'all',[a,12]):
            with self.assertRaises(ValueError):capture.set_deleted(self.memory,ids)
        self.assertEqual(len(capture.list_items(self.memory)),2)
        self.assertEqual(capture.set_deleted(self.memory,[a,b,a])['changed'],2)
        self.assertEqual(len(capture.list_items(self.memory,deleted=True)),2)

    def test_deleted_capture_cannot_be_enriched_or_promoted(self):
        cid=self.save(note='我负责整理方案')
        capture.set_deleted(self.memory,[cid])
        capture.process(self.memory,cid)
        with self.assertRaises(ValueError):capture.promote(self.memory,cid)
        with self.assertRaises(ValueError):capture.edit(self.memory,cid,{'title':'修改'})
        with patch('capture.enqueue') as queue:
            self.assertEqual(capture.resume_pending(self.memory),0)
            queue.assert_not_called()
            capture.set_deleted(self.memory,[cid],deleted=False)
            queue.assert_called_once_with(self.memory,cid)

    def test_delete_during_enrichment_does_not_create_tasks(self):
        cid=self.save(note='我负责整理方案')
        def classify(item,text):
            capture.set_deleted(self.memory,[cid])
            return {'category':'todo','title':'方案','topic':'方案','tasks':[{'title':'整理方案','due':'','date_kind':'associated'}]}
        with patch('capture.ai_classify',side_effect=classify):capture.process(self.memory,cid)
        self.assertEqual(self.memory.state()['memories'],[])
        self.assertEqual(capture.list_items(self.memory),[])

    def test_deleted_content_can_be_saved_again_without_matching_trash(self):
        cid=self.save(text='可重新收集的内容')
        capture.set_deleted(self.memory,[cid])
        result=capture.save(self.memory,{'text':'可重新收集的内容'})
        self.assertTrue(result['saved']);self.assertNotEqual(result['id'],cid)
    def test_local_ai_requires_grounded_quotes_and_valid_dates(self):
        import io,json
        cid=self.save(text='我周五交付方案',note='周五交付方案',original_at='2026-10-13T10:00:00+08:00')
        item=capture.get(self.memory,cid)
        def response(result):
            return io.BytesIO(json.dumps({'message':{'content':json.dumps(result)}}).encode())
        model={'category':'todo','title':'交付方案','topic':'方案','tasks':[{'title':'交付方案','due':'2026-10-16','date_kind':'deadline','quote':'周五交付方案'}]}
        with patch('capture.model_name',return_value='local-test'),patch('capture.build_opener') as opener:
            opener.return_value.open.return_value=response(model)
            self.assertEqual(capture.ai_classify(item,item['text'])['tasks'][0]['date_kind'],'associated')
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url,'http://127.0.0.1:11434/api/chat')
            model['tasks'][0]['quote']='不存在的原文'
            opener.return_value.open.return_value=response(model)
            with self.assertRaises(ValueError):capture.ai_classify(item,item['text'])
            model['tasks'][0]['quote']='周五交付方案';model['tasks'][0]['due']='2026-02-31'
            opener.return_value.open.return_value=response(model)
            with self.assertRaises(ValueError):capture.ai_classify(item,item['text'])

    def test_saved_before_any_enrichment_and_date_is_server_generated(self):
        cid=self.save(text='资料原文',created_at='1900-01-01')
        item=capture.get(self.memory,cid)
        self.assertEqual(item['state'],'saved');self.assertNotIn('1900',item['created_at'])
        self.assertEqual(item['text'],'资料原文');self.assertTrue(item['created_at'].endswith('+08:00'))
    def test_brief_personal_instruction_and_not_completed(self):
        cid=self.save(text='网页资料',source_url='https://example.org',note='周五联系对方，确认报价')
        capture.process(self.memory,cid)
        self.assertEqual(capture.get(self.memory,cid)['category'],'todo')
        other=self.save(note='已经联系对方并完成整理')
        capture.process(self.memory,other)
        self.assertNotEqual(capture.get(self.memory,other)['category'],'todo')

    def test_restart_requeues_only_unfinished_captures(self):
        a=self.save(text='a');b=self.save(text='b')
        capture.edit(self.memory,b,{'title':'人工标题'})
        with patch('capture.enqueue') as queue:
            self.assertEqual(capture.resume_pending(self.memory),1)
        self.assertEqual(queue.call_args.args[1],a)

    def test_duplicate_append_copy_and_no_original_overwrite(self):
        cid=self.save(text='同一资料',note='初次说明')
        self.assertFalse(capture.save(self.memory,{'text':'同一资料','note':'第二次说明'})['saved'])
        capture.save(self.memory,{'text':'同一资料','note':'第二次说明','duplicate':'append'})
        self.assertIn('初次说明\n第二次说明',capture.get(self.memory,cid)['note'])
        other=capture.save(self.memory,{'text':'同一资料','duplicate':'copy'})
        self.assertNotEqual(cid,other['id'])
    def test_image_kept_when_ocr_and_model_fail(self):
        cid=self.save(image_data='data:image/png;base64,'+base64.b64encode(PNG).decode())
        with patch('capture.ocr_image',side_effect=ValueError('识别不可用')),patch('capture.ai_classify',side_effect=ValueError('模型失败')):
            capture.process(self.memory,cid)
        item=capture.get(self.memory,cid)
        self.assertEqual(item['image'],PNG);self.assertEqual(item['state'],'ready');self.assertIn('失败',item['detail'])
        public=capture.list_items(self.memory)[0];self.assertTrue(public['has_image']);self.assertNotIn('image',public)
    def test_action_creates_pending_task_and_is_idempotent(self):
        cid=self.save(text='需求原文',note='我负责整理演示方案，明天发给你',original_at='2026-10-14T12:00:00+08:00')
        capture.process(self.memory,cid)
        state=self.memory.state();tasks=state['memories']
        self.assertTrue(tasks);self.assertEqual(tasks[0]['status'],'pending');self.assertEqual(tasks[0]['due'],'2026-10-15')
        capture.promote(self.memory,cid)
        self.assertEqual(len(self.memory.state()['memories']),len(tasks))
        self.assertIn('需求原文',state['messages'][0]['text'])
    def test_copied_promise_without_intent_not_mine(self):
        cid=self.save(text='我负责明天交付报告',source_url='https://example.org/article')
        capture.process(self.memory,cid)
        self.assertEqual(capture.get(self.memory,cid)['category'],'reference')
        self.assertEqual(self.memory.state()['memories'],[])
    def test_manual_classification_survives_rerun_and_original_retained(self):
        cid=self.save(text='原始内容')
        capture.edit(self.memory,cid,{'title':'我的标题','category':'idea','due':'2026-10-22'})
        capture.process(self.memory,cid)
        item=capture.get(self.memory,cid)
        self.assertEqual(item['title'],'我的标题');self.assertEqual(item['text'],'原始内容')
        capture.save(self.memory,{'text':'原始内容','note':'新说明','duplicate':'append'})
        capture.process(self.memory,cid)
        self.assertEqual(capture.get(self.memory,cid)['title'],'我的标题')
        capture.promote(self.memory,cid)
        self.assertEqual(self.memory.state()['memories'][0]['title'],'我的标题')
    def test_reject_invalid_image_url_and_dates(self):
        for data in [{'source_url':'javascript:alert(1)'},{'source_url':'https://name:secret@example.org'},{'image_data':'data:image/svg+xml;base64,PHN2Zz4='},{'text':'x','original_at':'yesterday'}]:
            with self.assertRaises(ValueError):capture.save(self.memory,data)
        cid=self.save(text='x')
        with self.assertRaises(ValueError):capture.edit(self.memory,cid,{'due':'2026-02-31'})
    def test_multi_model_tasks_share_evidence(self):
        cid=self.save(text='整理报告并发送邀请')
        result={'category':'todo','title':'准备活动','topic':'活动','tasks':[{'title':'整理报告','due':'','date_kind':'associated'},{'title':'发送邀请','due':'','date_kind':'associated'}]}
        with patch('capture.ai_classify',return_value=result):capture.process(self.memory,cid)
        tasks=self.memory.state()['memories'];self.assertEqual(len(tasks),2)
        self.assertEqual(tasks[0]['message_id'],tasks[1]['message_id'])
        self.assertTrue(all(x['status']=='pending' for x in tasks))
    def test_promote_transaction_rolls_back_on_bad_task(self):
        cid=self.save(text='资料')
        with self.memory.connect() as db:db.execute("UPDATE captures SET tasks='[{\"title\": null}]' WHERE id=?",(cid,))
        # Explicit promotion does not accept a malformed machine-generated task.
        with self.assertRaises(ValueError):capture.promote(self.memory,cid)
        self.assertEqual(self.memory.state()['messages'],[])

if __name__=='__main__':unittest.main()
