export function initNavigation(ctx) {
  const {$,load,toast}=ctx;
function navigatePage() {
  const home=location.hash!=='#workspace';
  document.body.classList.toggle('home-view',home);
  $('home').hidden=!home;
  $('todo-widget').hidden=home;
  $('workspace').hidden=home;
  document.querySelector('.sidebar').hidden=home;
  document.querySelector('.evidence-panel').hidden=home;
  document.querySelectorAll('[data-page]').forEach(a=>{if(a.dataset.page===(home?'home':'workspace'))a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  document.querySelector('.skip-link').href=home?'#home':'#workspace';
  if(home)document.body.classList.remove('evidence-open');
  window.scrollTo(0,0);
}
window.addEventListener('hashchange',navigatePage);
$('home-settings').onclick=()=>{$('workspace-tools-dialog').showModal();document.querySelector('.nav-more').open=false;};
$('open-all-todos').onclick=()=>{
 location.hash='workspace';navigatePage();document.querySelector('.nav-more').open=false;
 document.body.classList.add('todos-visible');
 if($('todo-toggle').getAttribute('aria-expanded')!=='true')$('todo-toggle').click();
 $('todo-toggle').focus();
};
$('todo-toggle').addEventListener('click',()=>{if($('todo-toggle').getAttribute('aria-expanded')==='false')document.body.classList.remove('todos-visible');});
$('workspace-tools-close').onclick=()=>$('workspace-tools-dialog').close();
$('workspace-add').onclick=()=>$('workspace-add-dialog').showModal();
$('workspace-wechat').onclick=()=>$('wechat-import').click();
$('workspace-add-close').onclick=()=>$('workspace-add-dialog').close();
for(const id of ['workspace-add-dialog','workspace-tools-dialog']){
  $(id).addEventListener('click',e=>{
    if(e.target.closest('#add-wechat,#wechat-import,#sync,#model-settings'))$(id).close();
  },true);
}

$('home-import').onclick=()=>{location.hash='workspace';$('wechat-import').click();};
$('home-topics').addEventListener('click',e=>{const card=e.target.closest('[data-open-topic]');if(!card)return;ctx.topic=card.dataset.openTopic;ctx.view='timeline';$('answer').hidden=true;location.hash='workspace';load({resetScroll:true}).catch(e=>toast(e.message));});
navigatePage();


  return {navigatePage};
}
