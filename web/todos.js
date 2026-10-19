/* Shared, side-effect-free todo selection. No message data leaves the browser. */
(function(root) {
  const roleLabels={mine:'我的承诺',waiting:'等别人',proposal:'提议 / 请求',cancelled:'取消表达',unknown:'执行人待确认'};
  const certaintyLabels={explicit:'原话明确',conditional:'有前提条件',uncertain:'证据不足'};
  function traits(m) {
    const subject=m.subject||m.sender||'';
    const unknown=['','待确认执行人','待确认','你','您','大家','我们','对方'].includes(subject);
    const role=m.task_role||(m.event==='cancellation'?'cancelled':['proposal','request'].includes(m.event)?'proposal':m.kind==='task'&&!unknown?(subject==='我'?'mine':'waiting'):'unknown');
    const certainty=m.certainty||(m.condition?'conditional':['proposal','unknown'].includes(role)?'uncertain':'explicit');
    return {role,certainty,roleLabel:roleLabels[role]||roleLabels.unknown,certaintyLabel:m.reviewed&&certainty==='explicit'?'人工核对':certaintyLabels[certainty]||certaintyLabels.uncertain};
  }
  function canAdopt(m) {const t=traits(m);return m.kind==='task'&&['mine','waiting'].includes(t.role)&&t.certainty!=='uncertain'&&!['completion','cancellation'].includes(m.event);}
  function select(memories, filter='active') {
    const replaced=new Set(memories.filter(m=>['confirmed','completed'].includes(m.status)).map(m=>m.supersedes).filter(Boolean));
    return memories.filter(m=>{
      const t=traits(m),taskLike=m.kind==='task'||['request','proposal','cancellation'].includes(m.event);
      if(!taskLike||m.event==='completion'||m.status==='dismissed'||replaced.has(m.id))return false;
      if(filter==='pending')return m.status==='pending';
      if(filter==='completed')return m.kind==='task'&&m.status==='completed';
      if(!['pending','confirmed'].includes(m.status))return false;
      if(filter==='proposal')return t.role==='proposal';
      if(filter==='cancelled')return t.role==='cancelled';
      return m.kind==='task'&&t.role===(filter==='waiting'?'waiting':'mine')&&(filter==='waiting'||canAdopt(m));
    })
      .slice().sort((a,b)=>(a.due||'9999').localeCompare(b.due||'9999') || (b.timestamp||'').localeCompare(a.timestamp||'') || String(a.id).localeCompare(String(b.id)));
  }
  function today(now=new Date()) {return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);}
  function dueLabel(item,day=today()) {
    if(!item.due)return '未设日期';
    const label={deadline:'截止日期',event:'活动时间'}[item.date_kind];
    if(label)return label+' '+item.due;
    if(item.status==='completed')return '关联日期 '+item.due;
    return item.due===day?'关联今天':item.due<day?'关联日期已过 · '+item.due:'关联日期 '+item.due;
  }
  const api={select,today,dueLabel,traits,canAdopt};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  else root.MemoryTodos=api;
})(typeof window!=='undefined'?window:globalThis);
