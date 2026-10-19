// Optional visual effects. Reading, navigation and saving do not depend on them.
export function initMotion({document:doc=document,window:host=window}={}) {
  const reduced=host.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer=host.matchMedia('(hover: hover) and (pointer: fine)');
  const reveals=[...doc.querySelectorAll('[data-reveal]')];
  let active=null,surface=null,frame=null,point=null,observer=null;

  function resetPointer(){
    if(frame!==null)host.cancelAnimationFrame(frame);
    frame=null;point=null;
    if(surface){surface.style.removeProperty('--tilt-x');surface.style.removeProperty('--tilt-y');}
    active?.classList.remove('is-tilting');active=null;surface=null;
  }
  function paint(){
    frame=null;
    if(!active||!point)return;
    const bounds=active.getBoundingClientRect();
    if(!bounds.width||!bounds.height)return;
    const clamp=value=>Math.max(-1,Math.min(1,value));
    const requested=Number(active.dataset.tiltMax??3);
    const limit=Number.isFinite(requested)?Math.max(0,Math.min(6,requested)):3;
    const x=clamp((point.x-bounds.left)/bounds.width*2-1);
    const y=clamp((point.y-bounds.top)/bounds.height*2-1);
    surface.style.setProperty('--tilt-x',(-y*limit).toFixed(3)+'deg');
    surface.style.setProperty('--tilt-y',(x*limit).toFixed(3)+'deg');
  }
  function move(event){
    if(reduced.matches||!finePointer.matches||event.pointerType==='touch'||doc.body.classList.contains('opening-book')){
      resetPointer();return;
    }
    const target=event.target.closest?.('[data-pointer-tilt]');
    if(!target){resetPointer();return;}
    if(active!==target){
      resetPointer();active=target;surface=target.querySelector('[data-tilt-layer]')||target;
      active.classList.add('is-tilting');
    }
    point={x:event.clientX,y:event.clientY};
    if(frame===null)frame=host.requestAnimationFrame(paint);
  }
  function leave(event){if(active&&!active.contains(event.relatedTarget))resetPointer();}
  function revealAll(){
    reveals.forEach(element=>element.classList.remove('reveal-pending','is-visible'));
    observer?.disconnect();
  }
  function preferencesChanged(){resetPointer();if(reduced.matches)revealAll();}
  function keydown(event){if(event.key==='Tab')resetPointer();}
  function visibility(){if(doc.hidden)resetPointer();}
  function destroy(){
    resetPointer();revealAll();
    doc.removeEventListener('pointermove',move);
    doc.removeEventListener('pointerout',leave);
    doc.removeEventListener('keydown',keydown);
    doc.removeEventListener('visibilitychange',visibility);
    reduced.removeEventListener('change',preferencesChanged);
    finePointer.removeEventListener('change',preferencesChanged);
    host.removeEventListener('blur',resetPointer);
    host.removeEventListener('hashchange',resetPointer);
    host.removeEventListener('pagehide',destroy);
  }

  if(!reduced.matches&&typeof host.IntersectionObserver==='function'){
    observer=new host.IntersectionObserver(entries=>{
      for(const entry of entries){
        if(!entry.isIntersecting)continue;
        entry.target.classList.remove('reveal-pending');
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    },{threshold:.12,rootMargin:'0px 0px -18px 0px'});
    reveals.forEach(element=>{element.classList.add('reveal-pending');observer.observe(element);});
  }
  doc.addEventListener('pointermove',move,{passive:true});
  doc.addEventListener('pointerout',leave,{passive:true});
  doc.addEventListener('keydown',keydown);
  doc.addEventListener('visibilitychange',visibility);
  reduced.addEventListener('change',preferencesChanged);
  finePointer.addEventListener('change',preferencesChanged);
  host.addEventListener('blur',resetPointer);
  host.addEventListener('hashchange',resetPointer);
  host.addEventListener('pagehide',destroy,{once:true});
  return {destroy};
}
