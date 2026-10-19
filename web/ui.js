/* Shared presentation and request lifecycle. No business or permission rules. */
(function(root) {
  const pending=new Map();
  const doc=root.document;
  class RequestError extends Error {
    constructor(message,kind='request',status=0){super(message);this.kind=kind;this.status=status;}
  }
  function requestTimeout(path){
    if(path.startsWith('/api/sync'))return 600000;
    if(path.startsWith('/api/wechat/messages'))return 150000;
    if(path.startsWith('/api/wechat/chats'))return 45000;
    if(path.startsWith('/api/model-test'))return 100000;
    return 25000;
  }
  function connection(state){
    const node=doc?.getElementById('connection-status');if(!node)return;
    node.dataset.state=state;
    node.textContent=state==='offline'?'本机服务未连接':state==='online'?'本机服务已连接':'正在连接本机服务';
  }
  function feedback(message){
    const node=doc?.getElementById('operation-feedback');if(!node)return;
    node.hidden=false;node.querySelector('[data-feedback-message]').textContent=message;
  }
  async function request(path,options={}){
    const {timeoutMs=requestTimeout(path),signal,...init}=options;
    const controller=new AbortController();
    let timedOut=false;
    const cancel=()=>controller.abort();
    if(signal?.aborted)controller.abort();else signal?.addEventListener('abort',cancel,{once:true});
    const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeoutMs);
    try{
      const response=await root.fetch(path,{...init,signal:controller.signal});
      connection('online');
      let data;
      try{data=await response.json();}catch(error){
        if(controller.signal.aborted)throw error;
        throw new RequestError('本机服务返回了无法读取的结果，请刷新后重试。','format',response.status);
      }
      if(!response.ok)throw new RequestError(data.error||'操作未完成，请核对输入后重试。','request',response.status);
      return data;
    }catch(error){
      if(error instanceof RequestError){feedback(error.message);throw error;}
      if(controller.signal.aborted){
        if(!timedOut)throw new RequestError('已停止等待此请求。','cancelled');
        const message='本次等待已超时。后台操作可能仍在进行，请先核对结果，再重试。';
        feedback(message);throw new RequestError(message,'timeout');
      }
      connection('offline');
      const message='无法连接本机服务。请确认服务正在运行，然后点击“重新连接”。';
      feedback(message);throw new RequestError(message,'network');
    }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
  }
  function busyButton(button,label='处理中…',{disable=true}={}){
    if(!button)return ()=>{};
    const original={text:button.textContent,disabled:button.disabled,minWidth:button.style.minWidth};
    const width=button.getBoundingClientRect?.().width||0;
    button.style.minWidth=width?`${Math.ceil(width)}px`:original.minWidth;
    button.dataset.idleLabel=original.text;
    button.classList.add('is-loading');button.setAttribute('aria-busy','true');
    if(label)button.textContent=label;
    if(disable)button.disabled=true;
    let finished=false;
    return ()=>{
      if(finished)return;finished=true;
      button.classList.remove('is-loading');button.removeAttribute('aria-busy');
      button.style.minWidth=original.minWidth;
      if(button.textContent===label)button.textContent=original.text;
      if(disable)button.disabled=original.disabled;
      delete button.dataset.idleLabel;
    };
  }
  function run(key,button,label,action,options={}){
    if(pending.has(key))return pending.get(key);
    const end=busyButton(button,label,options);
    const promise=Promise.resolve().then(action).finally(()=>{end();pending.delete(key);});
    pending.set(key,promise);return promise;
  }
  function bindAction(target,property,key,button,label,options={}){
    if(!target||typeof target[property]!=='function')return;
    const handler=target[property];
    target[property]=function(event){
      if(property==='onsubmit')event.preventDefault();
      return run(key,typeof button==='function'?button():button,label,()=>handler.call(this,event),options).catch(error=>{
        if(error.kind!=='cancelled'){feedback(error.message);notify(error.message,'error');}
      });
    };
  }
  function sleep(ms,signal){return new Promise((resolve,reject)=>{
    if(signal?.aborted)return reject(new RequestError('已停止等待后台任务，任务可能仍在执行。','cancelled'));
    const onAbort=()=>{clearTimeout(timer);reject(new RequestError('已停止等待后台任务，任务可能仍在执行。','cancelled'));};
    const timer=setTimeout(()=>{signal?.removeEventListener('abort',onAbort);resolve();},ms);
    signal?.addEventListener('abort',onAbort,{once:true});
  });}
  async function waitForJob(id,read,{signal,timeoutMs=600000,interval=700,onState=()=>{}}={}){
    const started=Date.now();
    for(;;){
      if(signal?.aborted)throw new RequestError('已停止等待后台任务，任务可能仍在执行。','cancelled');
      const job=await read(id);onState(job.status);
      if(job.status==='completed')return job;
      if(job.status!=='running')throw new RequestError(job.error||'后台任务未完成，请检查后重试。');
      if(Date.now()-started>=timeoutMs)throw new RequestError('后台任务仍在运行，本次停止自动查询。请稍后刷新核对结果。','timeout');
      await sleep(interval,signal);
    }
  }
  function region(node,{skeleton=false,count=3}={}){
    if(!node)return ()=>{};
    node.setAttribute('aria-busy','true');node.classList.add('ui-loading-region');
    if(skeleton&&!node.children.length){
      node.innerHTML=`<div class="ui-skeleton" aria-hidden="true">${Array.from({length:count},()=>'<span></span>').join('')}</div>`;
    }
    return ()=>{node.removeAttribute('aria-busy');node.classList.remove('ui-loading-region');};
  }
  let notificationTimer;
  function notify(message,tone){
    const node=doc?.getElementById('toast');if(!node)return;
    tone=tone||(/失败|无法|超时|错误|不可用|未连接/.test(message)?'error':/已保存|已更新|已导入|已取消|成功/.test(message)?'success':'info');
    node.dataset.tone=tone;node.hidden=false;node.replaceChildren();
    const icon=doc.createElement('span');icon.className='toast-icon';icon.textContent={error:'!',success:'✓',info:'i'}[tone]||'i';icon.setAttribute('aria-hidden','true');
    const text=doc.createElement('span');text.textContent=message;
    const close=doc.createElement('button');close.textContent='×';close.setAttribute('aria-label','关闭提示');close.onclick=()=>{node.hidden=true;clearTimeout(notificationTimer);};
    node.append(icon,text,close);clearTimeout(notificationTimer);notificationTimer=setTimeout(()=>node.hidden=true,tone==='error'?10000:5000);
  }
  const primaryIds=new Set(['capture-save','authorize-save','authorized-read','import-selected','todo-organize','open-memory']);
  const dangerIds=new Set(['clear-model','authorized-revoke','capture-delete','inbox-delete-selected','capture-delete-accept']);
  const ghostIds=new Set(['cancel-edit','close-model','authorize-clear','authorized-clear']);
  const iconIds=new Set(['close-evidence','close-wechat','authorized-close','close-capture','close-inbox','close-capture-detail','close-library']);
  const preserveSelector='.home-topic,.inbox-card,.topic,[data-chat-ticket],.todo-toggle';
  function enhance(scope=doc){
    if(!scope)return;
    const controls=[...(scope.matches?.('button')?[scope]:[]),...(scope.querySelectorAll?.('button')||[])];
    for(const button of controls){
      if(button.dataset.uiReady)continue;button.dataset.uiReady='true';
      if(button.matches(preserveSelector)){button.classList.add('ui-interactive');continue;}
      if(button.closest('.tabs,.todo-filters')||['authorized-view-wechat','authorized-view-existing'].includes(button.id)){
        button.classList.add('ui-tab');
        if(button.closest('.tabs')){button.setAttribute('role','tab');button.setAttribute('aria-selected',String(button.classList.contains('active')));}
        continue;
      }
      button.classList.add('ui-button');
      const danger=dangerIds.has(button.id)||button.hasAttribute('data-revoke-chat')||button.dataset.memoryAction==='dismissed'||button.dataset.todoStatus==='dismissed';
      const primary=primaryIds.has(button.id)||(button.type==='submit'&&!!button.form)||button.closest('#ask-form');
      button.dataset.variant=danger?'danger':iconIds.has(button.id)?'icon':primary?'primary':ghostIds.has(button.id)?'ghost':'secondary';
      if(iconIds.has(button.id)){
        const label=button.getAttribute('aria-label')||button.title||'关闭';
        button.setAttribute('aria-label',label);button.dataset.tooltip=label;
      }
    }
  }
  function boot(){
    enhance();
    const observer=new MutationObserver(records=>{
      for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)enhance(node);
    });
    observer.observe(doc.body,{childList:true,subtree:true});
    doc.getElementById('feedback-dismiss')?.addEventListener('click',()=>doc.getElementById('operation-feedback').hidden=true);
    doc.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)||!event.target.matches('.tabs [role=tab]'))return;
      const tabs=[...event.target.closest('.tabs').querySelectorAll('[role=tab]')],i=tabs.indexOf(event.target);
      const next=event.key==='Home'?tabs[0]:event.key==='End'?tabs.at(-1):tabs[(i+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length];
      event.preventDefault();next.click();next.focus();
    });
    root.addEventListener('pagehide',()=>{observer.disconnect();clearTimeout(notificationTimer);},{once:true});
  }
  const api={request,RequestError,requestTimeout,busyButton,run,bindAction,waitForJob,region,notify,feedback,enhance};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else{root.MemoryUI=api;if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',boot,{once:true});else boot();}
})(typeof window!=='undefined'?window:globalThis);
