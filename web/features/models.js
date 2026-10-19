export function initModels(ctx) {
  const {$,api,toast,escape}=ctx;
async function loadModelSettings() {
  const config=await api('/api/model-config');
  $('model-status').textContent=config.has_key?`${config.model} · 仅合成案例`:'外部模型未配置 Key';
  if(ctx.state)ctx.todos.updateModel(config);
  return config;
}
$('model-settings').onclick=async()=>{try{const c=await loadModelSettings();$('model-base').value=c.base_url;$('model-name').value=c.model;$('model-key').value='';$('model-key').placeholder=c.has_key?'已配置；留空保留，重启后需重新填写':'填写 API Key';$('model-result').hidden=true;$('model-dialog').showModal();}catch(e){toast(e.message);}};
$('close-model').onclick=()=>{$('model-key').value='';$('model-dialog').close();};
$('model-dialog').addEventListener('close',()=>{$('model-key').value='';});
async function saveModel(clear=false) {
  const result=await api('/api/model-config',{base_url:$('model-base').value,model:$('model-name').value,api_key:clear?'':$('model-key').value,clear});
  $('model-key').value='';$('model-key').placeholder=result.has_key?'已配置；留空保留':'填写 API Key';await loadModelSettings();return result;
}
$('model-form').onsubmit=async e=>{e.preventDefault();try{await saveModel();toast('配置已保存。模型名称可随时更换；Key 仅保留在当前服务内存。');}catch(error){toast(error.message);}};
$('clear-model').onclick=async()=>{try{await saveModel(true);toast('API Key 已从服务内存清除');}catch(e){toast(e.message);}};
$('test-model').onclick=async()=>{
  const b=$('test-model');b.disabled=true;b.textContent='正在验证合成对话…';
  try{await saveModel();const r=await api('/api/model-test',{});$('model-result').hidden=false;$('model-result').innerHTML=`<h3>${escape(r.model)} · 验证通过</h3><p>${escape(r.note)}</p>${r.events.map(m=>`<p>${escape(m.title)}${m.due?' · '+escape(m.due):''}（待确认）</p>`).join('')||'<p>本次未提取到事件</p>'}`;}
  catch(e){$('model-result').hidden=false;$('model-result').textContent=e.message;}finally{b.disabled=false;b.textContent='测试合成对话';}
};

  ctx.bindActions([["model-form", "onsubmit", "保存中…"], ["clear-model", "onclick", "清除中…"], ["test-model", "onclick", "验证中…"], ["model-settings", "onclick", "读取配置…"]]);
  return {loadSettings:loadModelSettings};
}
