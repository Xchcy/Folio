import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import server
import remote_model


class ApiTests(unittest.TestCase):
    def test_paper_summary_configuration_and_job_require_token_and_preserve_data(self):
        import paper_summaries
        memory=server.store('private')
        memory.ingest([dict(id='paper-api',chat='合成纸条',sender='我',timestamp='2026-10-17T10:00:00+08:00',text='我负责整理材料。')])
        with self.assertRaises(HTTPError) as error:self.post('/api/paper-model',{'model':'synthetic-local'},token=False)
        self.assertEqual(error.exception.code,403);error.exception.close()
        self.post('/api/paper-model',{'model':'synthetic-local'})
        with patch.object(paper_summaries,'summarize_batch',side_effect=lambda items,model:{m['key']:'整理材料，仍待确认。' for m in items}):
            job=self.post('/api/paper-summaries',{'mode':'private','topic':'合成纸条','view':'timeline'})
            import time
            for _ in range(100):
                with urlopen(self.base+'/api/job?id='+job['job_id'],timeout=5) as response:result=json.load(response)
                if result['status']!='running':break
                time.sleep(.01)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['result']['saved'],1)
        item=memory.state()['memories'][0]
        self.assertEqual((item['paper_summary_method'],item['status']),('local-ai','pending'))
        self.assertEqual(memory.state()['messages'][0]['text'],'我负责整理材料。')

    def test_task_date_change_requires_token_and_updates_original(self):
        memory=server.store('private')
        memory.ingest([dict(id='date-a',chat='合成改期',sender='我',timestamp='2026-10-17T20:00:00+08:00',text='我现在去整理，周五给你'),
                       dict(id='date-b',chat='合成改期',sender='合成伙伴',timestamp='2026-10-17T21:00:00+08:00',text='提前一点，周三给我')])
        with self.assertRaises(HTTPError) as error:
            self.post('/api/task-date-change',{'mode':'private','id':'mem-date-b'},token=False)
        self.assertEqual(error.exception.code,403);error.exception.close()
        result=self.post('/api/task-date-change',{'mode':'private','id':'mem-date-b'})
        self.assertEqual((result['task_id'],result['due']),('mem-date-a','2026-10-21'))
        self.assertTrue(self.post('/api/task-date-change',{'mode':'private','id':'mem-date-b'})['already_applied'])

    def test_capture_delete_restore_requires_token_and_retains_item(self):
        import capture
        memory=server.store('private')
        cid=capture.save(memory,{'text':'合成删除测试'})['id']
        with self.assertRaises(HTTPError) as error:self.post('/api/capture-delete',{'ids':[cid]},token=False)
        self.assertEqual(error.exception.code,403);error.exception.close()
        self.assertEqual(len(capture.list_items(memory)),1)
        self.assertEqual(self.post('/api/capture-delete',{'ids':[cid]})['changed'],1)
        with urlopen(self.base+'/api/captures') as response:self.assertEqual(json.load(response)['items'],[])
        with urlopen(self.base+'/api/captures?deleted=1') as response:self.assertEqual(json.load(response)['items'][0]['id'],cid)
        self.assertEqual(self.post('/api/capture-restore',{'ids':[cid]})['changed'],1)
        self.assertEqual(capture.list_items(memory)[0]['id'],cid)

    def test_revoke_only_allows_private_authenticated_operation(self):
        import wechat
        with patch.object(wechat,'revoke_chats',return_value={'revoked':1}) as revoke:
            for mode,token in [('demo',True),('private',False)]:
                with self.assertRaises(HTTPError) as error:self.post('/api/wechat/revoke',{'mode':mode,'chats':['合成甲']},token=token)
                error.exception.close()
            revoke.assert_not_called()
            self.assertEqual(self.post('/api/wechat/revoke',{'mode':'private','chats':['合成甲']})['revoked'],1)
            revoke.assert_called_once_with(['合成甲'])

    def test_authorized_listing_is_private_and_does_not_read_history(self):
        import wechat
        with patch.object(wechat,'authorized_chats',return_value={'chats':[{'name':'合成甲'}]}) as listed,patch.object(wechat,'bridge') as reader:
            result=self.post('/api/wechat/authorized',{'mode':'private'})
            self.assertEqual(result['chats'][0]['name'],'合成甲')
            listed.assert_called_once();reader.assert_not_called()
            for body,token in (({'mode':'demo'},True),({'mode':'private'},False)):
                with self.assertRaises(HTTPError) as error:self.post('/api/wechat/authorized',body,token=token)
                error.exception.close()
            self.assertEqual(listed.call_count,1)

    def test_sync_requires_and_forwards_explicit_selection(self):
        with patch.object(server,'sync',return_value={'chats':[]}) as reader:
            with self.assertRaises(HTTPError) as error:self.post('/api/sync',{'mode':'private'})
            self.assertEqual(error.exception.code,400);error.exception.close();reader.assert_not_called()
            self.post('/api/sync',{'mode':'private','chats':['合成乙']})
            self.assertEqual(reader.call_args.kwargs['selected'],['合成乙'])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = patch.object(server, 'DATA_ROOT', Path(self.tmp.name))
        self.root.start()
        self.env = patch.dict(os.environ, {'MEMORY_LOCAL_MODEL': ''})
        self.env.start()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.root.stop()
        self.env.stop()
        self.tmp.cleanup()

    def post(self, path, body, token=True):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Memory-Token'] = server.TOKEN
        with urlopen(Request(self.base + path, data=json.dumps(body).encode(), headers=headers), timeout=5) as response:
            return json.load(response)

    def test_model_config_never_exposes_key(self):
        with patch.dict(remote_model.CONFIG, {'api_key': 'test-only-key'}):
            with urlopen(self.base + '/api/model-config', timeout=5) as response:
                data = response.read().decode()
        self.assertNotIn('test-only-key', data)
        self.assertTrue(json.loads(data)['has_key'])

    def test_model_api_rejects_private_space(self):
        with patch('remote_model.extract_demo') as mocked, self.assertRaises(HTTPError) as error:
            self.post('/api/model-analyze', {'mode': 'private'})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()
        mocked.assert_not_called()

    def test_write_requires_token(self):
        with self.assertRaises(HTTPError) as error:
            self.post('/api/group', {'mode': 'demo', 'source_topic': '发布讨论（合成）', 'target_topic': '产品发布'}, token=False)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_group_route_and_multi_evidence(self):
        result = self.post('/api/group', {'mode': 'demo', 'source_topic': '发布讨论（合成）', 'target_topic': '产品发布'})
        self.assertEqual(result['moved'], 8)
        with urlopen(self.base + '/api/state', timeout=5) as response:
            state = json.load(response)
        self.assertEqual(sum(m['topic'] == '产品发布' for m in state['memories']), 8)
        self.assertTrue(any(len(m['evidence_ids']) > 1 for m in state['memories']))

    def test_demo_and_missing_token_block_reader(self):
        from urllib.error import HTTPError
        import wechat
        with patch.object(wechat,'search_chats') as mocked:
            for mode,token in [('demo',True),('private',False)]:
                with self.assertRaises(HTTPError) as error:
                    self.post('/api/wechat/chats',{'mode':mode},token=token)
                error.exception.close()
            mocked.assert_not_called()

    def test_import_route_uses_private_root(self):
        from server import store
        import wechat
        import time
        from test_wechat import fixture
        wechat.PREVIEWS['api']={'messages':[fixture()], 'chat':'合成对象','username':'synthetic','expires':time.monotonic()+3600}
        try:
            result=self.post('/api/wechat/import',{'mode':'private','selections':[{'preview':'api','ids':['one']}]})
            self.assertEqual(result['added'],1)
            self.assertEqual(len(store('private').state()['messages']),1)
            self.assertFalse(any(m['id']=='one' for m in store('demo').state()['messages']))
        finally:wechat.PREVIEWS.clear()


    def test_capture_is_private_and_requires_token(self):
        with patch('capture.enqueue') as queue:
            with self.assertRaises(HTTPError) as error:
                self.post('/api/capture', {'text':'合成收集内容'}, token=False)
            self.assertEqual(error.exception.code,403);error.exception.close()
            saved=self.post('/api/capture', {'mode':'demo','text':'合成收集内容'})
            queue.assert_called_once()
        with urlopen(self.base+'/api/captures') as response:items=json.load(response)['items']
        self.assertEqual(items[0]['id'],saved['id'])
        self.assertEqual(server.store('demo').state()['messages'][0]['source'],'synthetic')
        self.assertFalse(any(m['text']=='合成收集内容' for m in server.store('demo').state()['messages']))

    def test_capture_edit_and_promote_via_http(self):
        with patch('capture.enqueue'):
            saved=self.post('/api/capture', {'text':'参考资料','note':'稍后看看'})
        self.post('/api/capture-edit',{'id':saved['id'],'changes':{'title':'阅读并整理资料','category':'todo','due':'2026-10-22','date_kind':'deadline'}})
        first=self.post('/api/capture-promote',{'id':saved['id']})
        second=self.post('/api/capture-promote',{'id':saved['id']})
        self.assertEqual(first['memory_ids'],second['memory_ids'])
        row=server.store('private').state()['memories'][0]
        self.assertEqual(row['status'],'pending');self.assertEqual(row['title'],'阅读并整理资料')
        self.assertEqual(row['due'],'2026-10-22');self.assertEqual(row['date_kind'],'deadline')

    def test_capture_image_roundtrip_and_no_raw_blob_in_list(self):
        import base64
        from test_capture import PNG
        with patch('capture.enqueue'):
            saved=self.post('/api/capture', {'image_data':'data:image/png;base64,'+base64.b64encode(PNG).decode()})
        with urlopen(self.base+'/api/capture-image?id='+saved['id']) as response:
            self.assertEqual(response.headers['Content-Type'],'image/png');self.assertEqual(response.read(),PNG)
        with urlopen(self.base+'/api/captures') as response:item=json.load(response)['items'][0]
        self.assertTrue(item['has_image']);self.assertNotIn('image',item)
        with urlopen(self.base+'/capture-ui.js') as response:self.assertEqual(response.status,200)


if __name__ == '__main__':
    unittest.main()
