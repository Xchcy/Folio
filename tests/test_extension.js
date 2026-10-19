const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
function runtime(){const events={},drafts={},windows=[];const chrome={runtime:{onInstalled:{addListener:f=>events.install=f},getURL:p=>'chrome-extension://test/'+p},contextMenus:{removeAll:f=>f(),create:x=>events.menu=x,onClicked:{addListener:f=>events.click=f}},storage:{local:{set:async values=>Object.assign(drafts,values)}},scripting:{executeScript:async()=>[{result:{error:true}}]},windows:{getLastFocused:async()=>({left:0,top:0,width:1200}),create:async x=>windows.push(x)},action:{onClicked:{addListener:f=>events.action=f}},commands:{onCommand:{addListener:f=>events.command=f}}};const ctx={chrome,URL,crypto:{randomUUID:()=>String(Object.keys(drafts).length+1)}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('extension/background.js','utf8'),ctx);return {events,drafts,windows,ctx};}
test('context menu only captures selected data with source and does not persist tokens',async()=>{const r=runtime();r.events.install();assert.equal(r.events.menu.title,'收集到 Folio');await vm.runInContext("openCapture({selectionText:'选中文字',pageUrl:'https://example.org/page'}, {title:'示例',id:1})",r.ctx);assert.equal(r.drafts['draft-1'].text,'选中文字');assert.equal(r.drafts['draft-1'].source_title,'示例');assert.equal(r.windows.length,1);assert(!JSON.stringify(r.drafts).includes('token'));});
test('image failure explicitly preserves link rather than claiming original saved',async()=>{const r=runtime();await vm.runInContext("openCapture({srcUrl:'https://example.org/image.png',pageUrl:'https://example.org'}, {id:1})",r.ctx);assert.equal(r.drafts['draft-1'].image_data,'');assert(r.drafts['draft-1'].warning.includes('仅保留图片链接'));});
test('global shortcut starts blank without reading clipboard or current page',async()=>{const r=runtime();await vm.runInContext('openCapture({},null,true)',r.ctx);assert.equal(r.drafts['draft-1'].source_url,'');assert.equal(r.drafts['draft-1'].text,'');});
test('manifest permissions are local and user-triggered',()=>{const m=JSON.parse(fs.readFileSync('extension/manifest.json','utf8').replace(/^\uFEFF/,''));assert.deepEqual(m.host_permissions,['http://127.0.0.1:8771/*']);assert(!m.permissions.includes('clipboardRead'));assert.equal(m.commands['quick-capture'].global,true);});
function captureUiRuntime(fetcher){
 const elements={},storage={'draft-1':{text:'原始选中文字',note:'周五联系对方',source_url:'https://example.org'}};
 function element(id){return elements[id]||(elements[id]={value:'',textContent:'',hidden:false,disabled:false,src:'',listeners:{},addEventListener(name,callback){this.listeners[name]=callback;},replaceChildren(){},append(){},querySelectorAll(){return [];}});}
 const ctx={URL,AbortSignal,TypeError,document:{getElementById:element,createElement:()=>({textContent:"",onclick:null}),addEventListener(){}},location:{href:'chrome-extension://test/capture.html?draft=1'},window:{close(){}},chrome:{storage:{local:{get:async()=>({...storage}),set:async values=>Object.assign(storage,values),remove:async key=>delete storage[key]}}},fetch:fetcher};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('extension/capture.js','utf8'),ctx);return {ctx,elements,storage,element};
}
test('offline capture retains original and image draft, never claims server saved',async()=>{
 const r=captureUiRuntime(async()=>{throw new TypeError('offline');});await vm.runInContext('init()',r.ctx);await vm.runInContext('save()',r.ctx);
 assert.equal(r.storage['draft-1'].text,'原始选中文字');assert(r.element('status').textContent.includes('草稿保留'));assert.equal(r.element('save').disabled,false);
});
test('duplicate response keeps editable draft until user chooses disposition',async()=>{
 let calls=0;const r=captureUiRuntime(async()=>({ok:true,json:async()=>++calls===1?{token:'temporary'}:{duplicate:true,saved:false}}));await vm.runInContext('init()',r.ctx);await vm.runInContext('save()',r.ctx);
 assert.equal(r.element('duplicate').hidden,false);assert(r.storage['draft-1']);assert.equal(r.element('save').disabled,false);
});
test('successful capture clears only its own browser draft after acknowledgement',async()=>{
 let calls=0;const r=captureUiRuntime(async()=>({ok:true,json:async()=>++calls===1?{token:'temporary'}:{saved:true,duplicate:false,id:'capture'}}));r.storage['draft-2']={text:'另一个草稿'};
 await vm.runInContext('init()',r.ctx);await vm.runInContext('save()',r.ctx);assert(!r.storage['draft-1']);assert(r.storage['draft-2']);assert(r.element('status').textContent.includes('已保存'));
});
