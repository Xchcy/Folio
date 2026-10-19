const {test}=require('node:test');
const assert=require('node:assert/strict');
const todos=require('../web/todos');
const item=(id,changes={})=>({id,kind:'task',subject:'我',status:'pending',event:'promise',timestamp:'2026-10-15T10:00:00+08:00',...changes});
test('only actionable personal tasks; completion and cancellation are evidence, not new tasks',()=>{
 const data=[item('mine'),item('other',{subject:'同事'}),item('done',{status:'completed'}),item('ignored',{status:'dismissed'}),item('cancel',{event:'cancellation'}),item('report',{event:'completion'}),item('fact',{kind:'fact'})];
 assert.deepEqual(todos.select(data).map(x=>x.id),['mine']);
 assert.deepEqual(todos.select(data,'completed').map(x=>x.id),['done']);
});
test('candidate replacement does not hide confirmed original, confirmed replacement does',()=>{
 const old=item('old',{status:'confirmed'}),candidate=item('new',{supersedes:'old'});
 assert.equal(todos.select([old,candidate]).length,2);
 assert.deepEqual(todos.select([old,{...candidate,status:'confirmed'}]).map(x=>x.id),['new']);
});
test('date order, undated last, no mutation, candidate filter',()=>{
 const data=[item('undated'),item('later',{due:'2026-10-17'}),item('early',{due:'2026-10-14',status:'confirmed'})];
 assert.deepEqual(todos.select(data).map(x=>x.id),['early','later','undated']);
 assert.deepEqual(data.map(x=>x.id),['undated','later','early']);
 assert.deepEqual(todos.select(data,'pending').map(x=>x.id),['later','undated']);
});
test('Shanghai date boundary and associated date does not claim a deadline',()=>{
 assert.equal(todos.today(new Date('2026-10-14T17:00:00Z')),'2026-10-15');
 assert.equal(todos.dueLabel(item('today',{due:'2026-10-15'}),'2026-10-15'),'关联今天');
 assert.equal(todos.dueLabel(item('past',{due:'2026-10-14'}),'2026-10-15'),'关联日期已过 · 2026-10-14');
});

test('waiting, proposals and cancellation stay distinct from my commitments',()=>{
 const data=[item('mine'),item('waiting',{subject:'小李'}),item('proposal',{kind:'question',event:'proposal',subject:'待确认执行人'}),item('cancelled',{kind:'question',event:'cancellation'}),item('uncertain',{subject:'小李',task_role:'waiting',certainty:'uncertain'})];
 assert.deepEqual(todos.select(data,'active').map(m=>m.id),['mine']);
 assert.deepEqual(todos.select(data,'waiting').map(m=>m.id),['uncertain','waiting']);
 assert.deepEqual(todos.select(data,'proposal').map(m=>m.id),['proposal']);
 assert.deepEqual(todos.select(data,'cancelled').map(m=>m.id),['cancelled']);
 assert.equal(todos.select(data,'pending').length,5);
 assert.equal(todos.canAdopt(data[4]),false);
 assert.equal(todos.traits(data[1]).roleLabel,'等别人');
});

test('unknown assignee cannot be adopted and event dates never claim overdue',()=>{
 const unknown=item('unknown',{subject:'我们'});
 assert.equal(todos.canAdopt(unknown),false);
 assert.equal(todos.traits(unknown).certainty,'uncertain');
 assert.equal(todos.dueLabel(item('event',{date_kind:'event',due:'2026-10-10'}),'2026-10-16'),'活动时间 2026-10-10');
});
