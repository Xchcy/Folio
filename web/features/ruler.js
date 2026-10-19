import {paperStatuses} from '../papers.js';

export function unfinishedItems(memories,todos){
  const ids=new Set([...todos.select(memories,'active'),...todos.select(memories,'waiting')].map(m=>m.id));
  return memories.filter(m=>m.status==='confirmed'&&m.event!=='cancellation'&&ids.has(m.id))
    .sort((a,b)=>(a.due||'9999').localeCompare(b.due||'9999')||String(a.id).localeCompare(String(b.id)));
}

export function initRuler(ctx){
  const {$,escape}=ctx;
  const rail=document.createElement('nav');
  rail.className='workspace-ruler';rail.setAttribute('aria-label','纸条刻度导航');rail.hidden=true;
  const preview=document.createElement('div');
  preview.className='ruler-preview';preview.id='ruler-preview';preview.role='tooltip';preview.hidden=true;
  document.body.append(rail,preview);
  const home=$('home-task-ruler');
  let rows=[],frame=0,current=-1,homeItems=[],scope='',opening=false;
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  function hidePreview(){preview.hidden=true;document.querySelectorAll('[aria-describedby="ruler-preview"]').forEach(n=>n.removeAttribute('aria-describedby'));}
  function showPreview(button,item){
    hidePreview();
    const dots=paperStatuses(item);
    preview.innerHTML=`<div class="ruler-preview-meta"><span>${escape(item.topic||'来源消息')}</span><time>${escape((item.timestamp||'').slice(0,10))}</time></div><strong>${escape(item.paper_summary||item.title||item.text||'暂无文字内容')}</strong><div class="ruler-preview-status">${dots.map(d=>`<span class="paper-state" data-tone="${escape(d.tone)}"><i aria-hidden="true"></i>${escape(d.label)}</span>`).join('')}</div><small>${button.closest('#home-task-ruler')?'点击接着处理':'点击定位纸条'}</small>`;
    preview.hidden=false;button.setAttribute('aria-describedby',preview.id);
    const r=button.getBoundingClientRect(),p=preview.getBoundingClientRect();
    const isHome=!!button.closest('#home-task-ruler');
    preview.style.left=Math.max(12,Math.min(isHome?r.x-p.width/2+r.width/2:r.right+12,window.innerWidth-p.width-12))+'px';
    preview.style.top=Math.max(90,Math.min(isHome?r.top-p.height-14:r.y-p.height/2,window.innerHeight-p.height-12))+'px';
  }
  function mark(index){
    if(index===current)return;
    current=index;
    [...rail.children].forEach((button,i)=>{
      button.classList.toggle('is-current',i===index);button.tabIndex=i===index?0:-1;
      if(i===index)button.setAttribute('aria-current','location');else button.removeAttribute('aria-current');
    });
    const button=rail.children[index];
    if(button){if(button.offsetTop<rail.scrollTop)rail.scrollTop=button.offsetTop;else if(button.offsetTop+button.offsetHeight>rail.scrollTop+rail.clientHeight)rail.scrollTop=button.offsetTop+button.offsetHeight-rail.clientHeight;}
  }
  function track(){
    frame=0;if(document.body.classList.contains('home-view')||!rows.length)return;
    const sidebar=document.querySelector('.sidebar').getBoundingClientRect();
    const workspace=$('workspace').getBoundingClientRect();
    const header=document.querySelector('.app-nav').getBoundingClientRect();
    const mobile=window.innerWidth<=690;
    const top=mobile?Math.max(header.bottom+16,workspace.top+16):Math.max(header.bottom+24,window.innerHeight*.24);
    rail.style.left=(mobile?1:sidebar.right+6)+'px';
    rail.style.top=top+'px';
    rail.style.height=Math.max(0,Math.min(window.innerHeight*.56,window.innerHeight-top-24))+'px';
    rail.style.visibility=top<window.innerHeight-64?'visible':'hidden';
    let nearest=0,distance=Infinity;
    rows.forEach((row,i)=>{const r=row.note.getBoundingClientRect();const d=Math.abs(r.top-window.innerHeight*.4);if(d<distance){nearest=i;distance=d;}});
    mark(nearest);
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(track);}
  function clearWorkspace(){rows=[];current=-1;rail.replaceChildren();rail.hidden=true;hidePreview();}
  function clear(){clearWorkspace();homeItems=[];home.replaceChildren();$('home-task-count').textContent='正在读取事项…';}
  function renderWorkspace(){
    clearWorkspace();scope=ctx.state.mode;
    const items=new Map((ctx.view==='messages'?ctx.sourceMessages():ctx.state.memories).map(m=>[String(m.id),m]));
    rows=[...$('memories').querySelectorAll('.paper-note')].map(note=>({note,item:items.get(note.dataset.paperKey.slice((ctx.state.mode+':'+(ctx.view==='messages'?'message':'memory')+':').length))})).filter(r=>r.item);
    rail.innerHTML=rows.map(({item},i)=>`<button type="button" class="ruler-tick" data-ui-ready="true" data-index="${i}" aria-label="第 ${i+1} 条：${escape(item.paper_summary||item.title||item.text||'原话')}" tabindex="${i?-1:0}"><i></i></button>`).join('');
    rail.hidden=!rows.length;schedule();
  }
  async function openHome(index){
    if(opening)return;
    const item=homeItems[index];if(!item||ctx.state.mode!==scope)return;
    const requestedMode=ctx.state.mode;opening=true;hidePreview();
    const button=home.querySelector(`[data-index="${index}"]`);button?.setAttribute('aria-busy','true');
    try{
      ctx.topic=item.topic;ctx.view='timeline';location.hash='workspace';ctx.navigation.navigatePage();
      await ctx.load({resetScroll:true});
      if(ctx.state.mode!==requestedMode||ctx.topic!==item.topic)return;
      const note=[...$('memories').querySelectorAll('.paper-note')].find(n=>n.dataset.recordId===String(item.id));
      if(note){note.scrollIntoView({block:'center',behavior:'instant'});ctx.papers.open(note);}
    }catch(error){ctx.toast(error.message);}finally{opening=false;button?.removeAttribute('aria-busy');}
  }
  function renderHome(){
    scope=ctx.state.mode;hidePreview();homeItems=unfinishedItems(ctx.state.memories,MemoryTodos);
    $('home-task-count').textContent=homeItems.length?`${homeItems.length} 件已确认，待完成`:'暂无已确认的未完成事项';
    home.innerHTML=homeItems.map((item,i)=>`<button type="button" data-ui-ready="true" class="ruler-tick home-task-tick ${MemoryTodos.traits(item).role==='waiting'?'is-waiting':''}" data-index="${i}" aria-label="${escape(item.paper_summary||item.title)}" tabindex="${i?-1:0}"><i></i></button>`).join('');
  }
  for(const node of [rail,home]){
    const itemFor=button=>node===rail?rows[Number(button.dataset.index)]?.item:homeItems[Number(button.dataset.index)];
    node.addEventListener('pointerover',event=>{const button=event.target.closest('button');if(button&&itemFor(button))showPreview(button,itemFor(button));});
    node.addEventListener('pointerleave',hidePreview);
    node.addEventListener('focusin',event=>{const button=event.target.closest('button');requestAnimationFrame(()=>{if(button?.isConnected&&document.activeElement===button&&itemFor(button))showPreview(button,itemFor(button));});});
    node.addEventListener('focusout',hidePreview);
    node.addEventListener('keydown',event=>{
      if(event.key==='Escape'){hidePreview();return;}
      if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      event.preventDefault();const buttons=[...node.children],index=buttons.indexOf(event.target.closest('button'));
      const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,index+(['ArrowUp','ArrowLeft'].includes(event.key)?-1:1)));
      buttons.forEach((b,i)=>b.tabIndex=i===next?0:-1);buttons[next]?.focus({preventScroll:true});if(buttons[next]&&itemFor(buttons[next]))showPreview(buttons[next],itemFor(buttons[next]));
    });
    node.addEventListener('click',event=>{
      const button=event.target.closest('button');if(!button)return;const index=Number(button.dataset.index);
      hidePreview();
      if(node===home){openHome(index);return;}
      const row=rows[index];if(!row)return;
      row.note.scrollIntoView({block:'center',behavior:reduced.matches?'instant':'smooth'});
      row.note.querySelector('.paper-head').focus({preventScroll:true});mark(index);
    });
  }
  function route(){hidePreview();if(location.hash==='#workspace')schedule();}
  window.addEventListener('scroll',()=>{hidePreview();schedule();},{passive:true});
  window.addEventListener('resize',()=>{hidePreview();schedule();},{passive:true});
  window.addEventListener('hashchange',route);
  document.addEventListener('memory:navigate',route);
  window.addEventListener('pagehide',()=>{cancelAnimationFrame(frame);hidePreview();},{once:true});
  return {clear,clearWorkspace,renderWorkspace,renderHome};
}
