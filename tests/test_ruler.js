const {test}=require('node:test');
const assert=require('node:assert/strict');
const todos=require('../web/todos.js');

test('home ruler contains only current confirmed unfinished tasks, including waiting',async()=>{
  const {unfinishedItems}=await import('../web/features/ruler.js');
  const base={kind:'task',task_role:'mine',subject:'我',certainty:'explicit',status:'confirmed',timestamp:'2026-10-18T12:00:00'};
  const items=[
    {...base,id:'old'},
    {...base,id:'new',supersedes:'old',due:'2026-10-22'},
    {...base,id:'pending',status:'pending'},
    {...base,id:'done',status:'completed'},
    {...base,id:'ignored',status:'dismissed'},
    {...base,id:'fact',kind:'fact'},
    {...base,id:'wait',task_role:'waiting',subject:'小李',due:'2026-10-21'},
    {...base,id:'cancelled',event:'cancellation'},
    {...base,id:'uncertain',task_role:'unknown',certainty:'uncertain'},
  ];
  assert.deepEqual(unfinishedItems(items,todos).map(m=>m.id),['wait','new']);
  assert.equal(items[0].id,'old');
  assert.deepEqual(unfinishedItems([],todos),[]);
});
