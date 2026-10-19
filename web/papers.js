const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function paperStatuses(m){
  const dots=[{tone:m.kind==='task'?'active':m.kind==='decision'?'decision':'source',label:{task:'承诺 / 待办',decision:'决定',fact:'事实',question:'请求 / 提议'}[m.kind]||'原话'}];
  if(m.kind==='task'&&m.task_role==='waiting')dots.push({tone:'waiting',label:'等别人'});
  if(m.status==='pending')dots.push({tone:'pending',label:m.field==='task_due_change'?'改期待确认':'待确认'});
  else if(m.status==='completed')dots.push({tone:'complete',label:'已完成'});
  else if(m.status==='dismissed')dots.push({tone:'muted',label:'已忽略'});
  else if(m.kind==='task'&&!['mine','waiting'].includes(m.task_role))dots.push({tone:'pending',label:'归属待核对'});
  return dots;
}

export function paperNote(item,{body,key,status=paperStatuses(item),record=false}){
  const summary=item.paper_summary||item.title||item.text||'暂无文字内容';
  const dots=[...new Map(status.map(dot=>[dot.tone+':'+dot.label,dot])).values()];
  const method=item.paper_summary_method==='local-ai'?'AI 摘要':'本机简述';
  return `<details class="paper-note" data-paper-key="${escape(key)}" ${record?`data-record-id="${escape(item.id)}" tabindex="-1"`:''}>
    <summary class="paper-head"><time class="paper-time">${escape(item.timestamp?.slice(11,16)||'')}</time><span class="paper-preview"><span class="paper-sentence">${escape(summary)}</span><small class="paper-method">${method}</small></span><span class="paper-states">${dots.map(dot=>`<span class="paper-state" data-tone="${escape(dot.tone)}" role="img" aria-label="${escape(dot.label)}" data-label="${escape(dot.label)}" tabindex="0"><i aria-hidden="true"></i></span>`).join('')}</span><span class="paper-chevron" aria-hidden="true">⌄</span></summary>
    <div class="paper-expansion"><div class="paper-content"><p class="paper-reading-note">${method}用于浏览，原话和确认状态以以下记录为准。</p>${body}</div></div></details>`;
}

