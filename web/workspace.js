import {paperNote,paperStatuses} from './papers.js';
export function createWorkspace(){
let state, topic = '', view = 'timeline', selectedId = null, editId = null;
const $ = id => document.getElementById(id);
const labels = {decision:'决定', fact:'事实', task:'承诺', question:'待确认'};
const statuses = {pending:'待确认', confirmed:'已确认', completed:'已完成', dismissed:'已忽略'};
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(text,tone) { MemoryUI.notify(text,tone); }
async function api(path, body,options={}) {
  return MemoryUI.request(path,{...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Token':state?.token||''},body:JSON.stringify({...body,mode:$('mode').value})}:{}),...options});
}
let stateLoadVersion=0,askVersion=0,askAbort,askEnd,resetScrollOnLoad=false;
const pageLifetime=new AbortController();
window.addEventListener('pagehide',()=>{pageLifetime.abort();askAbort?.abort();},{once:true});
const waitForAnalysis=id=>MemoryUI.waitForJob(id,id=>api('/api/job?id='+encodeURIComponent(id),undefined,{signal:pageLifetime.signal}),{signal:pageLifetime.signal});
async function load({resetScroll=false}={}) {
  if(resetScroll)resetScrollOnLoad=true;
  const version=++stateLoadVersion,mode=$('mode').value;
  const fresh=!state||state.mode!==mode;
  const nodes=[$('topics'),$('memories'),$('home-topics')];
  if(fresh){ctx.ruler.clear();nodes.forEach(n=>n.replaceChildren());$('home-memory-count').textContent='—';$('home-message-count').textContent='正在读取消息';$('todo-list').replaceChildren();$('workspace').inert=true;$('todo-widget').inert=true;document.querySelector('.sidebar').inert=true;}
  const finish=nodes.map(n=>MemoryUI.region(n,{skeleton:fresh}));
  try{
  const next=await api('/api/state?mode='+mode);
  if(version!==stateLoadVersion||mode!==$('mode').value)return;
  state=next;
  if (!state.topics.includes(topic)) topic = (state.mode==='demo' && state.topics.includes('社区开放日')) ? '社区开放日' : state.topics[0] || '';
  $('topics').innerHTML = state.topics.map(t => `<button class="topic ${topic===t?'chosen':''}" data-topic="${escape(t)}"><span class="topic-dot"></span>${escape(t)}<small>${state.memories.filter(m=>matchesTopic(m,t)).length}</small></button>`).join('') || '<p class="empty-nav">还没有记录<br>读取微信或导入消息开始</p>';
  $('mode-label').textContent = state.mode==='demo' ? '合成数据 · 可公开演示' : '私有记录 · 仅本机';
  $('sync').disabled = false;
  $('refresh-wechat').disabled=state.mode!=='private';
  $('model-analyze').disabled=state.mode!=='demo';
  $('heading').textContent = topic || '我的工作记忆'; $('breadcrumb').textContent = '工作记忆 / ' + (topic || '尚无事项');
  $('engine').textContent = state.engine;
  render();renderHome();
  if(resetScrollOnLoad){window.scrollTo(0,0);resetScrollOnLoad=false;}
  await ctx.models.loadSettings();
  }catch(error){
    if(version===stateLoadVersion&&fresh){
      const message='<div class="ui-error-state">工作空间暂未加载成功。请使用上方“重新连接”重试；本机记录不会因此丢失。</div>';
      $('memories').innerHTML=message;$('home-topics').innerHTML=message;$('topics').innerHTML='<p class="empty-nav">会话加载失败<br>可重新连接或切换空间。</p>';
    }
    throw error;
  }finally{
    if(version===stateLoadVersion){finish.forEach(end=>end());$('workspace').inert=!state||state.mode!==$('mode').value;$('todo-widget').inert=!state||state.mode!==$('mode').value;document.querySelector('.sidebar').inert=!state||state.mode!==$('mode').value;}
  }
}
$('feedback-retry').onclick=()=>MemoryUI.run('reconnect',$('feedback-retry'),'连接中…',async()=>{await load();$('operation-feedback').hidden=true;toast('已重新连接本机服务','success');}).catch(e=>toast(e.message,'error'));
function matchesTopic(m,name) {return !name||m.topic===name||m.source_topic===name;}
function scopeItems() {return state.memories.filter(m=>matchesTopic(m,topic));}
function sourceMessages() {
  const ids=new Set(scopeItems().flatMap(m=>m.evidence_ids?.length?m.evidence_ids:[m.message_id]));
  return state.messages.filter(m=>!topic||m.topic===topic||ids.has(m.id));
}
function inlineEvidence(m) {
  const ids=m.evidence_ids?.length?m.evidence_ids:[m.message_id];
  return `<div class="inline-evidence">${ids.slice(0,3).map(id=>{
    const s=state.messages.find(msg=>msg.id===id);if(!s)return '';
    return `<blockquote>${escape(s.text.slice(0,600))}${s.text.length>600?'…':''}</blockquote><p>${escape(s.sender)} · ${escape(s.chat)} · ${escape(s.timestamp.slice(0,19).replace('T',' '))}${s.source?.startsWith('capture:')?' · 随手记原材料':''}</p>`;
  }).join('')}</div>`;
}
function quickEditor(m) {
  const traits=MemoryTodos.traits(m),options=(values,current)=>Object.entries(values).map(([value,label])=>`<option value="${value}" ${value===current?'selected':''}>${label}</option>`).join('');
  return `<details class="quick-editor"><summary>快捷修改</summary><form data-quick-form="${escape(m.id)}"><label>内容<input name="title" value="${escape(m.title)}" required maxlength="500"></label><div class="form-row"><label>归属<select name="task_role">${options({mine:'我的承诺',waiting:'等别人',proposal:'提议 / 请求',cancelled:'取消表达',unknown:'执行人待确认'},traits.role)}</select></label><label>执行人<input name="subject" value="${escape(m.subject||'')}" placeholder="填写具体姓名或我"></label></div><label>表达确定性<select name="certainty">${options({explicit:'原话明确',conditional:'有前提条件',uncertain:'证据不足'},traits.certainty)}</select></label><div class="form-row"><label>日期<input type="date" name="due" value="${escape(m.due||'')}"></label><label>日期用途<select name="date_kind">${options({associated:'关联日期',event:'活动时间',deadline:'截止日期'},m.date_kind||'associated')}</select></label></div><button type="submit">保存快捷修改</button><small>确认状态不变；所有修改保留历史。</small></form></details>`;
}
function confirmationActions(m) {
  if(m.field==='task_due_change')return `<div class="confirmation-actions">${m.status==='pending'&&m.relation_suggestion?`<button data-apply-task-date="${escape(m.id)}">确认改期并更新原承诺</button>`:''}${m.status==='pending'?`<button data-memory-action="dismissed" data-memory-id="${escape(m.id)}">忽略改期</button>`:''}</div>`;
  const taskLike=m.kind==='task'||['request','proposal','cancellation'].includes(m.event),actionable=MemoryTodos.canAdopt(m);
  return `<div class="confirmation-actions">${m.status==='pending'&&(m.kind!=='task'||actionable)?`<button data-memory-action="confirmed" data-memory-id="${escape(m.id)}">${taskLike&&actionable?'采用任务':'采用记录'}</button>`:''}${m.status==='confirmed'&&actionable?`<button data-memory-action="completed" data-memory-id="${escape(m.id)}">标记完成</button>`:''}${m.status==='completed'&&actionable?`<button data-memory-action="confirmed" data-memory-id="${escape(m.id)}">恢复待办</button>`:''}${m.status!=='dismissed'?`<button data-memory-action="dismissed" data-memory-id="${escape(m.id)}">忽略</button>`:''}</div>${taskLike?quickEditor(m):''}`;
}
function details(m) {
  const evidence=m.evidence_ids?.length ? m.evidence_ids : [m.message_id];
  const related=state.memories.find(p=>p.id===m.relation_suggestion);
  const t=MemoryTodos.traits(m),taskLike=m.kind==='task'||['request','proposal','cancellation'].includes(m.event);
  const dateChange=m.field==='task_due_change'?`<p class="task-date-change">${m.value?'原日期 '+escape(m.value)+' → ':''}请求日期 ${escape(m.due||'待核对')} · ${m.status==='confirmed'?'已人工确认并更新原承诺':m.status==='dismissed'?'已忽略，未更新原承诺':m.relation_suggestion?'待你确认，原承诺日期尚未修改':'未能唯一关联任务，请核对原话后手动修改对应承诺'}</p>`:'';
  return `${dateChange}<div class="event-details">${m.event_label?`<span class="event-pill">${escape(m.event_label)}</span>`:''}${taskLike?`<span class="role-pill ${t.role}">${t.roleLabel}</span><span>${t.certaintyLabel}</span>`:''}${m.subject?`<span>执行人：${escape(m.subject)}</span>`:''}${m.extraction_source==='rules-model-fallback'?'<span>模型未返回合格结果，已用本地识别</span>':''}</div>${m.condition?`<p class="condition-note">需满足条件：${escape(m.condition)}</p>`:''}${m.topic_suggestion && m.topic_suggestion!==m.topic?`<div class="topic-suggestion">可能属于「${escape(m.topic_suggestion)}」<button data-adopt="${escape(m.id)}">归入此事项</button></div>`:''}${related?`<p class="relation-note">${m.event==='completion'?'可能对应此前的任务':'可能关联此前的记录'}：${escape(related.title)} <button data-evidence="${escape(related.message_id)}">查看对照</button> · ${m.field==='task_due_change'&&m.status==='confirmed'?'已确认改期':'尚未自动改变状态'}</p>`:''}${evidence.length>1?`<div class="evidence-links">共同支持这条记忆：${evidence.map((id,i)=>`<button data-evidence="${escape(id)}">原话 ${i+1}</button>`).join('')}</div>`:''}${m.status==='pending'?inlineEvidence(m)+confirmationActions(m):m.kind==='task'?confirmationActions(m):''}`;
}
function render() {
  ctx.ruler.clearWorkspace();
  ctx.papers.remember();ctx.papers.update();
  let items=scopeItems();
  $('pending-count').textContent=items.filter(m=>m.status==='pending').length;
  $('source-count').textContent=sourceMessages().length+' 条来源消息';
  const conflicts=(state.conflicts||[]).filter(c=>!topic||c.topic===topic);
  const groups={};items.filter(m=>m.status!=='dismissed' && m.topic_suggestion && m.topic_suggestion!==m.topic).forEach(m=>groups[m.topic_suggestion]=(groups[m.topic_suggestion]||0)+1);
  $('group-suggestions').hidden=!Object.keys(groups).length;
  $('group-suggestions').innerHTML=Object.entries(groups).map(([name,count])=>`<p>发现 ${count} 条可能属于「${escape(name)}」的记忆 <button data-group="${escape(name)}">核对后归入此事项</button></p>`).join('');
  $('conflicts').hidden=!conflicts.length;
  $('conflicts').innerHTML=conflicts.length?`<details><summary>${conflicts.length} 条变化需要核对</summary><div>`+conflicts.map(c=>{
    const old=state.memories.find(m=>m.id===c.before), newer=state.memories.find(m=>m.id===c.after);
    return `<h3>有变化需要核对 · ${escape(c.field)}</h3><p>已确认：${escape(old?.title)}<br>后续候选：${escape(newer?.title)}</p><p>${escape(c.note)}</p><button data-evidence="${escape(old?.message_id)}">旧记录原话</button><button data-evidence="${escape(newer?.message_id)}">新记录原话</button><button data-edit="${escape(c.after)}">核对与确认</button>`;
  }).join('')+'</div></details>':'';
  const taskView=['tasks','waiting','completed'].includes(view);
  $('task-filters').hidden=!taskView;
  $('record-view-label').textContent={timeline:'全部记录',tasks:'我的承诺',waiting:'等别人',completed:'已完成',pending:'待确认',messages:'来源消息',reviews:'修改记录'}[view]||'全部记录';
  document.querySelectorAll('[data-view]').forEach(b=>{
    const active=b.dataset.view===view||(b.closest('.tabs')&&b.dataset.view==='tasks'&&taskView);
    b.classList.toggle('active',!!active);
    if(b.closest('.tabs'))b.setAttribute('aria-selected',String(!!active));
    else b.setAttribute('aria-pressed',String(!!active));
  });
  if(view==='tasks') items=MemoryTodos.select(items,'active');
  if(view==='waiting') items=MemoryTodos.select(items,'waiting');
  if(view==='completed') items=MemoryTodos.select(items,'completed');
  if(view==='pending') items=items.filter(m=>m.status==='pending');
  if(view==='reviews') {
    const ids=new Set(items.map(m=>m.id));
    $('memories').innerHTML=state.reviews.filter(r=>ids.has(r.memory_id)).map(r=>{
      const before=JSON.parse(r.before_json), after=JSON.parse(r.after_json);
      return `<article class="review-row"><time>${escape(r.timestamp.slice(0,19).replace('T',' '))}</time><h3>${escape(after.title)}</h3><p>${escape(r.note)}</p><p class="review-change">${escape(before.title)}（${statuses[before.status]}） → ${escape(after.title)}（${statuses[after.status]}）</p><button data-evidence="${escape(before.message_id)}">查看原文</button></article>`;
    }).join('') || '<div class="empty-state">还没有人工修改。纠正记忆后，这里会保留修改前后的内容。</div>'; return;
  }
  if(view==='messages'){
    $('memories').innerHTML=[...sourceMessages()].reverse().map(msg=>{
      const linked=state.memories.filter(m=>m.message_id===msg.id||m.evidence_ids?.includes(msg.id));
      return paperNote(msg,{key:state.mode+':message:'+msg.id,status:linked.length?linked.flatMap(paperStatuses):[{tone:'source',label:'原话'}],body:`<article class="source-message-card"><div class="row-meta"><strong>${escape(msg.sender)}</strong><time>${escape(msg.timestamp.slice(0,19).replace('T',' '))}</time><span>${escape(msg.chat)}</span></div><p class="source-message-text">${escape(msg.text)}</p><p class="source-message-state">${linked.length?linked.map(m=>`${escape(labels[m.kind]||'记忆')} · ${escape(statuses[m.status])} · ${escape(m.topic)}`).join('；'):'已导入，尚未提取为独立记忆'}</p><button data-evidence="${escape(msg.id)}">查看原话与前后文</button></article>`});
    }).join('')||'<div class="empty-state">还没有导入来源消息。可点击上方“导入聊天记录”。</div>';
    ctx.ruler.renderWorkspace();ctx.papers.restore();return;
  }
  if(!items.length) { $('memories').innerHTML='<div class="empty-state">这里还没有记录。可以读取消息，或切换到合成案例演示。</div>'; return; }
  const reverse=[...items].reverse(); let lastDay='';
  $('memories').innerHTML=reverse.map(m=>{
    const day=m.timestamp.slice(0,10), group=day!==lastDay ? `<div class="day-label">${escape(day.replaceAll('-','.'))}</div>` : ''; lastDay=day;
    const previous=state.memories.find(p=>p.id===m.supersedes);
    const newer=state.memories.find(p=>p.supersedes===m.id && p.status==='confirmed');
    const assignment=topic&&m.topic!==topic?`<p class="record-assignment">保留在来源会话中 · 已归入 <button data-topic="${escape(m.topic)}">${escape(m.topic)}</button></p>`:'';
    const applied=state.memories.filter(c=>c.field==='task_due_change'&&c.relation_suggestion===m.id&&c.status==='confirmed').at(-1);
    const appliedChange=applied&&applied.due===m.due?`<p class="task-date-change">已人工确认改期：${escape(applied.value)} → ${escape(m.due)} <button data-evidence="${escape(applied.message_id)}">改期原话</button></p>`:'';
    const original=m.status==='pending'?'':`<details class="adopted-evidence"><summary>原话 · ${escape(statuses[m.status])}</summary>${inlineEvidence(m)}</details>`;
    return group+paperNote(m,{key:state.mode+':memory:'+m.id,record:true,body:`<article class="memory-row ${m.status==='dismissed'?'muted':''}"><div class="row-marker ${m.kind}"></div><div class="row-main"><div class="row-meta"><span class="kind ${m.kind}">${labels[m.kind]}</span><span>${escape(m.sender)} · ${escape(m.timestamp.slice(11,16))}</span><span class="status ${m.status}">${statuses[m.status]}</span>${newer?'<span class="old-version">历史版本</span>':''}</div><h2>${appliedChange?'原承诺：':''}${escape(m.title)}</h2>${assignment}${appliedChange}${details(m)}${original}${previous?`<div class="change"><span>原来</span><del>${escape(previous.title)}</del><span>现在</span><strong>${escape(m.title)}</strong></div>`:''}${m.reason?`<p class="reason">原因：${escape(m.reason)}</p>`:''}${m.kind==='task'?`<p class="task-note">${m.due?({deadline:'截止日期 ',event:'活动时间 '}[m.date_kind]||'关联日期 ')+escape(m.due)+' · ':''}${m.status==='completed'?'已人工标记完成':'尚无人工确认的完成状态'}</p>`:''}${m.kind==='question'&&m.status==='pending'?'<p class="task-note">这是一项待确认表达，尚未替代已确认记录。</p>':''}<div class="row-actions"><button data-evidence="${escape(m.message_id)}">查看原文 <span>↗</span></button><button data-edit="${escape(m.id)}">纠正记忆</button></div></div></article>`});
  }).join('');
  ctx.ruler.renderWorkspace();ctx.papers.restore();
}
function showEvidence(id) {
  selectedId=id; const msg=state.messages.find(m=>m.id===id); if(!msg) return;
  const chat=state.messages.filter(m=>m.chat===msg.chat), i=chat.findIndex(m=>m.id===id);
  $('evidence').innerHTML=`<div class="source-title"><h2>${escape(msg.chat)}</h2><p>${state.mode==='demo'?'合成案例，非真实联系人':'本机私有记录'}</p></div><div class="context-label">前后文</div>${chat.slice(Math.max(0,i-2),i+3).map(m=>`<article class="message ${m.id===id?'highlight':''}"><div><strong>${escape(m.sender)}</strong><time>${escape(m.timestamp.slice(0,19).replace('T',' '))}</time></div><p>${escape(m.text)}</p>${m.id===id?'<span class="evidence-tag">这条记忆的来源</span>':''}</article>`).join('')}<div class="source-foot"><b>来源定位</b><p>${escape(msg.source)}</p><p>记录编号：${escape(msg.id)}</p>${msg.source.startsWith('capture:')?`<button data-capture-open="${escape(msg.source.slice(8))}">查看收集原文 / 原图</button><p>收集时间、原图和补充说明保留在本机收集箱。</p>`:state.mode==='private'?'<p>编号关联本机数据库中的消息；原始读取批次保留消息类型和引用信息。</p>':''}</div>`;
  document.body.classList.add('evidence-open');
  $('close-evidence').focus({preventScroll:true});
}
function edit(id) {
  const m=state.memories.find(m=>m.id===id); if(!m)return;
  editId=id; $('edit-title').value=m.title; $('edit-topic').value=m.topic; $('edit-status').value=m.status; $('edit-due').value=m.due||''; $('edit-note').value=''; $('edit-kind').value=m.kind; $('edit-field').value=m.field; $('edit-reason').value=m.reason;
  const t=MemoryTodos.traits(m);$('edit-subject').value=m.subject||'';$('edit-role').value=t.role;$('edit-certainty').value=t.certainty;$('edit-date-kind').value=m.date_kind||'associated';
  $('edit-previous').innerHTML='<option value="">不替代</option>'+state.memories.filter(p=>p.id!==m.id && p.timestamp<m.timestamp).map(p=>`<option value="${escape(p.id)}">${escape(p.title)}</option>`).join(''); $('edit-previous').value=m.supersedes||'';
  $('edit-dialog').showModal();
}
async function ask(question) {
  if(!question.trim()) return toast('先输入一个问题');
  askAbort?.abort();askEnd?.();
  const version=++askVersion,scope={mode:$('mode').value,topic,date:$('asof').value};
  const controller=new AbortController();askAbort=controller;
  $('question').value=question;const button=$('ask-form').querySelector('button');const end=MemoryUI.busyButton(button,'查找中…');askEnd=end;
  try {
    const answer=await api('/api/ask',{question,topic:scope.topic||null,as_of:scope.date||null},{signal:controller.signal});
    if(version!==askVersion||scope.mode!==$('mode').value||scope.topic!==topic||scope.date!==$('asof').value||question!==$('question').value)return;
    $('answer').hidden=false;
    $('answer').innerHTML=`<div class="answer-label">${answer.uncertain?'有待确认的内容':'依据已有记录'}${answer.as_of?' · 截至 '+escape(answer.as_of):''}</div><h2>${escape(answer.text)}</h2>${answer.items.map(m=>`<div class="answer-item"><span>${escape(m.title)}${m.condition?' · 条件：'+escape(m.condition):''}</span><button data-evidence="${escape(m.message_id)}">证据：${escape(m.timestamp.slice(5,10))}</button></div>`).join('')}<div class="evidence-links">${answer.evidence_ids.map((id,i)=>`<button data-evidence="${escape(id)}">原话 ${i+1}</button>`).join('')}</div><p>范围：${escape(answer.scope)}。${escape(answer.method)}。</p>`;
    if(answer.evidence_ids.length)showEvidence(answer.evidence_ids[0]);
  }catch(e){if(e.kind!=='cancelled'&&version===askVersion)toast(e.message,'error');}finally{if(version===askVersion)end();}
}
document.addEventListener('click', e=>{
  const b=e.target.closest('button'); if(!b)return;
  if(b.dataset.topic!==undefined){topic=b.dataset.topic; $('answer').hidden=true; load({resetScroll:true}).catch(e=>toast(e.message));}
  if(b.dataset.openSource!==undefined){topic=b.dataset.openSource;view='messages';$('answer').hidden=true;load({resetScroll:true}).catch(e=>toast(e.message));}
  if(b.dataset.view){view=b.dataset.view;b.closest('details.record-options')?.removeAttribute('open');render();}
  if(b.dataset.q)ask(b.dataset.q);
  if(b.dataset.evidence)showEvidence(b.dataset.evidence);
  if(b.dataset.edit)edit(b.dataset.edit);
  if(b.dataset.group)MemoryUI.run('group:'+topic,b,'归并中…',async()=>{const r=await api('/api/group',{source_topic:topic,target_topic:b.dataset.group});topic=r.topic;await load();toast(`已归并 ${r.moved} 条记忆，原文和状态均保留。`);}).catch(e=>toast(e.message));
  if(b.dataset.adopt){const m=state.memories.find(m=>m.id===b.dataset.adopt);if(m)MemoryUI.run('adopt:'+m.id,b,'归并中…',async()=>{await api('/api/review',{id:m.id,changes:{topic:m.topic_suggestion},note:'人工采用事项归并建议，事实状态未改变'});topic=m.topic_suggestion;await load();toast('事项已归并，状态仍需核对');}).catch(e=>toast(e.message));}
});
$('asof').addEventListener('change',()=>document.querySelector('.ask-box').classList.toggle('has-history',!!$('asof').value));
$('ask-form').onsubmit=e=>{e.preventDefault();ask($('question').value);};
$('mode').onchange=()=>{topic='';$('answer').hidden=true;$('evidence').innerHTML='<div class="empty-state">选择记忆查看原文。</div>';load().catch(e=>toast(e.message));};
let evidenceReturnFocus;
 document.addEventListener('click',e=>{if(e.target.closest('[data-evidence],[data-todo-source]'))evidenceReturnFocus=e.target.closest('.paper-note')?.querySelector('.paper-head')||e.target.closest('button');},true);
 function closeEvidence(){document.body.classList.remove('evidence-open');if(evidenceReturnFocus?.isConnected)evidenceReturnFocus.focus({preventScroll:true});}
 $('close-evidence').onclick=closeEvidence;
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('evidence-open')&&!document.querySelector('dialog[open]'))closeEvidence();});
$('cancel-edit').onclick=()=>$('edit-dialog').close();
$('edit-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/review',{id:editId,changes:{title:$('edit-title').value,status:$('edit-status').value,topic:$('edit-topic').value,due:$('edit-due').value||null,kind:$('edit-kind').value,field:$('edit-field').value,reason:$('edit-reason').value,supersedes:$('edit-previous').value,subject:$('edit-subject').value,task_role:$('edit-role').value,certainty:$('edit-certainty').value,date_kind:$('edit-date-kind').value},note:$('edit-note').value});$('edit-dialog').close();$('answer').hidden=true;await load();toast('修改已保存，原文和修改历史已保留');}catch(e){toast(e.message);}};

