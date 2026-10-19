const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createEntrance}=require('../web/home');
test('repeated book clicks share one transition and commit navigation once',async()=>{
 let resolve,plays=0,entries=0;
 const gate=createEntrance({play:()=>{plays++;return new Promise(r=>resolve=r);},enter:()=>entries++});
 const first=gate.open(),second=gate.open();assert.equal(first,second);await Promise.resolve();assert.equal(plays,1);resolve();await first;assert.equal(entries,1);assert.equal(gate.active,false);
});
test('broken animation still lets the user reach the workspace',async()=>{
 let entered=0,errors=0;
 const gate=createEntrance({play:()=>Promise.reject(Error('animation unavailable')),enter:()=>entered++,onError:()=>errors++});
 await gate.open();assert.equal(entered,1);assert.equal(errors,1);assert.equal(gate.active,false);
});
test('Escape cancels entry and a later click can open normally',async()=>{
 let entered=0,finish;
 const gate=createEntrance({play:signal=>new Promise((resolve,reject)=>{finish=resolve;signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true});}),enter:()=>entered++});
 const first=gate.open();await Promise.resolve();gate.cancel();await first;assert.equal(entered,0);
 const second=gate.open();await Promise.resolve();finish();await second;assert.equal(entered,1);
});
test('immediate bypass does not start a stale animation or change the route',async()=>{
 let played=0,entered=0;const gate=createEntrance({play:()=>played++,enter:()=>entered++});
 const pending=gate.open();gate.cancel();await pending;assert.equal(played,0);assert.equal(entered,0);
});
