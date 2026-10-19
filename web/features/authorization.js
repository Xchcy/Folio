export function initAuthorization(ctx) {
  const {$,api,toast,load,escape}=ctx;
let authorizedBusy=false,refreshing=false;
const authorizationPicks=new Set();
let authorizationQuery='',authorizationOffset=0;
function authorizationView(existing){
  $('authorized-view-wechat').setAttribute('aria-pressed',String(!existing));
  $('authorized-view-existing').setAttribute('aria-pressed',String(existing));
}
function updateGrantSelection() {
  $('authorize-save').disabled=authorizedBusy||!authorizationPicks.size;
  $('authorize-save').textContent=`确认授权（${authorizationPicks.size}）`;
}
async function searchAuthorizableChats(reset=true) {
  if(authorizedBusy)return;
  authorizationView(false);
  authorizedBusy=true;$('authorize-save').disabled=true;$('authorize-more').disabled=true;
  if(reset){authorizationQuery=$('authorize-query').value;authorizationOffset=0;$('authorize-choices').innerHTML='';}
  const finish=MemoryUI.region($('authorize-choices'),{skeleton:reset});
  $('authorize-feedback').textContent='正在加载微信联系人和群聊，仅查看名单…';
  try{const r=await api('/api/wechat/chats',{query:authorizationQuery,offset:authorizationOffset});authorizationOffset=r.next_offset;$('authorize-choices').querySelector('.ui-skeleton')?.remove();
    $('authorize-choices').insertAdjacentHTML('beforeend',r.chats.map(c=>`<label class="authorized-chat"><input type="checkbox" value="${escape(c.ticket)}" ${authorizationPicks.has(c.ticket)?'checked':''}><span><strong>${escape(c.name)}</strong><small>${c.is_group?'群聊':'个人聊天'}${c.nickname?' · 昵称 '+escape(c.nickname):''} · 账号尾号 ${escape(c.account_hint)}</small></span></label>`).join(''));
    $('authorize-more').hidden=!r.has_more;$('authorize-feedback').textContent=r.chats.length?'勾选需要授权的微信会话，再点击确认授权。不会自动读取消息。':'没有匹配对象，请换昵称、备注、微信 ID 或群名搜索。';
  }catch(e){$('authorize-choices').querySelector('.ui-skeleton')?.remove();$('authorize-feedback').textContent=e.message;}finally{finish();authorizedBusy=false;$('authorize-more').disabled=false;updateGrantSelection();}
}
async function showExistingAuthorized(selected=[]) {
  authorizationView(true);
  const wasBusy=authorizedBusy;authorizedBusy=true;
  $('authorize-picker').hidden=true;$('authorized-existing').hidden=false;$('authorized-title').textContent='已授权会话';
  $('authorized-list').innerHTML='';authorizedSelection();
  const finish=MemoryUI.region($('authorized-list'),{skeleton:true});
  $('authorized-feedback').textContent='正在加载授权名单，尚未读取聊天消息…';
  try{const r=await api('/api/wechat/authorized',{});
    $('authorized-list').innerHTML=r.chats.map(c=>`<div class="authorized-entry"><label class="authorized-chat"><input type="checkbox" value="${escape(c.name)}" ${selected.includes(c.name)?'checked':''}><span><strong>${escape(c.name)}</strong><small>${c.resolved?'账号尾号 '+escape(c.account_hint):'读取前核对唯一身份'}</small></span></label><button type="button" data-revoke-chat="${escape(c.name)}">取消授权</button></div>`).join('')||'<p class="empty-state">还没有授权会话，点击“从微信选择”添加。</p>';
    $('authorized-feedback').textContent=r.note;authorizedSelection();return true;
  }catch(e){$('authorized-list').querySelector('.ui-skeleton')?.remove();$('authorized-feedback').textContent=e.message;return false;}
  finally{finish();authorizedBusy=wasBusy;authorizedSelection();}
}
function authorizedSelection() {
  const names=[...document.querySelectorAll('#authorized-list input:checked')].map(c=>c.value);
  $('authorized-read').disabled=authorizedBusy||!names.length;
  $('authorized-read').textContent=`${refreshing?'刷新导入':'读取'}勾选会话（${names.length}）`;
  $('authorized-revoke').disabled=authorizedBusy||!names.length;
  $('authorized-revoke').textContent=`取消勾选授权（${names.length}）`;
  return names;
}
async function openAuthorizedChats() {
  if(authorizedBusy||!ctx.state)return;
  refreshing=false;
  if(ctx.state.mode!=='private'){$('mode').value='private';ctx.topic='';$('answer').hidden=true;$('evidence').innerHTML='';await load();}
  $('authorized-dialog').showModal();$('authorize-picker').hidden=false;$('authorized-existing').hidden=true;$('authorized-title').textContent='从微信选择授权会话';
  authorizationPicks.clear();$('authorize-query').value='';updateGrantSelection();await searchAuthorizableChats();
}
$('authorized-view-wechat').onclick=async()=>{if(authorizedBusy)return;$('authorize-picker').hidden=false;$('authorized-existing').hidden=true;$('authorized-title').textContent='从微信选择授权会话';await searchAuthorizableChats();};
$('authorized-view-existing').onclick=()=>{if(!authorizedBusy)return showExistingAuthorized();};
$('authorize-search-form').onsubmit=e=>{e.preventDefault();return searchAuthorizableChats();};
$('authorize-more').onclick=()=>searchAuthorizableChats(false);
$('authorize-choices').onchange=e=>{if(e.target.type!=='checkbox')return;if(e.target.checked)authorizationPicks.add(e.target.value);else authorizationPicks.delete(e.target.value);updateGrantSelection();};
$('authorize-clear').onclick=()=>{authorizationPicks.clear();document.querySelectorAll('#authorize-choices input').forEach(c=>c.checked=false);updateGrantSelection();};
$('authorize-save').onclick=async()=>{
  if(authorizedBusy||!authorizationPicks.size)return;
  authorizedBusy=true;updateGrantSelection();$('authorize-feedback').textContent='正在保存勾选会话的授权…';
  try{const r=await api('/api/wechat/authorize',{tickets:[...authorizationPicks]});authorizationPicks.clear();await showExistingAuthorized(r.selected);$('authorized-feedback').textContent=r.note+' 如需导入，请点击“读取勾选会话”。';}
  catch(e){$('authorize-feedback').textContent=e.message;}finally{authorizedBusy=false;updateGrantSelection();authorizedSelection();}
};
$('sync').onclick=()=>openAuthorizedChats().catch(e=>toast(e.message));
$('wechat-authorized').onclick=$('sync').onclick;
$('refresh-wechat').onclick=async()=>{
  if(authorizedBusy||ctx.state?.mode!=='private')return;
  refreshing=true;
  const sources=[...new Set(ctx.sourceMessages().filter(m=>!m.source?.startsWith('capture:')).map(m=>m.chat))];
  $('authorized-dialog').showModal();
  const loaded=await showExistingAuthorized(sources);
  $('authorized-title').textContent='刷新导入聊天记录';
  if(!loaded)return;
  $('authorized-feedback').textContent='已优先勾选当前事项的已授权来源。请核对后刷新；不会读取未勾选会话。每个会话最多读取最近 400 条，自动跳过重复消息。';
};
$('authorized-close').onclick=()=>$('authorized-dialog').close();
$('authorized-list').onchange=authorizedSelection;
$('authorized-all').onclick=()=>{document.querySelectorAll('#authorized-list input').forEach(c=>c.checked=true);authorizedSelection();};
$('authorized-clear').onclick=()=>{document.querySelectorAll('#authorized-list input').forEach(c=>c.checked=false);authorizedSelection();};
async function revokeAuthorizedChats(chats) {
  if(authorizedBusy||!chats.length)return;
  const remaining=authorizedSelection().filter(n=>!chats.includes(n));
  authorizedBusy=true;document.querySelectorAll('#authorized-dialog button,#authorized-list input').forEach(c=>c.disabled=true);
  $('authorized-feedback').textContent='正在取消授权，已导入记录会保留…';
  try{const r=await api('/api/wechat/revoke',{chats});authorizationPicks.clear();await showExistingAuthorized(remaining);$('authorized-feedback').textContent=r.note;}
  catch(e){$('authorized-feedback').textContent=e.message;}
  finally{authorizedBusy=false;document.querySelectorAll('#authorized-dialog button,#authorized-list input').forEach(c=>c.disabled=false);authorizedSelection();}
}
$('authorized-list').onclick=e=>{const button=e.target.closest('[data-revoke-chat]');if(button)return MemoryUI.run('revoke-chat',button,'取消中…',()=>revokeAuthorizedChats([button.dataset.revokeChat]),{disable:false});};
$('authorized-revoke').onclick=()=>revokeAuthorizedChats(authorizedSelection());
$('authorized-dialog').addEventListener('cancel',e=>{if(authorizedBusy)e.preventDefault();});
$('authorized-read').onclick=async()=>{
  const chats=authorizedSelection();if(authorizedBusy||!chats.length)return;
  authorizedBusy=true;document.querySelectorAll('#authorized-dialog button,#authorized-list input').forEach(c=>c.disabled=true);$('mode').disabled=true;$('todo-space').disabled=true;
  $('authorized-feedback').textContent=`正在读取勾选的 ${chats.length} 个会话…`;
  try{
    const r=await api('/api/sync',{chats});ctx.view='timeline';await load();
    const summary=r.chats.map(c=>`${c.name}：读取 ${c.fetched||0} 条，新增 ${c.added} 条，重复 ${c.duplicates||0} 条，新增候选记忆 ${c.candidates||0} 条${c.latest?'；最新消息 '+c.latest.slice(0,19).replace('T',' '):''}；${c.status}${c.window_limited?'；已达到最近 400 条窗口，更早消息请从微信选择导入':''}`).join('。');
    $('authorized-feedback').textContent=summary;
    $('chat-refresh-status').textContent=`刷新时间 ${r.refreshed_at.slice(0,19).replace('T',' ')}。${summary}。可在“来源消息”查看已导入但未提取成记忆的聊天。`;
    $('chat-refresh-links').innerHTML=r.chats.map(c=>`<button type="button" data-open-source="${escape(c.name)}">查看 ${escape(c.name)} 的来源消息</button>`).join('');
    toast(r.chats.some(c=>c.complete===false)?'部分会话未完整刷新，请查看读取结果':'已刷新导入，新增记忆仍需确认');
  }
  catch(e){$('authorized-feedback').textContent=e.message;}
  finally{authorizedBusy=false;document.querySelectorAll('#authorized-dialog button,#authorized-list input').forEach(c=>c.disabled=false);$('mode').disabled=ctx.todos.busy;$('todo-space').disabled=ctx.todos.busy;authorizedSelection();}
};

  ctx.bindActions([["sync", "onclick", "加载中…"], ["refresh-wechat", "onclick", "加载中…"], ["wechat-authorized", "onclick", "加载中…"], ["authorize-search-form", "onsubmit", "搜索中…"], ["authorize-more", "onclick", "加载中…"], ["authorized-view-wechat", "onclick", "加载中…"], ["authorized-view-existing", "onclick", "加载中…"], ["authorize-save", "onclick", "保存授权…"], ["authorized-revoke", "onclick", "取消中…"], ["authorized-read", "onclick", "读取中…"]]);
  return {};
}