export function initPapers(ctx){
  const {$,api,toast,load,waitForAnalysis}=ctx;
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  const dialog=document.createElement('dialog');
  dialog.className='paper-window';dialog.setAttribute('aria-label','纸条详情');
  dialog.innerHTML='<button type="button" class="paper-window-close" aria-label="收起纸条" autofocus>×</button><div class="paper-window-sheet"></div>';
  document.body.append(dialog);
  const sheet=dialog.querySelector('.paper-window-sheet'),closeButton=dialog.querySelector('button');
  let generating=false,modelLoading=false,active=null,placeholder=null,resumeKey=null,closing=false,animations=[],opening=false;
  function cancelAnimations(){animations.forEach(a=>a.cancel());animations=[];dialog.classList.remove('paper-opening');}
  function finishClose(focus=true){
    cancelAnimations();opening=false;
    const note=active;
    if(note){note.open=false;placeholder?.replaceWith(note);}
    active=null;placeholder=null;closing=false;dialog.close();document.body.classList.remove('paper-window-active');
    if(focus&&note?.isConnected)note.querySelector('.paper-head').focus({preventScroll:true});
  }
  function close(animate=true){
    if(!active||closing)return;
    closing=true;
    if(!animate||reduced.matches||opening){finishClose();return;}
    cancelAnimations();
    const from=sheet.getBoundingClientRect(),to=placeholder.getBoundingClientRect();
    const motion=sheet.animate([{transform:'none',opacity:1},{transform:`translate(${to.x-from.x}px,${to.y-from.y}px) scale(${to.width/from.width},${to.height/from.height})`,opacity:.35}],{duration:420,easing:'cubic-bezier(.4,0,.6,1)',fill:'both'});
    animations.push(motion);
    motion.finished.then(()=>finishClose()).catch(()=>{});
  }
  function open(note,desired=true,animate=true){
    if(!desired){close(animate);return;}
    if(!note?.matches('.paper-note')||note===active)return;
    if(active)finishClose(false);
    const origin=note.getBoundingClientRect();
    placeholder=document.createElement('div');placeholder.className='paper-placeholder';
    placeholder.style.height=`${origin.height}px`;note.replaceWith(placeholder);
    active=note;note.open=true;sheet.replaceChildren(note);
    document.body.classList.add('paper-window-active');dialog.showModal();
    const target=sheet.getBoundingClientRect();
    if(animate&&!reduced.matches){
      opening=true;dialog.classList.add('paper-opening');
      const scale=Math.min(origin.width/target.width,1);
      const x=origin.x-target.x,y=origin.y-target.y;
      const expandedY=Math.max(16,Math.min(origin.y,window.innerHeight-target.height*scale-16))-target.y;
      const hidden=Math.max(0,target.height-origin.height/scale);
      const expandDuration=396,approachDuration=1008;
      const motion=sheet.animate([
        {transform:`translate(${x}px,${y}px) scale(${scale})`,clipPath:`inset(0 0 ${hidden}px 0 round 5px 12px 12px 5px)`,easing:'cubic-bezier(.22,.7,.3,1)'},
        {transform:`translate(${x}px,${expandedY}px) scale(${scale})`,clipPath:'inset(0 round 5px 12px 12px 5px)',offset:expandDuration/(expandDuration+approachDuration),easing:'cubic-bezier(.16,1,.3,1)'},
        {transform:'none',clipPath:'inset(0 round 5px 12px 12px 5px)'}
      ],{duration:expandDuration+approachDuration,fill:'both'});
      const content=note.querySelector('.paper-expansion').animate([{opacity:0},{opacity:1}],{duration:260,delay:180,fill:'both'});
      animations=[motion,content];
      motion.finished.then(()=>{if(active===note&&!closing){opening=false;cancelAnimations();}}).catch(()=>{});
    }
    closeButton.focus({preventScroll:true});
  }
  reduced.addEventListener('change',()=>{if(reduced.matches&&opening){cancelAnimations();opening=false;}});
  closeButton.onclick=()=>close();
  dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
  document.addEventListener('click',event=>{
    if(active&&event.target.closest('[data-evidence],[data-edit],[data-open-source]')){finishClose(false);return;}
    const head=event.target.closest('.paper-head');if(!head)return;
    event.preventDefault();if(head.parentElement===active)close();else open(head.parentElement);
  },true);
  function remember(){resumeKey=active?.dataset.paperKey||null;if(active)finishClose(false);}
  function restore(){
    const key=resumeKey;resumeKey=null;
    const note=[...document.querySelectorAll('#memories .paper-note')].find(n=>n.dataset.paperKey===key);
    if(note)open(note,true,false);
  }
  function update(){
    const items=ctx.view==='messages'?ctx.sourceMessages():ctx.state.memories.filter(m=>!ctx.topic||m.topic===ctx.topic||m.source_topic===ctx.topic);
    const ai=items.filter(m=>m.paper_summary_method==='local-ai').length;
    if(!generating)$('paper-summary-status').textContent=ai?`${ai} 条 AI 摘要 · 点击纸条展开原话`:'一句简述，一张纸条 · 点击展开原话';
    $('paper-generate').disabled=generating||!items.length;
  }
  async function generate(){
    if(generating)return;generating=true;update();
    const scope={mode:ctx.state.mode,topic:ctx.topic,view:ctx.view};
    const sameScope=()=>scope.mode===ctx.state.mode&&scope.topic===ctx.topic&&scope.view===ctx.view;
    $('paper-summary-status').textContent='本机 AI 正在精简纸条，原话与确认状态保持不变…';
    try{
      const job=await api('/api/paper-summaries',{topic:ctx.topic,view:ctx.view});
      const result=await waitForAnalysis(job.job_id);await load();
      if(sameScope())$('paper-summary-status').textContent=`已生成 ${result.result.saved} 条 AI 摘要${result.result.remaining?'，还有 '+result.result.remaining+' 条可继续精简':'，原话保留在展开内容中'}。`;
      toast(result.result.saved?'纸条已精简，原话与操作均保留':'已有摘要已是最新版本');
    }catch(error){if(sameScope())$('paper-summary-status').textContent=error.message;toast(error.message);}
    finally{generating=false;$('paper-generate').disabled=false;if(!sameScope())update();}
  }
  async function models(){
    if(modelLoading)return;modelLoading=true;$('paper-model-refresh').disabled=true;$('paper-model-save').disabled=true;
    $('paper-model-note').textContent='正在查找本机 AI 模型…';
    try{
      const config=await api('/api/paper-models');
      $('paper-model-choice').innerHTML=config.models.map(name=>`<option value="${escape(name)}">${escape(name)}</option>`).join('');
      if(config.models.includes(config.model))$('paper-model-choice').value=config.model;
      $('paper-model-save').disabled=!config.connected||!config.models.length;
      $('paper-model-note').textContent=!config.connected?'未连接本机 AI。当前使用本机简述，纸条仍可展开、核对和操作。请先启动已安装的 Ollama 本机服务。':config.models.length?'选择已安装的本机模型，摘要只在这台电脑上生成。每次最多精简20条。':'本机服务已连接，但还没有安装模型。安装后点“重新检测”。';
    }catch(error){$('paper-model-note').textContent=error.message;}
    finally{modelLoading=false;$('paper-model-refresh').disabled=false;}
  }
  $('paper-generate').onclick=()=>{if(ctx.state.paper_ai_model)return generate();$('paper-ai-dialog').showModal();return models();};
  $('paper-ai-settings').onclick=()=>{$('paper-ai-dialog').showModal();return models();};
  $('paper-model-refresh').onclick=models;
  $('paper-model-close').onclick=()=>$('paper-ai-dialog').close();
  $('paper-model-save').onclick=async()=>{
    if(modelLoading||!$('paper-model-choice').value)return;
    try{await api('/api/paper-model',{model:$('paper-model-choice').value});await load();$('paper-ai-dialog').close();await generate();}
    catch(error){$('paper-model-note').textContent=error.message;}
  };
  ctx.bindActions([['paper-model-save','onclick','保存中…']]);
  return {open,remember,restore,update};
}
