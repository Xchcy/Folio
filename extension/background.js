const safeUrl=value=>{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:'';}catch{return '';}};
chrome.runtime.onInstalled.addListener(()=>{chrome.contextMenus.removeAll(()=>chrome.contextMenus.create({id:'remember',title:'收集到 Folio',contexts:['selection','image','page']}));});
async function openCapture(info={},tab,blank=false){
  const id=crypto.randomUUID();
  let draft={text:info.selectionText||'',source_title:blank?'':tab?.title||'',source_url:blank?'':safeUrl(info.pageUrl||tab?.url),image_url:safeUrl(info.srcUrl),note:'',image_data:'',warning:''};
  if(info.srcUrl&&tab?.id){
    try{
      const result=await chrome.scripting.executeScript({target:{tabId:tab.id,frameIds:[info.frameId||0]},func:async src=>{
        try{
          const img=[...document.images].find(x=>x.currentSrc===src||x.src===src);
          if(!img||!img.naturalWidth)return {error:true};
          if(img.naturalWidth>4096||img.naturalHeight>4096)return {error:true};
          const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;canvas.getContext('2d').drawImage(img,0,0);
          const data=canvas.toDataURL('image/png');return data.length<5300000?{data}:{error:true};
        }catch{return {error:true};}
      },args:[info.srcUrl]});
      draft.image_data=result[0]?.result?.data||'';
    }catch{}
    if(!draft.image_data)draft.warning='网页限制了原图读取，目前仅保留图片链接。可粘贴图片或选择图片文件补充。';
  }
  // Only this explicit action collects content. No clipboard history or continuous page access.
  await chrome.storage.local.set({['draft-'+id]:draft});
  const bounds=await chrome.windows.getLastFocused();
  await chrome.windows.create({url:chrome.runtime.getURL('capture.html')+'?draft='+id,type:'popup',width:470,height:720,left:Math.max(0,(bounds.left||0)+(bounds.width||1000)-490),top:Math.max(0,(bounds.top||0)+80)});
}
chrome.contextMenus.onClicked.addListener((info,tab)=>{if(info.menuItemId==='remember')openCapture(info,tab);});
chrome.action.onClicked.addListener(tab=>openCapture({},tab));
chrome.commands.onCommand.addListener(command=>{if(command==='quick-capture')openCapture({},null,true);});
