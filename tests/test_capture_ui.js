const {test}=require('node:test');
const assert=require('node:assert/strict');

test('modular capture keeps Chinese text readable and opens the inbox after saving',async()=>{
  const {initCapture}=await import('../web/capture-ui.js');
  const elements=new Map(),notifications=[];
  function element(id){
    if(!elements.has(id))elements.set(id,{
      value:'',textContent:'',innerHTML:'',hidden:false,disabled:false,open:false,dataset:{},
      classList:{remove(){}},addEventListener(){},setAttribute(){},removeAttribute(){},
      querySelector(){return null;},focus(){},reset(){},
      showModal(){this.open=true;},close(){this.open=false;}
    });
    return elements.get(id);
  }
  const item={id:'synthetic-capture',title:'中文原话 <img onerror=bad>',text:'周五买水果',note:'',
    ocr_text:'',topic:'随手记',category:'note',state:'ready',created_at:'2026-10-17T10:00:00+08:00',
    deleted_at:'',method:'本机规则',memory_ids:[]};
  const previous={document:global.document,window:global.window,location:global.location,MemoryUI:global.MemoryUI};
  try{
    global.document={getElementById:element,addEventListener(){}};
    global.window={addEventListener(){}};
    global.location={hash:'#workspace'};
    global.MemoryUI={region:()=>()=>{},bindAction(){},request:async path=>{
      if(path==='/api/capture-connection')return {token:'test-token'};
      if(path==='/api/capture')return {saved:true};
      if(path==='/api/captures')return {items:[item]};
      throw Error('Unexpected request: '+path);
    }};
    element('inbox-filter').value='all';
    const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    initCapture({$:element,escape,toast:message=>notifications.push(message),load:async()=>{},state:{mode:'private'}});
    element('quick-capture').onclick();
    element('capture-text').value='周五买水果';
    await element('capture-form').onsubmit({preventDefault(){}});
    assert.equal(element('capture-dialog').open,false);
    assert.equal(element('inbox-dialog').open,true);
    assert.equal(element('capture-save').disabled,false);
    assert.match(notifications.join(''),/已保存到本机收集箱/);
    assert.match(element('inbox-items').innerHTML,/中文原话 &lt;img onerror=bad&gt;/);
    assert.match(element('inbox-items').innerHTML,/周五买水果/);
    assert.doesNotMatch(element('inbox-items').innerHTML,/%u[0-9A-F]{4}|<img onerror=bad>/);
  }finally{
    for(const [name,value] of Object.entries(previous)){
      if(value===undefined)delete global[name];else global[name]=value;
    }
  }
});
