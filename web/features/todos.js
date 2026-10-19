export function initTodos(ctx) {
  const {$,api,toast,load,escape,waitForAnalysis,showEvidence,inlineEvidence,confirmationActions,statuses}=ctx;
  let todoFilter='active',todoWorking=false,todoCollapsed=true;
function updateTodoModel(config) {
  const local=ctx.state.engine.includes('本机模型已配置');
  $('todo-organize').textContent=ctx.state.mode==='demo'?'AI 整理待办':local?'本机 AI 整理':'AI 整理说明';
  $('todo-model-note').textContent=ctx.state.mode==='demo'?(config.has_key?`${config.model} · 仅整理合成案例`:'未配置模型 Key；可配置 AI 或先用本机规则整理。'):(local?'真实聊天由本机模型整理。':'真实聊天仅在本机处理；本机 AI 尚未配置，可先用规则整理。');
}
function renderTodos() {
  if(!ctx.state)return;
  $('todo-space').value=ctx.state.mode;
  $('todo-count').textContent=MemoryTodos.select(ctx.state.memories).length+MemoryTodos.select(ctx.state.memories,'waiting').length;
  document.querySelectorAll('[data-todo-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.todoFilter===todoFilter)));
  const items=MemoryTodos.select(ctx.state.memories,todoFilter);
  $('todo-list').innerHTML=items.map(m=>{
    const source=m.extraction_source==='remote-demo-model'?'AI 整理':m.extraction_source==='local-model'?'本机 AI':m.extraction_source==='curated'?'合成示例':'本机识别';
    const t=MemoryTodos.traits(m);
    return `<article class="todo-item" data-todo-card="${escape(m.id)}"><div class="todo-item-meta"><span>${escape(m.topic)}</span><span>${statuses[m.status]}</span></div><h3>${escape(m.title)}</h3><p class="todo-owner"><span class="role-pill ${t.role}">${t.roleLabel}</span> · ${escape(m.subject||'待确认执行人')} · ${t.certaintyLabel}</p><p class="todo-date">${escape(MemoryTodos.dueLabel(m))}</p>${m.condition?`<p class="todo-condition">条件：${escape(m.condition)}</p>`:''}${m.status==='pending'?inlineEvidence(m):''}${confirmationActions(m)}<div class="todo-item-actions"><button data-todo-source="${escape(m.id)}">查看完整原话</button><button data-edit="${escape(m.id)}">完整修改</button></div><small>${source}</small></article>`;
  }).join('') || `<div class="todo-empty"><span aria-hidden="true">✓</span><h3>${todoFilter==='completed'?'还没有完成记录':todoFilter==='pending'?'没有待确认的候选':'目前没有待处理事项'}</h3><p>${todoFilter==='completed'?'确认并完成待办后，会保留在这里。':'导入聊天后，点击整理提取属于你的待办。'}</p></div>`;
  setTodoBusy(todoWorking);
}
function setTodoBusy(busy) {
  todoWorking=busy;
  ['todo-organize','todo-local','todo-space','mode'].forEach(id=>$(id).disabled=busy);
  document.querySelectorAll('[data-todo-status]').forEach(b=>b.disabled=busy);
}
$('todo-toggle').onclick=()=>{todoCollapsed=!todoCollapsed;$('todo-body').hidden=todoCollapsed;$('todo-toggle').setAttribute('aria-expanded',String(!todoCollapsed));$('todo-chevron').textContent=todoCollapsed?'+':'−';};
$('todo-space').onchange=async()=>{if(todoWorking)return;const previous=ctx.state.mode;$('mode').value=$('todo-space').value;ctx.topic='';$('answer').hidden=true;$('evidence').innerHTML='<div class="empty-state">选择记忆查看原文。</div>';try{await load();$('todo-feedback').textContent='已切换数据空间。';}catch(e){$('mode').value=previous;$('todo-space').value=previous;toast(e.message);}};
document.querySelectorAll('[data-todo-filter]').forEach(b=>b.onclick=()=>{todoFilter=b.dataset.todoFilter;renderTodos();});
$('todo-list').onclick=async e=>{
  const b=e.target.closest('button');if(!b||!ctx.state)return;
  if(b.dataset.todoSource){const m=ctx.state.memories.find(m=>m.id===b.dataset.todoSource);if(!m)return;ctx.topic=m.topic;ctx.view=MemoryTodos.traits(m).role==='waiting'?'waiting':'timeline';$('heading').textContent=ctx.topic;$('breadcrumb').textContent='工作记忆 / '+ctx.topic;$('answer').hidden=true;location.hash='workspace';ctx.navigation.navigatePage();try{await load();showEvidence(m.message_id);}catch(error){toast(error.message);}return;}
  if(!b.dataset.todoStatus||todoWorking)return;
  setTodoBusy(true);
  try{await api('/api/review',{id:b.dataset.todoId,changes:{status:b.dataset.todoStatus},note:'主页待办：'+b.textContent});await load();$('todo-feedback').textContent='已更新，工作台同步保留修改记录。';}
  catch(e){$('todo-feedback').textContent=e.message;}finally{setTodoBusy(false);}
};
async function organizeTodos(useAI) {
  if(!ctx.state||todoWorking)return;
  setTodoBusy(true);const finish=MemoryUI.busyButton($(useAI?'todo-organize':'todo-local'),'正在整理…',{disable:false});
  try{
    let path='/api/analyze';
    if(useAI && ctx.state.mode==='demo'){
      const config=await ctx.models.loadSettings();
      if(!config.has_key){$('todo-feedback').textContent='先填写模型 API Key，然后再次点击 AI 整理待办。';await $('model-settings').onclick();return;}
      path='/api/model-analyze';
    } else if(useAI && !ctx.state.engine.includes('本机模型已配置')) {
      $('todo-feedback').textContent='当前尚未启用本机 AI，可按使用说明配置。你也可以先点击“本机整理”提取待办；真实聊天不会发给外部 API。';return;
    }
    $('todo-feedback').textContent=useAI?'AI 正在整理，候选事项仍需你确认…':'正在本机整理聊天…';
    const started=await api(path,{});const job=await waitForAnalysis(started.job_id);
    await load();
    $('todo-feedback').textContent=`已整理 ${job.result.messages} 条消息；当前 ${MemoryTodos.select(ctx.state.memories).length} 条待处理。${job.result.remaining?'还有 '+job.result.remaining+' 条消息，可继续整理。':'候选请核对原话后确认。'}`;
  }catch(e){$('todo-feedback').textContent=e.message;}finally{finish();setTodoBusy(false);}
}
$('todo-organize').onclick=()=>organizeTodos(true);
$('todo-local').onclick=()=>organizeTodos(false);


  return {render:renderTodos,updateModel:updateTodoModel,get busy(){return todoWorking;}};
}