const reviewing=new Set();
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-apply-task-date]');if(!b)return;
  MemoryUI.run('task-date:'+b.dataset.applyTaskDate,b,'正在更新…',async()=>{
    const result=await api('/api/task-date-change',{id:b.dataset.applyTaskDate});
    if(view==='pending')view='timeline';$('answer').hidden=true;await load();
    const card=[...$('memories').querySelectorAll('[data-record-id]')].find(n=>n.dataset.recordId===result.task_id);
    if(card){ctx.papers.open(card,true,false);card.focus({preventScroll:true});card.scrollIntoView({block:'center',behavior:'instant'});}
    toast('已确认改期，原承诺日期已更新；原话与修改历史保留');
  }).catch(error=>toast(error.message));
});
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-memory-action]');if(!b||reviewing.has(b.dataset.memoryId))return;
  const id=b.dataset.memoryId,status=b.dataset.memoryAction,label=b.textContent;reviewing.add(id);const finish=MemoryUI.busyButton(b,'更新中…');
  try{
    await api('/api/review',{id,changes:{status},note:'核对卡：'+label});$('answer').hidden=true;
    if(status==='confirmed'&&view==='pending')view='timeline';
    await load();
    const card=[...$('memories').querySelectorAll('[data-record-id]')].find(node=>node.dataset.recordId===id);
    if(card){ctx.papers.open(card,true,false);card.focus({preventScroll:true});card.scrollIntoView({block:'center',behavior:'instant'});}
    toast(status==='confirmed'?'已采用，记录与原话仍保留在时间线中':'已更新，修改已留痕');
  }catch(error){toast(error.message);}finally{reviewing.delete(id);finish();}
});
document.addEventListener('change',e=>{
  if(e.target.name!=='task_role')return;const form=e.target.closest('[data-quick-form]');if(!form)return;
  if(e.target.value==='mine')form.elements.subject.value='我';
  else if(e.target.value==='waiting'&&form.elements.subject.value==='我')form.elements.subject.value='';
});
document.addEventListener('submit',async e=>{
  const form=e.target.closest('[data-quick-form]');if(!form)return;e.preventDefault();
  const data=Object.fromEntries(new FormData(form)),role=data.task_role;
  const changes={...data,due:data.due||null,kind:['mine','waiting','unknown'].includes(role)?'task':'question'};
  if(role==='mine')changes.subject='我';
  const button=form.querySelector('button');if(button.disabled)return;const finish=MemoryUI.busyButton(button,'保存中…');
  try{await api('/api/review',{id:form.dataset.quickForm,changes,note:'核对卡快捷修改归属、原话解释或日期；确认状态不变'});$('answer').hidden=true;await load();toast('修改已保存；核对无误后可直接采用');}catch(error){toast(error.message);}finally{finish();}
});
async function runAnalysis(path,b) {
  if(b.disabled)return;const finish=MemoryUI.busyButton(b,'正在整理…');
  try {
    const started=await api(path,{});const job=await waitForAnalysis(started.job_id);
    await load();toast(`已整理 ${job.result.messages} 条消息，${job.result.candidates} 个候选。${job.result.saved!==undefined?'更新 '+job.result.saved+' 条未人工修改的记忆。':''}${job.result.recovered_date_changes?'补回 '+job.result.recovered_date_changes+' 条此前漏识别的改期请求。':''}${job.result.remaining?'还剩 '+job.result.remaining+' 条，可继续整理。':''}人工修改已保留。`);
  }catch(e){toast(e.message);}finally{finish();b.disabled=b.id==='model-analyze' && state.mode!=='demo';}
}
$('analyze').onclick=()=>runAnalysis('/api/analyze',$('analyze'));
$('model-analyze').onclick=()=>runAnalysis('/api/model-analyze',$('model-analyze'));
function renderHome() {
  ctx.ruler.renderHome();
  ctx.todos.render();
  $('home-space').textContent=state.mode==='demo'?'合成案例演示':'我的本机记录';
  $('home-memory-count').textContent=state.memories.length;
  $('home-message-count').textContent=`来自 ${state.messages.length} 条消息`;
  $('home-topics').innerHTML=[...state.topics].sort((a,b)=>{
    const latest=name=>state.memories.filter(m=>m.topic===name).reduce((date,m)=>m.timestamp>date?m.timestamp:date,'');
    return latest(b).localeCompare(latest(a));
  }).slice(0,3).map((name,index)=>{
    const items=state.memories.filter(m=>m.topic===name), pending=items.filter(m=>m.status==='pending').length;
    return `<button class="home-topic" data-pointer-tilt data-tilt-max="3" data-open-topic="${escape(name)}"><span class="topic-card-top"><span class="topic-card-symbol" aria-hidden="true">${['◷','◇','⌁'][index]}</span><span>${pending?pending+' 条待确认':'随时可回看'}</span></span><strong>${escape(name)}</strong><span class="topic-card-bottom">${items.length} 条记忆<span aria-hidden="true">↗</span></span></button>`;
  }).join('') || '<div class="home-empty"><h3>还没有工作记忆</h3><p>从微信选几条消息，开始整理你的第一个事项。</p><button class="secondary-action" id="empty-import">从微信导入</button></div>';
  if($('empty-import'))$('empty-import').onclick=()=>$('home-import').click();
}

function bindActions(actions){
  for(const [id,property,label] of actions){
    const target=$(id),button=property==='onsubmit'?target.querySelector('button[type=submit],button:not([type])'):target;
    MemoryUI.bindAction(target,property,id,button,label,{disable:false});
  }
}

const ctx={ bindActions,$,api,toast,load,escape,waitForAnalysis,showEvidence,inlineEvidence,confirmationActions,statuses,sourceMessages,
  get state(){return state;},get topic(){return topic;},set topic(value){topic=value;},
  get view(){return view;},set view(value){view=value;},
  start(){
    bindActions([['edit-form','onsubmit','保存中…']]);
    load().catch(e=>toast(e.message));
  }
};
return ctx;
}
