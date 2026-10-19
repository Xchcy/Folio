const $=id=>document.getElementById(id);
const base='http://127.0.0.1:8771';
let draftId=new URL(location.href).searchParams.get('draft'),draft={},imageData='',busy=false;
async function readFile(file){
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>4000000)throw new Error('请选择 4 MB 以内的 PNG、JPEG 或 WebP 图片');
  return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('图片读取失败'));reader.readAsDataURL(file);});
}
function showImage(value){imageData=value;$('image-wrap').hidden=!value;$('image').src=value||'';}
function payload(){const original=$('original').value;return {...draft,text:$('text').value,note:$('note').value,source_url:$('source-url').value,source_title:$('source-title').value,original_at:original?original+':00+08:00':'',image_data:imageData};}
async function keepDraft(){if(draftId)await chrome.storage.local.set({['draft-'+draftId]:payload()});}
async function init(){
  const all=await chrome.storage.local.get(null);draft=all['draft-'+draftId]||{};
  $('text').value=draft.text||'';$('note').value=draft.note||'';$('source-url').value=draft.source_url||'';$('source-title').value=draft.source_title||'';$('original').value=(draft.original_at||'').slice(0,16);showImage(draft.image_data||'');$('status').textContent=draft.warning||'保存后会自动记录时间，并在本机整理分类。';
  const others=Object.entries(all).filter(([key])=>key.startsWith('draft-')&&key!=='draft-'+draftId);
  $('draft-list').hidden=!others.length;$('draft-items').replaceChildren();
  for(const [key,value] of others){const button=document.createElement('button');button.textContent=(value.note||value.text||value.source_title||'图片草稿').slice(0,65);button.onclick=()=>{location.href='capture.html?draft='+encodeURIComponent(key.slice(6));};$('draft-items').append(button);}
}
$('form').addEventListener('input',()=>keepDraft().catch(()=>{$('status').textContent='浏览器草稿保存失败，请尽快保存到Folio。';}));
$('file').onchange=async e=>{try{if(e.target.files[0]){showImage(await readFile(e.target.files[0]));await keepDraft();}}catch(err){$('status').textContent=err.message;}e.target.value='';};
document.addEventListener('paste',async e=>{const file=[...e.clipboardData.items].find(x=>x.type.startsWith('image/'))?.getAsFile();if(!file)return;e.preventDefault();try{showImage(await readFile(file));await keepDraft();}catch(err){$('status').textContent=err.message;}});
$('remove-image').onclick=async()=>{showImage('');await keepDraft();};
$('cancel').onclick=()=>window.close();
async function save(duplicate='ask'){
  if(busy)return;busy=true;$('save').disabled=true;$('status').textContent='正在保存到本机…';
  try{
    await keepDraft();
    let response=await fetch(base+'/api/capture-connection',{signal:AbortSignal.timeout(5000)});
    if(!response.ok)throw new Error('请先启动新版Folio');
    const {token}=await response.json();
    response=await fetch(base+'/api/capture',{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Token':token},body:JSON.stringify({...payload(),duplicate}),signal:AbortSignal.timeout(15000)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'保存失败');
    if(result.duplicate&&!result.saved){$('duplicate').hidden=false;$('status').textContent='这条内容已收集过，可追加说明或再次保存。';return;}
    await chrome.storage.local.remove('draft-'+draftId).catch(()=>{});draftId=null;$('duplicate').hidden=true;$('status').textContent='已保存，正在整理。可关闭窗口继续工作，稍后在收集箱查看。';$('save').textContent='已保存';$('form').querySelectorAll('input,textarea,button').forEach(x=>x.disabled=true);
  }catch(err){$('status').textContent=err instanceof TypeError||err.name==='TimeoutError'?'暂时连接不到Folio。草稿保留在浏览器中，请启动本机服务后重试。':err.message;}
  finally{busy=false;if(draftId)$('save').disabled=false;}
}
$('form').onsubmit=e=>{e.preventDefault();save();};$('append').onclick=()=>save('append');$('copy').onclick=()=>save('copy');
init().catch(err=>{$('status').textContent='草稿加载失败：'+err.message;});
