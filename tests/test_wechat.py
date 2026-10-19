import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import Memory
import wechat


def fixture(mid='one', sender='我'):
    return dict(id=mid,chat='合成对象',sender=sender,timestamp='2026-10-13T10:00:00+08:00',
        text='我明天交付演示方案',type='text',source='wechat-local',
        locator={'database':'test.db','table':'Msg_test','local_id':1})


class WechatTests(unittest.TestCase):
    def test_refresh_orders_messages_before_extraction_and_preserves_adoption(self):
        root=Path(self.tmp.name)
        (root/'allowed-names.json').write_text(json.dumps(['合成对象']),encoding='utf-8')
        (root/'authorized-chats.json').write_text(json.dumps({'合成对象':'fake'}),encoding='utf-8')
        older={**fixture('older'),'text':'确认演示安排在明天。','timestamp':'2026-10-13T10:00:00+08:00'}
        newer={**fixture('newer'),'text':'好，就按刚才说的时间。','timestamp':'2026-10-13T11:00:00+08:00'}
        payload={'username':'fake','messages':[newer,older],'failures':[],'has_more':False}
        with patch.object(wechat,'AUTHORIZATION_ROOT',root),patch.object(wechat,'bridge',return_value=payload):
            first=wechat.sync(self.memory,selected=['合成对象'])
            reply=next(m for m in self.memory.state()['memories'] if m['message_id']=='newer')
            self.assertIn('older',reply['evidence_ids'])
            self.memory.review(reply['id'],{'status':'confirmed'},'人工采用')
            second=wechat.sync(self.memory,selected=['合成对象'])
        self.assertEqual(first['chats'][0]['added'],2)
        self.assertEqual(second['chats'][0]['added'],0)
        self.assertEqual(second['chats'][0]['duplicates'],2)
        self.assertEqual(second['chats'][0]['candidates'],0)
        self.assertEqual(len(self.memory.state()['messages']),2)
        self.assertEqual(next(m for m in self.memory.state()['memories'] if m['id']==reply['id'])['status'],'confirmed')

    def test_refresh_reports_failed_chat_once_without_success_claim(self):
        root=Path(self.tmp.name)
        (root/'allowed-names.json').write_text(json.dumps(['合成对象']),encoding='utf-8')
        (root/'authorized-chats.json').write_text(json.dumps({'合成对象':'fake'}),encoding='utf-8')
        with patch.object(wechat,'AUTHORIZATION_ROOT',root),patch.object(wechat,'bridge',return_value={'username':'fake','messages':[],'failures':['UnreadableShard']}):
            result=wechat.sync(self.memory,selected=['合成对象'])
        self.assertEqual(len(result['chats']),1)
        self.assertFalse(result['chats'][0]['complete'])
        self.assertEqual(result['chats'][0]['added'],0)

    def test_revoke_blocks_reads_preserves_saved_records_and_invalidates_tickets(self):
        root=Path(self.tmp.name)
        (root/'allowed-names.json').write_text(json.dumps(['合成甲','合成乙']),encoding='utf-8')
        (root/'authorized-chats.json').write_text(json.dumps({'合成甲':'fake-a','合成乙':'fake-b'}),encoding='utf-8')
        self.memory.ingest([fixture()])
        wechat.CHAT_CHOICES['a']={'username':'fake-a','name':'合成甲','expires':time.monotonic()+3600}
        wechat.CHAT_CHOICES['b']={'username':'fake-b','name':'合成乙','expires':time.monotonic()+3600}
        wechat.PREVIEWS['old-preview']={'username':'fake-a','messages':[fixture()],'expires':time.monotonic()+3600}
        with patch.object(wechat,'AUTHORIZATION_ROOT',root),patch.object(wechat,'bridge') as reader:
            self.assertEqual(wechat.revoke_chats(['合成甲'])['revoked'],1)
            self.assertEqual([c['name'] for c in wechat.authorized_chats()['chats']],['合成乙'])
            with self.assertRaises(ValueError):wechat.sync(self.memory,selected=['合成甲'])
            with self.assertRaises(ValueError):wechat.authorize_chats(['a'])
            self.assertNotIn('old-preview',wechat.PREVIEWS)
            self.assertIn('b',wechat.CHAT_CHOICES)
            self.assertEqual(len(self.memory.state()['messages']),1)
            self.assertEqual(wechat.revoke_chats(['合成甲'])['revoked'],0)
            reader.assert_not_called()

    def test_revoke_all_then_regrant_requires_fresh_selection(self):
        root=Path(self.tmp.name)
        (root/'allowed-names.json').write_text(json.dumps(['合成甲']),encoding='utf-8')
        (root/'authorized-chats.json').write_text(json.dumps({'合成甲':'fake-a'}),encoding='utf-8')
        with patch.object(wechat,'AUTHORIZATION_ROOT',root):
            wechat.revoke_chats(['合成甲'])
            self.assertEqual(wechat.authorized_chats()['chats'],[])
            wechat.CHAT_CHOICES['fresh']={'username':'fake-a','name':'合成甲','expires':time.monotonic()+3600}
            wechat.authorize_chats(['fresh'])
            self.assertEqual(len(wechat.authorized_chats()['chats']),1)

    def test_grant_selects_new_wechat_contact_not_only_existing_four(self):
        root=Path(self.tmp.name)
        (root/'allowed-names.json').write_text(json.dumps(['原有对象']),encoding='utf-8')
        (root/'authorized-chats.json').write_text(json.dumps({'原有对象':'fake-original'}),encoding='utf-8')
        with patch.object(wechat,'AUTHORIZATION_ROOT',root),patch.object(wechat,'bridge',return_value={'total':2,'chats':[{'username':'fake-new','name':'新微信对象','is_group':False},{'username':'fake-other','name':'未勾选对象','is_group':False}]}) as reader:
            listing=wechat.search_chats('')
            result=wechat.authorize_chats([listing['chats'][0]['ticket']])
            self.assertEqual(result['selected'],['新微信对象'])
            self.assertEqual(reader.call_count,1)  # Contact metadata only, no history.
            self.assertEqual(reader.call_args.args[0]['action'],'contacts')
            self.assertEqual([c['name'] for c in wechat.authorized_chats()['chats']],['原有对象','新微信对象'])
            wechat.authorize_chats([listing['chats'][0]['ticket']])
            self.assertEqual(len(wechat.authorized_chats()['chats']),2)

    def test_grant_rejects_forged_ticket_and_preserves_same_name_identities(self):
        root=Path(self.tmp.name)
        with patch.object(wechat,'AUTHORIZATION_ROOT',root):
            with self.assertRaises(ValueError):wechat.authorize_chats(['任意账号名'])
            self.assertFalse((root/'allowed-names.json').exists())
            for ticket,username in [('a','fake-a'),('b','fake-b')]:
                wechat.CHAT_CHOICES[ticket]={'username':username,'name':'同名对象','is_group':False,'expires':time.monotonic()+3600}
            granted=wechat.authorize_chats(['a','b'])
            self.assertEqual(len(set(granted['selected'])),2)
            mapping=json.loads((root/'authorized-chats.json').read_text('utf-8'))
            self.assertEqual(set(mapping.values()),{'fake-a','fake-b'})

    def test_authorized_selection_only_reads_checked_chat(self):
        root=Path(self.tmp.name)
        (root/'allowed-names.json').write_text(json.dumps(['合成甲','合成乙']),encoding='utf-8')
        (root/'authorized-chats.json').write_text(json.dumps({'合成甲':'fake-a','合成乙':'fake-b'}),encoding='utf-8')
        with patch.object(wechat,'AUTHORIZATION_ROOT',root),patch.object(wechat,'bridge',return_value={'username':'fake-b','messages':[],'failures':[]}) as reader:
            listed=wechat.authorized_chats()
            self.assertEqual([c['name'] for c in listed['chats']],['合成甲','合成乙'])
            reader.assert_not_called()
            result=wechat.sync(self.memory,selected=['合成乙'])
            self.assertEqual([c['name'] for c in result['chats']],['合成乙'])
            self.assertEqual(reader.call_args.args[0]['username'],'fake-b')

    def test_authorized_selection_rejects_empty_or_unknown_before_read(self):
        root=Path(self.tmp.name)
        (root/'allowed-names.json').write_text(json.dumps(['合成甲']),encoding='utf-8')
        with patch.object(wechat,'AUTHORIZATION_ROOT',root),patch.object(wechat,'bridge') as reader:
            for selected in ([],['未授权对象'],'合成甲'):
                with self.subTest(selected=selected),self.assertRaises(ValueError):wechat.sync(self.memory,selected=selected)
            reader.assert_not_called()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.memory=Memory(self.root/'private.sqlite3')
        self.alias_patch=patch.object(wechat,'CONTACT_ALIASES_PATH',self.root/'contact-aliases.json')
        self.alias_patch.start()
        self.addCleanup(self.alias_patch.stop)
        wechat.PREVIEWS.clear();wechat.CHAT_CHOICES.clear()

    def tearDown(self):
        wechat.PREVIEWS.clear();wechat.CHAT_CHOICES.clear()
        self.tmp.cleanup()

    def preview(self, ticket='preview', messages=None):
        wechat.PREVIEWS[ticket]={'messages':messages or [fixture()], 'chat':'合成对象',
            'username':'synthetic', 'expires':time.monotonic()+3600}

    def test_selected_only_and_duplicates(self):
        self.preview(messages=[fixture(),fixture('two')])
        request=[{'preview':'preview','ids':['one']}]
        result=wechat.import_selected(self.memory,request,self.root)
        self.assertEqual(result,{'selected':1,'added':1,'duplicates':0})
        self.assertEqual([m['id'] for m in self.memory.state()['messages']],['one'])
        batch=json.loads(next(self.root.glob('selected-*.json')).read_text('utf-8'))
        self.assertEqual(len(batch['messages']),1)
        self.assertEqual(batch['messages'][0]['locator']['local_id'],1)
        self.assertEqual(wechat.import_selected(self.memory,request,self.root)['duplicates'],1)

    def test_import_retains_original_wechat_time_to_second(self):
        original=fixture()
        original.update(timestamp='2025-05-31T13:44:59+08:00',original_timestamp=1748670299)
        self.preview(messages=[original])
        request=[{'preview':'preview','ids':['one'],'timestamp':'2026-10-13T23:00:00+08:00'}]
        wechat.import_selected(self.memory,request,self.root)
        self.assertEqual(self.memory.state()['messages'][0]['timestamp'],original['timestamp'])
        batch=json.loads(next(self.root.glob('selected-*.json')).read_text('utf-8'))
        self.assertEqual(batch['messages'][0]['original_timestamp'],1748670299)
        self.assertEqual(batch['messages'][0]['timestamp'],original['timestamp'])
        wechat.import_selected(self.memory,request,self.root)
        self.assertEqual(self.memory.state()['messages'][0]['timestamp'],original['timestamp'])

    def test_forged_or_expired_selection_does_not_write(self):
        self.preview()
        for request in ([{'preview':'preview','ids':['forged']}], [{'preview':'missing','ids':['one']}],
                        [{'preview':'preview','ids':['one']},{'preview':'missing','ids':['one']}]):
            with self.assertRaises(ValueError):wechat.import_selected(self.memory,request,self.root)
        self.assertEqual(self.memory.state()['messages'],[])
        self.assertFalse(list(self.root.glob('selected-*.json')))

    def test_multi_page_dedup_and_no_client_text(self):
        self.preview('p1',[fixture()]);self.preview('p2',[fixture(),fixture('two')])
        result=wechat.import_selected(self.memory,[{'preview':'p1','ids':['one'],'text':'forged'},
            {'preview':'p2','ids':['one','two']}],self.root)
        self.assertEqual(result['added'],2)
        self.assertTrue(all(m['text']=='我明天交付演示方案' for m in self.memory.state()['messages']))

    def test_search_issues_opaque_ticket(self):
        with patch.object(wechat,'bridge',return_value={'total':1,'chats':[{'username':'secret-id','name':'合成对象','is_group':False}]}):
            result=wechat.search_chats('合成')
        self.assertNotIn('secret-id',json.dumps(result))
        self.assertEqual(wechat.CHAT_CHOICES[result['chats'][0]['ticket']]['username'],'secret-id')
        self.assertEqual(result['chats'][0]['account_hint'],'…ret-id')

    def test_same_nickname_accounts_keep_distinct_identities(self):
        chats=[{'username':'fake-old-111111','name':'旧备注','nickname':'合成昵称','is_group':False},
               {'username':'fake-new-222222','name':'新备注','nickname':'合成昵称','is_group':False}]
        with patch.object(wechat,'bridge',return_value={'total':2,'chats':chats}):
            result=wechat.search_chats('合成昵称')
        self.assertEqual(len({c['account_hint'] for c in result['chats']}),2)
        self.assertEqual(len({c['ticket'] for c in result['chats']}),2)
        self.assertEqual([c['nickname'] for c in result['chats']],['合成昵称','合成昵称'])

    def test_confirmed_alias_search_includes_both_accounts(self):
        config={'people':[{'name':'合成伙伴','accounts':[{'username':'fake-new-222222','role':'current'},
            {'username':'fake-old-111111','role':'previous'}]}]}
        wechat.CONTACT_ALIASES_PATH.write_text(json.dumps(config),'utf-8')
        chats=[{'username':'fake-new-222222','name':'新的微信备注','nickname':'合成昵称','is_group':False},
               {'username':'fake-old-111111','name':'原来的备注','nickname':'合成昵称','is_group':False}]
        with patch.object(wechat,'bridge',return_value={'total':2,'chats':chats}) as mocked:
            result=wechat.search_chats('合成伙伴')
        self.assertEqual(mocked.call_args.args[0]['extra_usernames'],['fake-new-222222','fake-old-111111'])
        self.assertEqual(result['chats'][0]['name'],'合成伙伴（当前账号）')
        self.assertEqual(result['chats'][1]['name'],'合成伙伴（旧账号）')
        self.assertEqual(result['chats'][0]['wechat_name'],'新的微信备注')
        self.assertNotEqual(wechat.CHAT_CHOICES[result['chats'][0]['ticket']]['username'],
                            wechat.CHAT_CHOICES[result['chats'][1]['ticket']]['username'])

    def test_alias_config_rejects_invalid_roles(self):
        wechat.CONTACT_ALIASES_PATH.write_text(json.dumps({'people':[{'name':'合成伙伴','accounts':[{'username':'fake','role':'guess'}]}]}),'utf-8')
        with patch.object(wechat,'bridge') as mocked,self.assertRaises(ValueError):wechat.search_chats('合成伙伴')
        mocked.assert_not_called()

    def test_filters_and_identity_validation(self):
        wechat.CHAT_CHOICES['chat']={'username':'synthetic','name':'合成对象','expires':time.monotonic()+3600}
        with patch.object(wechat,'bridge',return_value={'username':'synthetic','messages':[fixture()],
            'failures':[],'has_more':True,'next_offset':100,'scanned':100}) as mocked:
            result=wechat.preview_messages('chat',filters={'mine':True,'start':'2026-10-01'})
            self.assertTrue(mocked.call_args.args[0]['filters']['mine'])
            self.assertEqual(result['next_offset'],100)
            self.assertIn(result['preview'],wechat.PREVIEWS)
        with patch.object(wechat,'bridge') as mocked:
            for filters in ({'start':'bad'},{'start':'2026-10-13','end':'2026-10-01'},{'mine':'true'}):
                with self.assertRaises(ValueError):wechat.preview_messages('chat',filters=filters)
            mocked.assert_not_called()
        with patch.object(wechat,'bridge',return_value={'username':'wrong'}):
            with self.assertRaises(ValueError):wechat.preview_messages('chat')

    def test_partial_read_is_not_importable(self):
        wechat.CHAT_CHOICES['chat']={'username':'synthetic','name':'合成对象','expires':time.monotonic()+3600}
        with patch.object(wechat,'bridge',return_value={'username':'synthetic','messages':[fixture()],'failures':['OSError']}):
            with self.assertRaises(ValueError):wechat.preview_messages('chat')
        self.assertFalse(wechat.PREVIEWS)

    def test_more_contacts_does_not_expire_previous_page(self):
        chats=[{'username':f'fake-{i}','name':f'合成 {i}','is_group':False} for i in range(100)]
        with patch.object(wechat,'bridge',return_value={'chats':chats,'total':200}):
            first=wechat.search_chats()
            wechat.search_chats(offset=100)
        wechat.cleanup()
        self.assertIn(first['chats'][0]['ticket'],wechat.CHAT_CHOICES)

    def test_database_date_and_sender_filters(self):
        import sqlite3
        from contextlib import closing
        import wechat_bridge as wb
        from datetime import datetime,timezone,timedelta
        from types import SimpleNamespace
        import hashlib
        table='Msg_'+hashlib.md5(b'fake').hexdigest()
        path=self.root/'messages.db'
        tz=timezone(timedelta(hours=8))
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(f'CREATE TABLE {table}(local_id INTEGER,local_type INTEGER,create_time INTEGER,real_sender_id INTEGER,message_content TEXT,WCDB_CT_message_content INTEGER)')
            for i,date in enumerate(['2026-10-12T23:59:00','2026-10-13T00:00:00','2026-10-13T23:59:00','2026-10-14T00:00:00']):
                db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?)',(i,1,int(datetime.fromisoformat(date).replace(tzinfo=tz).timestamp()),1,'合成方案',0))
        app=SimpleNamespace(msg_db_keys=['message/message_0.db'],db_dir=str(self.root),cache=SimpleNamespace(get=lambda rel:str(path)),decrypted_dir='',display_name_fn=None)
        with patch.object(wb,'AppContext',return_value=app),patch.object(wb,'get_contact_names',return_value={}),\
             patch.object(wb,'_load_name2id_maps',return_value={}),patch.object(wb,'decompress_content',side_effect=lambda content,ct:content),\
             patch.object(wb,'_format_message_text',return_value=('me','合成方案')),patch.object(wb,'_resolve_sender_label',return_value='me'):
            result=wb.history('fake',100,0,{'start':'2026-10-13','end':'2026-10-13','mine':True,'query':'方案'})
        self.assertFalse(result['failures'])
        self.assertEqual([m['locator']['local_id'] for m in result['messages']],[2,1])
        self.assertEqual(result['scanned'],2)

    def shard_history(self, rows_by_shard, **request):
        import sqlite3, hashlib
        from contextlib import closing, ExitStack
        from types import SimpleNamespace
        import wechat_bridge as wb
        folder=self.root/'message'
        folder.mkdir(exist_ok=True)
        table='Msg_'+hashlib.md5(b'fake').hexdigest()
        paths={}
        for index,rows in enumerate(rows_by_shard):
            path=folder/f'message_{index}.db';paths[f'message/{path.name}']=str(path)
            with closing(sqlite3.connect(path)) as db,db:
                db.execute(f'CREATE TABLE [{table}](local_id INTEGER,local_type INTEGER,create_time INTEGER,real_sender_id INTEGER,message_content TEXT,WCDB_CT_message_content INTEGER)')
                db.executemany(f'INSERT INTO [{table}] VALUES(?,1,?,?,?,0)',rows)
        # Only one known key: remaining physical shards must still be checked.
        app=SimpleNamespace(msg_db_keys=['message/message_0.db'],db_dir=str(self.root),
            cache=SimpleNamespace(get=lambda rel:paths.get(rel)),decrypted_dir='',display_name_fn=None)
        with ExitStack() as stack:
            stack.enter_context(patch.object(wb,'AppContext',return_value=app))
            stack.enter_context(patch.object(wb,'get_contact_names',return_value={'fake':'合成对象'}))
            stack.enter_context(patch.object(wb,'_load_name2id_maps',return_value={}))
            stack.enter_context(patch.object(wb,'decompress_content',side_effect=lambda content,ct:content))
            stack.enter_context(patch.object(wb,'_format_message_text',side_effect=lambda mid,kind,text,*args:('',text)))
            stack.enter_context(patch.object(wb,'_resolve_sender_label',side_effect=lambda sid,*args:'me' if sid==1 else '伙伴'))
            return wb.history('fake',request.get('limit',100),request.get('offset',0),request.get('filters'),request.get('exact_total',False))

    def test_search_finds_messages_beyond_first_hundred(self):
        rows=[(i,1700000000+i,1 if i%2==0 else 2,'更早的目标' if i<10 else '普通内容') for i in range(350)]
        result=self.shard_history([rows],filters={'query':'目标','mine':True})
        self.assertEqual(len(result['messages']),5)
        self.assertEqual(result['matched_total'],5)
        self.assertFalse(result['has_more'])
        self.assertEqual(result['total'],350)
        self.assertEqual(result['scanned'],350)

    def test_filtered_offset_is_matching_offset(self):
        rows=[(i,1700000000+i,1 if i%2==0 else 2,'内容') for i in range(350)]
        result=self.shard_history([rows],offset=100,filters={'mine':True})
        self.assertEqual(len(result['messages']),75)
        self.assertEqual(result['matched_total'],175)
        self.assertEqual(result['next_offset'],175)
        self.assertFalse(result['has_more'])

    def test_all_shards_and_equal_timestamps_paginate_without_loss(self):
        rows=[[(i,1700000000,1,'内容') for i in range(130)],[(i,1700000000,1,'内容') for i in range(130)]]
        first=self.shard_history(rows)
        self.assertEqual(first['total'],260)
        self.assertEqual(first['table_count'],2)
        self.assertTrue(first['has_more'])
        # Reuse the created shards for later pages without rebuilding them.
        import wechat_bridge as wb
        from types import SimpleNamespace
        app=SimpleNamespace(msg_db_keys=['message/message_0.db'],db_dir=str(self.root),
            cache=SimpleNamespace(get=lambda rel:str(self.root/rel)),decrypted_dir='',display_name_fn=None)
        with patch.object(wb,'AppContext',return_value=app),patch.object(wb,'get_contact_names',return_value={}),\
             patch.object(wb,'_load_name2id_maps',return_value={}),patch.object(wb,'_resolve_sender_label',return_value='me'):
            second=wb.history('fake',100,100)
            third=wb.history('fake',100,200)
        messages=first['messages']+second['messages']+third['messages']
        self.assertEqual(len(messages),260)
        self.assertEqual(len({m['id'] for m in messages}),260)
        self.assertFalse(third['has_more'])

    def test_unreadable_shard_is_reported(self):
        import wechat_bridge as wb
        from types import SimpleNamespace
        app=SimpleNamespace(msg_db_keys=['message/message_0.db'],db_dir=str(self.root),
            cache=SimpleNamespace(get=lambda rel:None),decrypted_dir='',display_name_fn=None)
        with patch.object(wb,'AppContext',return_value=app),patch.object(wb,'get_contact_names',return_value={}):
            result=wb.history('fake',100,0)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['failures']),1)

    def test_exact_filtered_count_for_page_navigation(self):
        rows=[(i,1700000000+i,1 if i%2==0 else 2,'内容') for i in range(350)]
        result=self.shard_history([rows],limit=20,filters={'mine':True},exact_total=True)
        self.assertEqual(len(result['messages']),20)
        self.assertEqual(result['matched_total'],175)
        self.assertTrue(result['has_more'])

    def test_twenty_row_last_page_reaches_oldest(self):
        rows=[(i,1700000000+i,1,'内容') for i in range(195)]
        result=self.shard_history([rows],limit=20,offset=180,exact_total=True)
        self.assertEqual(len(result['messages']),15)
        self.assertEqual(result['messages'][-1]['timestamp'],result['date_start'])
        self.assertFalse(result['has_more'])

    def test_preview_page_clamps_and_uses_twenty(self):
        wechat.CHAT_CHOICES['chat']={'username':'synthetic','name':'合成对象','expires':time.monotonic()+3600}
        result={'username':'synthetic','messages':[],'failures':[],'matched_total':195}
        with patch.object(wechat,'bridge',return_value=result) as mocked:
            data=wechat.preview_messages('chat',page=99)
        self.assertEqual(data['page'],10)
        self.assertEqual(data['total_pages'],10)
        self.assertEqual(data['page_size'],20)
        self.assertEqual(mocked.call_args.args[0]['offset'],180)
        self.assertTrue(mocked.call_args.args[0]['exact_total'])
        self.assertEqual(mocked.call_args.args[0]['limit'],20)

    def test_invalid_pages_and_empty_page_count(self):
        wechat.CHAT_CHOICES['chat']={'username':'synthetic','name':'合成对象','expires':time.monotonic()+3600}
        with patch.object(wechat,'bridge') as mocked:
            for page in (0,-1,True,1.5,'2',50001):
                with self.assertRaises(ValueError):wechat.preview_messages('chat',page=page)
            mocked.assert_not_called()
        with patch.object(wechat,'bridge',return_value={'username':'synthetic','messages':[],'failures':[],'matched_total':0}):
            result=wechat.preview_messages('chat',page=1)
        self.assertEqual(result['total_pages'],0)
        self.assertEqual(result['page'],0)



if __name__=='__main__':unittest.main()
