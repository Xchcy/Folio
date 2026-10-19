export function initWechat(ctx) {
  const {$,api,toast,load,escape}=ctx;
$('import').onchange=async e=>{if(!e.target.files[0])return;const finish=MemoryUI.region(e.target.closest('label'));try{const data=JSON.parse(await e.target.files[0].text());const r=await api('/api/import',{messages:data});await load();toast(`已导入 ${r.added} 条新消息`);}catch(err){toast(err.message);}finally{finish();e.target.value='';}};
let pickedChat=null, chatOffset=0, currentPreview=null, currentMessages=[], chatQuery='', messageFilters={}, wechatBusy=false;
let currentPage=0,totalPages=0;
const messagePreviews=new Map();
const selectedMessages=new Map();
function selectionChanged() {
  $('selection-count').textContent=`已选 ${selectedMessages.size} 条（保留跨页选择）`;
  $('import-selected').disabled=wechatBusy || !selectedMessages.size;
  $('import-selected').textContent=`导入已选 ${selectedMessages.size} 条消息`;
  const checked=currentMessages.filter(m=>selectedMessages.has(m.id)).length;
  $('select-page').checked=!!currentMessages.length && checked===currentMessages.length;
  $('select-page').indeterminate=checked>0 && checked<currentMessages.length;
  document.querySelectorAll('[data-pick-message]').forEach(c=>c.checked=selectedMessages.has(c.dataset.pickMessage));
}
async function wechatAction(action) {
  if(wechatBusy)return;
  wechatBusy=true;selectionChanged();const finish=MemoryUI.region($('wechat-dialog'));const end=MemoryUI.busyButton($('import-selected'),'处理中…',{disable:false});
  $('wechat-feedback').textContent='正在读取本机微信，请稍候…';
  ['more-chats','page-first','page-prev','page-next','page-last','page-jump','jump-page','filter-messages','select-page','clear-selection','close-wechat'].forEach(id=>$(id).disabled=true);
  document.querySelectorAll('#wechat-dialog button[data-chat-ticket]').forEach(b=>b.disabled=true);
  try{await action();}catch(e){$('wechat-feedback').textContent=e.message;}
  finally{finish();end();wechatBusy=false;['more-chats','clear-selection','close-wechat'].forEach(id=>$(id).disabled=false);$('filter-messages').disabled=!pickedChat;$('select-page').disabled=!currentMessages.length;document.querySelectorAll('#wechat-dialog button[data-chat-ticket]').forEach(b=>b.disabled=false);selectionChanged();updatePager();}
}
async function searchWechat(reset=true) {
  await wechatAction(async()=>{
    if(reset){chatOffset=0;chatQuery=$('chat-search').value; $('chat-list').innerHTML='';}
    const r=await api('/api/wechat/chats',{query:chatQuery,offset:chatOffset});chatOffset=r.next_offset;
    $('chat-list').insertAdjacentHTML('beforeend',r.chats.map(c=>`<button data-chat-ticket="${escape(c.ticket)}" data-chat-name="${escape(c.name)}"><strong>${escape(c.name)}</strong><small>${c.is_group?'群聊':'个人聊天'}${c.nickname?' · 昵称 '+escape(c.nickname):''}</small>${c.wechat_name?`<small>微信备注：${escape(c.wechat_name)}</small>`:''}<small>账号尾号 ${escape(c.account_hint)}</small></button>`).join(''));
    $('more-chats').hidden=!r.has_more;
    $('wechat-feedback').textContent=r.chats.length?'请选择左侧对象。搜索和预览不会自动导入。':'未找到对象，试试其他昵称或备注。';
  });
}
function readFilters() {return {query:$('message-query').value,sender:$('message-sender').value,start:$('message-start').value,end:$('message-end').value,mine:$('message-mine').checked};}
function updatePager() {
  $('page-info').textContent=`第 ${currentPage} / ${totalPages} 页 · 每页 20 条`;
  $('page-first').disabled=wechatBusy || currentPage<=1;
  $('page-prev').disabled=wechatBusy || currentPage<=1;
  $('page-next').disabled=wechatBusy || !totalPages || currentPage>=totalPages;
  $('page-last').disabled=wechatBusy || !totalPages || currentPage>=totalPages;
  $('jump-page').max=Math.max(1,totalPages);
  $('jump-page').disabled=wechatBusy || !totalPages;
  $('page-jump').disabled=wechatBusy || !totalPages;
}
async function fetchWechatMessages(reset=true,page=1) {
  if(!pickedChat)return;
  await wechatAction(async()=>{
    if(reset){messageFilters=readFilters();currentMessages=[];currentPreview=null;messagePreviews.clear();$('wechat-messages').innerHTML='';currentPage=0;totalPages=0;updatePager();}
    const r=await api('/api/wechat/messages',{ticket:pickedChat.ticket,page,filters:messageFilters});
    currentPage=r.page;totalPages=r.total_pages;currentPreview=r.preview;currentMessages=r.messages;messagePreviews.clear();
    for(const m of r.messages){messagePreviews.set(m.id,r.preview);if(selectedMessages.has(m.id))selectedMessages.set(m.id,{preview:r.preview,id:m.id});}
    $('wechat-messages').innerHTML=r.messages.map(m=>`<label class="wechat-message"><input type="checkbox" data-pick-message="${escape(m.id)}" ${selectedMessages.has(m.id)?'checked':''}><span><span class="message-meta"><strong>${escape(m.sender)}</strong><time>${escape(m.timestamp.slice(0,19).replace('T',' '))}</time></span><span class="message-text">${escape(m.text)}</span>${m.type==='media'?'<small>媒体消息：仅现有文字说明</small>':''}</span></label>`).join('') || '<div class="empty-state">在整个会话的当前日期范围内，没有找到匹配消息。可调整筛选。</div>';
    $('wechat-messages').scrollTop=0;
    $('jump-page').value=currentPage || 1;
    $('wechat-feedback').textContent=`本机可读 ${r.total} 条，${r.date_start?.slice(0,10)||'—'} 至 ${r.date_end?.slice(0,10)||'—'}。当前筛选共 ${r.matched_total} 条，本页 ${r.messages.length} 条。按时间从新到旧排列，尾页为最早记录。`;
    selectionChanged();updatePager();
  });
}
$('wechat-import').onclick=async()=>{
  if(!ctx.state)return;
  if(ctx.state.mode!=='private'){$('mode').value='private';ctx.topic='';$('answer').hidden=true;$('evidence').innerHTML='<div class="empty-state">选择记忆查看原文。</div>';await load();}
  $('wechat-dialog').showModal();if(!$('chat-list').children.length)await searchWechat();
};
$('close-wechat').onclick=()=>$('wechat-dialog').close();
$('add-wechat').onclick=()=>$('wechat-import').click();
$('wechat-dialog').addEventListener('cancel',e=>{if(wechatBusy)e.preventDefault();});
$('chat-search-form').onsubmit=e=>{e.preventDefault();searchWechat();};
$('more-chats').onclick=()=>searchWechat(false);
$('chat-list').onclick=e=>{const b=e.target.closest('[data-chat-ticket]');if(!b||wechatBusy)return;pickedChat={ticket:b.dataset.chatTicket,name:b.dataset.chatName};$('chat-heading').textContent=pickedChat.name;document.querySelectorAll('[data-chat-ticket]').forEach(c=>c.classList.toggle('chosen',c===b));fetchWechatMessages();};
$('message-filter-form').onsubmit=e=>{e.preventDefault();fetchWechatMessages();};
$('reset-message-filters').onclick=()=>{if(wechatBusy)return;['message-query','message-sender','message-start','message-end'].forEach(id=>$(id).value='');$('message-mine').checked=false;fetchWechatMessages();};
$('page-first').onclick=()=>fetchWechatMessages(false,1);
$('page-prev').onclick=()=>fetchWechatMessages(false,currentPage-1);
$('page-next').onclick=()=>fetchWechatMessages(false,currentPage+1);
$('page-last').onclick=()=>fetchWechatMessages(false,totalPages);
$('page-jump-form').onsubmit=e=>{e.preventDefault();const page=Number($('jump-page').value);if(!Number.isInteger(page)||page<1||page>totalPages)return toast(`请输入 1 到 ${totalPages} 的页码`);fetchWechatMessages(false,page);};
function pickMessage(id,checked) {if(checked)selectedMessages.set(id,{preview:messagePreviews.get(id),id});else selectedMessages.delete(id);}
$('wechat-messages').onchange=e=>{if(e.target.dataset.pickMessage){pickMessage(e.target.dataset.pickMessage,e.target.checked);selectionChanged();}};
$('select-page').onchange=e=>{currentMessages.forEach(m=>pickMessage(m.id,e.target.checked));selectionChanged();};
$('clear-selection').onclick=()=>{selectedMessages.clear();selectionChanged();};
$('import-selected').onclick=()=>wechatAction(async()=>{
  const groups=new Map();for(const m of selectedMessages.values()){if(!groups.has(m.preview))groups.set(m.preview,[]);groups.get(m.preview).push(m.id);}
  const result=await api('/api/wechat/import',{selections:[...groups].map(([preview,ids])=>({preview,ids}))});
  selectedMessages.clear();ctx.topic=pickedChat?.name||ctx.topic;ctx.view='timeline';await load({resetScroll:true});$('wechat-feedback').textContent=`已导入 ${result.added} 条新消息，${result.duplicates} 条已存在。可关闭窗口查看和确认记忆。`;
  $('chat-refresh-status').textContent=`已手动导入 ${result.added} 条新消息，跳过 ${result.duplicates} 条重复记录。没有出现在时间线的聊天可到“来源消息”查看。`;toast(`已导入 ${result.added} 条新消息，自动跳过 ${result.duplicates} 条重复记录。`);
});

  ctx.bindActions([["wechat-import", "onclick", "加载中…"]]);
  return {};
}
