const {test}=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../web/ui');
function button(){const classes=new Set(),attrs={};return {textContent:'保存',disabled:false,style:{minWidth:'2px'},dataset:{},classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x)},setAttribute:(k,v)=>attrs[k]=v,removeAttribute:k=>delete attrs[k],getAttribute:k=>attrs[k],getBoundingClientRect:()=>({width:87.2})};}
test('busy button restores layout, label and enabled state exactly once',()=>{
 const b=button(),end=ui.busyButton(b,'保存中…');
 assert.equal(b.disabled,true);assert.equal(b.style.minWidth,'88px');assert.equal(b.getAttribute('aria-busy'),'true');
 end();end();assert.equal(b.textContent,'保存');assert.equal(b.disabled,false);assert.equal(b.style.minWidth,'2px');assert.equal(b.classList.contains('is-loading'),false);
});
test('computed final label and disabled state survive visual-only loading',()=>{
 const b=button(),end=ui.busyButton(b,'处理中…',{disable:false});b.textContent='读取勾选会话（0）';b.disabled=true;end();
 assert.equal(b.textContent,'读取勾选会话（0）');assert.equal(b.disabled,true);
});
test('duplicate action shares one promise and allows retry after failure',async()=>{
 const b=button();let calls=0,reject;
 const first=ui.run('save',b,'保存中…',()=>{calls++;return new Promise((_,r)=>reject=r);});
 const second=ui.run('save',b,'保存中…',()=>calls++);assert.equal(first,second);
 await Promise.resolve();reject(new Error('failed'));await assert.rejects(first,/failed/);assert.equal(calls,1);assert.equal(b.disabled,false);
 assert.equal(await ui.run('save',b,'保存中…',()=>42),42);
});
test('bound submit prevents navigation synchronously and deduplicates work',async()=>{
 let calls=0,prevented=0,resolve;const b=button(),form={onsubmit:()=>{calls++;return new Promise(r=>resolve=r);}};
 ui.bindAction(form,'onsubmit','form',b,'保存中…');
 const a=form.onsubmit({preventDefault:()=>prevented++}),c=form.onsubmit({preventDefault:()=>prevented++});
 assert.equal(prevented,2);await Promise.resolve();assert.equal(calls,1);resolve();await Promise.all([a,c]);assert.equal(b.disabled,false);
});
test('request distinguishes success, HTTP errors, invalid JSON and network failure',async()=>{
 const original=global.fetch;
 try{
 global.fetch=async()=>({ok:true,status:200,json:async()=>({saved:true})});assert.deepEqual(await ui.request('/api/x'),{saved:true});
 global.fetch=async()=>({ok:false,status:409,json:async()=>({error:'冲突'})});await assert.rejects(ui.request('/api/x'),e=>e.status===409&&e.message==='冲突');
 global.fetch=async()=>({ok:true,status:200,json:async()=>{throw Error('json');}});await assert.rejects(ui.request('/api/x'),e=>e.kind==='format');
 global.fetch=async()=>{throw Error('network');};await assert.rejects(ui.request('/api/x'),e=>e.kind==='network');
 }finally{global.fetch=original;}
});
test('request timeout and cancellation stop waiting without retry',async()=>{
 const original=global.fetch;let calls=0;
 global.fetch=(_,options)=>{calls++;return new Promise((_,reject)=>{if(options.signal.aborted)reject(Error('aborted'));else options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true});});};
 try{
 await assert.rejects(ui.request('/api/x',{timeoutMs:5}),e=>e.kind==='timeout');assert.equal(calls,1);
 const controller=new AbortController();const result=ui.request('/api/x',{signal:controller.signal});controller.abort();await assert.rejects(result,e=>e.kind==='cancelled');assert.equal(calls,2);
 }finally{global.fetch=original;}
});
test('job polling stops at completion and reports actual failure',async()=>{
 let reads=0;const states=[];
 const job=await ui.waitForJob('id',async()=>({status:++reads===2?'completed':'running',result:3}),{interval:1,onState:s=>states.push(s)});
 assert.equal(job.result,3);assert.equal(reads,2);assert.deepEqual(states,['running','completed']);
 await assert.rejects(ui.waitForJob('id',async()=>({status:'failed',error:'失败原因'})),/失败原因/);
});
test('job polling obeys wait deadline and pre-cancelled lifecycle',async()=>{
 let reads=0;await assert.rejects(ui.waitForJob('id',async()=>{reads++;return {status:'running'};},{timeoutMs:0}),e=>e.kind==='timeout');assert.equal(reads,1);
 const controller=new AbortController();controller.abort();await assert.rejects(ui.waitForJob('id',async()=>reads++,{signal:controller.signal}),e=>e.kind==='cancelled');assert.equal(reads,1);
});
test('job cancellation during interval prevents another read',async()=>{
 const controller=new AbortController();let reads=0;
 const result=ui.waitForJob('id',async()=>{reads++;return {status:'running'};},{interval:1000,signal:controller.signal,onState:()=>queueMicrotask(()=>controller.abort())});
 await assert.rejects(result,e=>e.kind==='cancelled');assert.equal(reads,1);
});
test('timeouts reflect actual long operations',()=>{
 assert.equal(ui.requestTimeout('/api/sync'),600000);assert.equal(ui.requestTimeout('/api/wechat/messages'),150000);assert.equal(ui.requestTimeout('/api/state'),25000);
});
