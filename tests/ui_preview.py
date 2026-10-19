"""Local UI fixture: synthetic contacts and messages, disposable data, no WeChat access."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['MEMORY_LOCAL_MODEL'] = ''

import capture
import server
import wechat


def bridge(request):
    if request['action'] == 'contacts':
        return {'total': 1, 'chats': [{'username': 'synthetic-ui-contact', 'name': '合成测试对象',
                                     'nickname': '合成昵称', 'is_group': False}]}
    if request['action'] == 'history':
        return {'username': request['username'], 'failures': [], 'total': 3, 'matched_total': 3, 'has_more':False,
                'date_start': '2026-10-17T10:00:00+08:00', 'date_end': '2026-10-17T12:00:00+08:00',
                'messages': [{'id': 'synthetic-ui-message', 'chat': '合成测试对象', 'sender': '我',
                              'timestamp': '2026-10-17T11:00:00+08:00', 'text': '我明天整理测试方案',
                              'type': 'text', 'source': 'wechat-local',
                              'locator': {'database': 'synthetic.db', 'table': 'Msg_test', 'local_id': 1}},
                             {'id':'synthetic-moved-task','chat':'合成测试对象','sender':'我','timestamp':'2026-10-17T10:00:00+08:00',
                              'text':'我负责提交演示材料。','type':'text','source':'wechat-local'},
                             {'id':'synthetic-casual','chat':'合成测试对象','sender':'合成伙伴','timestamp':'2026-10-17T12:00:00+08:00',
                              'text':'哈哈哈','type':'text','source':'wechat-local'}]}
    raise ValueError('The UI fixture only supports synthetic contact and history requests.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8777)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='memory-ui-') as temp:
        server.DATA_ROOT = Path(temp)
        wechat.AUTHORIZATION_ROOT = Path(temp)
        wechat.CONTACT_ALIASES_PATH = Path(temp) / 'contact-aliases.json'
        wechat.bridge = bridge
        memory = server.store('private')
        memory.ingest([{'id':'synthetic-moved-task','chat':'合成测试对象','topic':'合成测试对象','sender':'我',
                        'timestamp':'2026-10-17T10:00:00+08:00','text':'我负责提交演示材料。','type':'text','source':'wechat-local'}])
        memory.review('mem-synthetic-moved-task',{'topic':'演示准备（合成）'},'复现人工归入其他事项；状态仍待确认')
        with patch('engine.extract_task_date_change',return_value=None):
            memory.ingest([{'id':'synthetic-date-original','chat':'合成改期会话','sender':'我','timestamp':'2026-10-17T20:05:08+08:00',
                            'text':'我现在去整理，周五给你','type':'text','source':'wechat-local'},
                           {'id':'synthetic-date-request','chat':'合成改期会话','sender':'合成伙伴','timestamp':'2026-10-17T21:31:28+08:00',
                            'text':'提前一点，周三给我','type':'text','source':'wechat-local'}])
        (Path(temp)/'allowed-names.json').write_text(json.dumps(['合成测试对象']),encoding='utf-8')
        (Path(temp)/'authorized-chats.json').write_text(json.dumps({'合成测试对象':'synthetic-ui-contact'}),encoding='utf-8')
        for text in ['我负责明天整理测试方案', '合成参考资料']:
            result = capture.save(memory, {'text': text})
            capture.process(memory, result['id'])
            if text.startswith('我负责'):
                capture.promote(memory, result['id'])
        http = server.ThreadingHTTPServer(('127.0.0.1', args.port), server.Handler)
        print(f'Synthetic UI preview: http://127.0.0.1:{http.server_port}/#home', flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            http.server_close()


if __name__ == '__main__':
    main()
