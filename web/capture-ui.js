export function initCapture(ctx) {
  const {$,load,showEvidence,escape,toast}=ctx;
  const byId=id=>document.getElementById(id);
  const names={todo:'待办',note:'笔记',reference:'资料',idea:'灵感',unclassified:'待整理'};
  const statuses={saved:'等待整理',processing:'正在整理',ready:'已整理',failed:'整理待重试'};
  let imageData='',items=[],current=null,saveBusy=false,poll,inboxRequest,inboxVersion=0,inboxSignature='';
  let deletedView=false,inboxChanging=false;
  const selectedCaptures=new Set();
  async function request(path,body,options={}) {
    const {token}=await MemoryUI.request('/api/capture-connection',options);
    return MemoryUI.request(path,{...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Token':token},body:JSON.stringify(body)}:{}),...options});
  }
  function imageFile(file) {
    return new Promise((resolve,reject)=>{
      if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>4000000)return reject(new Error('请选择 4 MB 以内的 PNG、JPEG 或 WebP 图片'));
      const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('图片读取失败'));reader.readAsDataURL(file);
    });
  }
  let imageVersion=0,imagePending=0;
  function showImage(value){++imageVersion;imageData=value;byId('capture-preview').hidden=!value;byId('capture-preview').src=value||'';byId('capture-remove-image').hidden=!value;}
  async function readImage(file){const version=++imageVersion,finish=MemoryUI.region(byId('capture-form'));++imagePending;byId('capture-save').disabled=true;byId('capture-feedback').textContent='正在读取图片…';try{const value=await imageFile(file);if(version===imageVersion){showImage(value);byId('capture-feedback').textContent='图片已就绪，保存后在本机整理。';}}finally{if(--imagePending===0){finish();byId('capture-save').disabled=saveBusy;}}}
  function openQuick(){byId('capture-feedback').textContent='自动保存收集时间；内容仅存本机。';byId('capture-dialog').showModal();byId('capture-dialog').scrollTop=0;byId('capture-text').focus();}
  byId('quick-capture').onclick=openQuick;byId('inbox-new').onclick=openQuick;
  byId('close-capture').onclick=()=>byId('capture-dialog').close();
  byId('capture-remove-image').onclick=()=>showImage('');
  byId('capture-file').onchange=async e=>{try{if(e.target.files[0])await readImage(e.target.files[0]);}catch(err){byId('capture-feedback').textContent=err.message;}finally{e.target.value='';}};
  byId('capture-dialog').addEventListener('paste',async e=>{const file=[...e.clipboardData.items].find(x=>x.type.startsWith('image/'))?.getAsFile();if(!file)return;e.preventDefault();try{await readImage(file);}catch(err){byId('capture-feedback').textContent=err.message;}});
  async function saveCapture(duplicate='ask') {
    if(saveBusy||imagePending)return;saveBusy=true;byId('capture-save').disabled=true;
    try{
      const original=byId('capture-original').value;
      const result=await request('/api/capture',{text:byId('capture-text').value,note:byId('capture-note').value,source_url:byId('capture-url').value,original_at:original?original+':00+08:00':'',image_data:imageData,duplicate});
      if(result.duplicate&&!result.saved){byId('capture-duplicate').hidden=false;byId('capture-feedback').textContent='这条内容已收集过，可追加说明或再次保存。';return;}
      byId('capture-form').reset();showImage('');byId('capture-duplicate').hidden=true;byId('capture-dialog').close();toast('已保存到本机收集箱，正在整理。');deletedView=false;selectedCaptures.clear();inboxSignature='';await openInbox();
    }catch(err){byId('capture-feedback').textContent=err.message;}finally{saveBusy=false;byId('capture-save').disabled=false;}
  }
  byId('capture-form').onsubmit=e=>{e.preventDefault();return saveCapture();};
  byId('capture-append').onclick=()=>saveCapture('append');byId('capture-copy').onclick=()=>saveCapture('copy');
  function visibleItems(){
    const query=byId('inbox-search').value.toLowerCase(),filter=byId('inbox-filter').value;
    return items.filter(x=>(filter==='all'||x.category===filter)&&[x.title,x.text,x.note,x.ocr_text,x.topic].join(' ').toLowerCase().includes(query));
  }
  function updateSelection(){
    const visible=visibleItems(),count=visible.filter(x=>selectedCaptures.has(x.id)).length;
    const all=byId('inbox-select-all');all.checked=!!visible.length&&count===visible.length;all.indeterminate=count>0&&count<visible.length;all.disabled=inboxChanging||!visible.length;
    const action=byId('inbox-delete-selected');action.textContent=`${deletedView?'恢复':'删除'}所选（${count}）`;action.disabled=inboxChanging||!count;action.dataset.variant=deletedView?'secondary':'danger';
    byId('inbox-deleted-view').textContent=deletedView?'返回收集箱':'最近删除';byId('inbox-deleted-view').setAttribute('aria-pressed',String(deletedView));byId('inbox-deleted-view').disabled=inboxChanging;
    byId('inbox-title').textContent=deletedView?'最近删除':'收集箱';
  }
  function renderInbox(){
    const filtered=visibleItems();
    for(const id of selectedCaptures)if(!items.some(x=>x.id===id))selectedCaptures.delete(id);
    byId('inbox-items').innerHTML=filtered.map(x=>`<div class="inbox-entry"><label class="inbox-pick"><input type="checkbox" data-select-capture="${escape(x.id)}" aria-label="选择：${escape(x.title)}" ${selectedCaptures.has(x.id)?'checked':''}>选择</label><button class="inbox-card" data-capture-id="${escape(x.id)}"><span class="inbox-card-top"><span>${names[x.category]}</span><time>${escape(x.created_at.slice(0,16).replace('T',' '))}</time></span>${x.has_image?`<img alt="收集图片缩略图" src="/api/capture-image?id=${encodeURIComponent(x.id)}">`:''}<strong>${escape(x.title)}</strong><p>${escape((x.note||x.text||x.source_title||'图片记录').slice(0,160))}</p><small>${x.deleted_at?'已删除 · 可恢复':statuses[x.state]}${x.manual?' · 人工修正':x.method?' · '+escape(x.method):''}${x.memory_ids.length?' · 已关联 '+x.memory_ids.length+' 条待办':''}</small></button></div>`).join('')||`<div class="empty-state">${deletedView?'这里没有匹配的已删除内容。可返回收集箱继续查看。':'还没有匹配内容。点击“随手记”，粘贴文字或图片开始。'}</div>`;
    byId('inbox-status').textContent=`当前显示 ${filtered.length} 条（最近 300 条内）。点击卡片查看原文和修改分类。`;
    updateSelection();
  }
  async function refreshInbox(){
    clearTimeout(poll);inboxRequest?.abort();
    const controller=new AbortController(),version=++inboxVersion;inboxRequest=controller;
    const finish=MemoryUI.region(byId('inbox-items'),{skeleton:!items.length});
    try{const result=await request('/api/captures'+(deletedView?'?deleted=1':''),undefined,{signal:controller.signal});
      if(version!==inboxVersion)return;
      byId('inbox-items').querySelector('.ui-skeleton')?.remove();
      items=result.items;const signature=JSON.stringify(items);
      if(signature!==inboxSignature){renderInbox();inboxSignature=signature;
        if(typeof load==='function'&&ctx.state?.mode==='private')await load();}
    }catch(err){if(version===inboxVersion&&err.kind!=='cancelled'){byId('inbox-items').querySelector('.ui-skeleton')?.remove();byId('inbox-status').textContent=err.message;}}
    finally{if(version===inboxVersion){finish();inboxRequest=null;
      if(!deletedView&&byId('inbox-dialog').open&&items.some(x=>['saved','processing'].includes(x.state)))poll=setTimeout(refreshInbox,2000);}}
  }
  async function openInbox(){if(!byId('inbox-dialog').open){byId('inbox-dialog').showModal();byId('inbox-dialog').scrollTop=0;}await refreshInbox();}
  byId('open-inbox').onclick=openInbox;byId('inbox-refresh').onclick=refreshInbox;
  function stopInbox(){clearTimeout(poll);inboxRequest?.abort();inboxRequest=null;++inboxVersion;byId('inbox-items').removeAttribute('aria-busy');byId('inbox-items').classList.remove('ui-loading-region');}
  byId('close-inbox').onclick=()=>byId('inbox-dialog').close();byId('inbox-dialog').addEventListener('close',stopInbox);
  window.addEventListener('pagehide',stopInbox,{once:true});
  byId('inbox-search').oninput=byId('inbox-filter').onchange=()=>{selectedCaptures.clear();renderInbox();};
  byId('inbox-deleted-view').onclick=async()=>{if(inboxChanging)return;deletedView=!deletedView;selectedCaptures.clear();items=[];inboxSignature='';renderInbox();await refreshInbox();};
  byId('inbox-select-all').onchange=e=>{for(const x of visibleItems())if(e.target.checked)selectedCaptures.add(x.id);else selectedCaptures.delete(x.id);renderInbox();};
  byId('inbox-items').onchange=e=>{const id=e.target.dataset.selectCapture;if(!id)return;if(e.target.checked)selectedCaptures.add(id);else selectedCaptures.delete(id);updateSelection();};
  function confirmDelete(count){
    const dialog=byId('capture-delete-confirm');dialog.returnValue='';
    byId('capture-delete-question').textContent=`将 ${count} 条收集内容移入“最近删除”？`;
    return new Promise(resolve=>{dialog.addEventListener('close',()=>resolve(dialog.returnValue==='delete'),{once:true});dialog.showModal();});
  }
  byId('capture-delete-cancel').onclick=()=>byId('capture-delete-confirm').close('cancel');
  byId('capture-delete-accept').onclick=()=>byId('capture-delete-confirm').close('delete');
  async function changeDeleted(ids,deleted){
    if(!ids.length||inboxChanging)return;
    if(deleted&&!await confirmDelete(ids.length))return;
    inboxChanging=true;stopInbox();updateSelection();
    try{const result=await request(deleted?'/api/capture-delete':'/api/capture-restore',{ids});
      if(current&&ids.includes(current.id)){byId('capture-detail').close();current=null;}
      selectedCaptures.clear();await refreshInbox();toast(`已${deleted?'删除':'恢复'} ${result.changed} 条收集内容${deleted?'，可在“最近删除”恢复。':'。'}`,'success');
    }catch(err){if(byId('capture-detail').open)byId('capture-detail-feedback').textContent=err.message;else byId('inbox-status').textContent=err.message;}
    finally{inboxChanging=false;updateSelection();}
  }
  byId('inbox-delete-selected').onclick=()=>changeDeleted(visibleItems().filter(x=>selectedCaptures.has(x.id)).map(x=>x.id),!deletedView);
  byId('capture-delete').onclick=()=>current&&changeDeleted([current.id],!current.deleted_at);
  byId('inbox-items').onclick=e=>{const b=e.target.closest('[data-capture-id]');if(!b)return;current=items.find(x=>x.id===b.dataset.captureId);openDetail();};
  function openDetail(){
    const x=current;
    const removed=!!x.deleted_at;
    byId('capture-delete').textContent=removed?'恢复这条收集':'删除这条收集';byId('capture-delete').dataset.variant=removed?'secondary':'danger';
    byId('capture-edit-form').querySelectorAll('input,select,textarea,button[type=submit]').forEach(el=>el.disabled=removed);
    byId('capture-promote').disabled=removed;
    byId('capture-original-content').innerHTML=`<p>收集于 ${escape(x.created_at.replace('T',' '))}${x.original_at?' · 原始时间 '+escape(x.original_at):''}</p>${x.has_image?`<a href="/api/capture-image?id=${encodeURIComponent(x.id)}" target="_blank" rel="noopener"><img class="capture-full-image" src="/api/capture-image?id=${encodeURIComponent(x.id)}" alt="收集原图"></a>`:''}<details open><summary>原始内容</summary><pre>${escape(x.text||'未附文字')}</pre></details>${x.note?`<p><b>我的说明</b></p><pre>${escape(x.note)}</pre>`:''}${x.source_url?`<a href="${escape(x.source_url)}" target="_blank" rel="noopener noreferrer">${escape(x.source_title||'打开来源网页')}</a>`:''}${x.image_url?`<p><a href="${escape(x.image_url)}" target="_blank" rel="noopener noreferrer">图片来源链接</a></p>`:''}${!x.has_image?'<label>补充原图<input id="capture-attach-file" type="file" accept="image/png,image/jpeg,image/webp"></label>':''}<p>${escape(x.detail)}</p>${x.memory_ids.length?'<button type="button" id="capture-linked-tasks">在工作台查看关联待办</button>':''}`;
    byId('capture-edit-title').value=x.title;byId('capture-edit-category').value=x.category;byId('capture-edit-topic').value=x.topic;
    byId('capture-edit-due').value=x.due;byId('capture-edit-date-kind').value=x.date_kind;byId('capture-edit-ocr').value=x.ocr_text;
    byId('capture-detail-feedback').textContent=removed?'已移入最近删除，可恢复；已关联待办及原文证据保留。':x.method?x.method+' · '+statuses[x.state]:statuses[x.state];byId('capture-retry').disabled=removed||!!x.manual;
    if(removed&&byId('capture-attach-file'))byId('capture-attach-file').disabled=true;
    byId('capture-promote').textContent=x.memory_ids.length?'已关联待办（不会重复创建）':'转为待确认任务';
    if(byId('capture-attach-file'))byId('capture-attach-file').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;await request('/api/capture-attach',{id:x.id,image_data:await imageFile(f)});byId('capture-detail').close();await refreshInbox();}catch(err){byId('capture-detail-feedback').textContent=err.message;}};
    if(byId('capture-linked-tasks'))byId('capture-linked-tasks').onclick=async()=>{byId('capture-detail').close();byId('inbox-dialog').close();$('mode').value='private';ctx.view='tasks';location.hash='workspace';ctx.navigation.navigatePage();await load();ctx.topic=ctx.state.memories.find(m=>x.memory_ids.includes(m.id))?.topic||x.topic;await load();showEvidence('capture-'+x.id);};
    if(!byId('capture-detail').open){byId('capture-detail').showModal();byId('capture-detail').scrollTop=0;}
  }
  byId('close-capture-detail').onclick=()=>byId('capture-detail').close();
  function formChanges(){return {title:byId('capture-edit-title').value,category:byId('capture-edit-category').value,topic:byId('capture-edit-topic').value,due:byId('capture-edit-due').value,date_kind:byId('capture-edit-date-kind').value,ocr_text:byId('capture-edit-ocr').value};}
  byId('capture-edit-form').onsubmit=async e=>{e.preventDefault();const record=current;try{await request('/api/capture-edit',{id:record.id,changes:formChanges()});await refreshInbox();if(current?.id===record.id){current=items.find(x=>x.id===record.id)||record;byId('capture-detail-feedback').textContent='修改已保存，原文与已有待办保留。';byId('capture-retry').disabled=true;}}catch(err){if(current?.id===record.id)byId('capture-detail-feedback').textContent=err.message;}};
  byId('capture-promote').onclick=async()=>{const record=current;try{const changes=formChanges();if(Object.entries(changes).some(([k,v])=>v!==record[k]))await request('/api/capture-edit',{id:record.id,changes});await request('/api/capture-promote',{id:record.id});await refreshInbox();if(current?.id===record.id&&byId('capture-detail').open){current=items.find(x=>x.id===record.id)||record;openDetail();}toast('已进入本机空间的待确认任务');}catch(err){if(current?.id===record.id)byId('capture-detail-feedback').textContent=err.message;}};
  byId('capture-retry').onclick=async()=>{const id=current.id;try{await request('/api/capture-retry',{id});if(current?.id===id)byId('capture-detail').close();await refreshInbox();}catch(err){if(current?.id===id)byId('capture-detail-feedback').textContent=err.message;}};
  for(const [id,property,label,button] of [
    ['capture-form','onsubmit','保存中…','capture-save'],['capture-append','onclick','追加中…'],['capture-copy','onclick','保存中…'],
    ['capture-edit-form','onsubmit','保存中…'],['capture-promote','onclick','正在关联…'],['capture-retry','onclick','提交中…'],['inbox-refresh','onclick','刷新中…'],['capture-delete','onclick','处理中…'],['inbox-delete-selected','onclick','处理中…']
  ]){const target=byId(id),key=['capture-edit-form','capture-promote','capture-retry','capture-delete','inbox-delete-selected'].includes(id)?'capture-detail-mutation':id;MemoryUI.bindAction(target,property,key,button?byId(button):property==='onsubmit'?target.querySelector('button[type=submit]'):target,label,{disable:!['capture-delete','inbox-delete-selected'].includes(id)});}
  document.addEventListener('click',async e=>{const button=e.target.closest('[data-capture-open]');if(!button)return;try{current=await request('/api/capture-item?id='+encodeURIComponent(button.dataset.captureOpen));openDetail();}catch(err){toast(err.message);}});
  document.addEventListener('keydown',e=>{if(e.altKey&&e.shiftKey&&e.code==='KeyM'){e.preventDefault();if(!byId('capture-dialog').open)openQuick();}});
  if(location.hash==='#capture')openQuick();
  if(location.hash==='#inbox')openInbox();
  window.addEventListener('hashchange',()=>{if(location.hash==='#inbox')openInbox();if(location.hash==='#capture'&&!byId('capture-dialog').open)openQuick();});
}
