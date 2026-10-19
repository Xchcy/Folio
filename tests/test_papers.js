const {test}=require('node:test');
const assert=require('node:assert/strict');
test('paper dots retain the type alongside confirmation, waiting and completion',async()=>{
  const {paperStatuses,paperNote}=await import('../web/papers.js');
  const task={kind:'task',task_role:'mine',status:'pending'};
  const tones=m=>paperStatuses(m).map(dot=>dot.tone);
  assert.deepEqual(tones(task),['active','pending']);
  assert.deepEqual(tones({...task,status:'confirmed'}),['active']);
  assert.deepEqual(tones({...task,task_role:'waiting'}),['active','waiting','pending']);
  assert.deepEqual(tones({...task,status:'completed'}),['active','complete']);
  assert.deepEqual(tones({...task,status:'dismissed'}),['active','muted']);
  assert.deepEqual(tones({kind:'fact',event:'completion',status:'pending'}),['source','pending']);
  const status=[...paperStatuses(task),...paperStatuses(task)];
  const html=paperNote(task,{body:'',key:'source:a',status});
  assert.equal((html.match(/role="img"/g)||[]).length,2);
  assert.ok(!html.includes('<span>待确认</span>'));
});

test('paper defaults to collapsed, escapes summaries and preserves evidence body separately',async()=>{
  const {paperNote}=await import('../web/papers.js');
  const html=paperNote({id:'a',status:'pending',title:'<script>bad</script>',timestamp:'2026-10-17T10:00:00'},{body:'<p>原话</p>',key:'memory:a',record:true});
  assert.ok(html.includes('<details class="paper-note"'));
  assert.ok(!html.includes(' open'));
  assert.ok(html.includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert.ok(html.indexOf('原话</p>')>html.indexOf('</summary>'));
  assert.ok(html.includes('本机简述'));
  assert.ok(!html.includes('AI 摘要'));
});
