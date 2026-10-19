const {test}=require('node:test');
const assert=require('node:assert/strict');

function events(){
  const handlers=new Map();
  return {
    addEventListener(name,fn){handlers.set(name,fn);},
    removeEventListener(name,fn){if(handlers.get(name)===fn)handlers.delete(name);},
    dispatch(name,event={}){handlers.get(name)?.(event);},
    get listenerCount(){return handlers.size;}
  };
}
function element(){
  const classes=new Set(),values=new Map();
  return {classList:{add:(...names)=>names.forEach(n=>classes.add(n)),remove:(...names)=>names.forEach(n=>classes.delete(n)),contains:n=>classes.has(n)},
    style:{setProperty:(name,value)=>values.set(name,value),removeProperty:name=>values.delete(name),getPropertyValue:name=>values.get(name)||''}};
}
async function runtime({reduce=false,fine=true,intersection=true}={}){
  const {initMotion}=await import('../web/motion.js');
  const reduced={...events(),matches:reduce},pointer={...events(),matches:fine};
  const surface=element(),book={...element(),dataset:{tiltMax:'3'},
    getBoundingClientRect:()=>({left:100,top:50,width:200,height:300}),
    querySelector:()=>surface,contains:node=>node===book};
  const reveal=element(),frames=new Map();let observer,next=0;
  const doc={...events(),body:element(),hidden:false,querySelectorAll:()=>[reveal]};
  const host={...events(),matchMedia:query=>query.includes('reduced')?reduced:pointer,
    requestAnimationFrame:fn=>{frames.set(++next,fn);return next;},cancelAnimationFrame:id=>frames.delete(id)};
  if(intersection)host.IntersectionObserver=class {
    constructor(callback){this.callback=callback;this.observed=new Set();observer=this;}
    observe(target){this.observed.add(target);}
    unobserve(target){this.observed.delete(target);}
    disconnect(){this.observed.clear();}
  };
  const controller=initMotion({document:doc,window:host});
  return {controller,doc,host,surface,book,reveal,reduced,pointer,frames,get observer(){return observer;},
    move(x,y,type='mouse'){doc.dispatch('pointermove',{target:{closest:()=>book},clientX:x,clientY:y,pointerType:type});},
    paint(){const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn());}};
}

test('pointer movement tilts the book within limits and leaving returns it to the front',async()=>{
  const r=await runtime();
  r.move(300,350);r.paint();
  assert.equal(r.surface.style.getPropertyValue('--tilt-x'),'-3.000deg');
  assert.equal(r.surface.style.getPropertyValue('--tilt-y'),'3.000deg');
  r.move(200,200);r.paint();
  assert.equal(Number.parseFloat(r.surface.style.getPropertyValue('--tilt-x')),0);
  assert.equal(Number.parseFloat(r.surface.style.getPropertyValue('--tilt-y')),0);
  r.move(1000,-1000);r.paint();
  assert.equal(r.surface.style.getPropertyValue('--tilt-x'),'3.000deg');
  r.doc.dispatch('pointerout',{relatedTarget:null});
  assert.equal(r.surface.style.getPropertyValue('--tilt-y'),'');
  assert.equal(r.book.classList.contains('is-tilting'),false);
  r.controller.destroy();
});
test('touch and reduced-motion users retain visible content without pointer tilt',async()=>{
  for(const options of [{reduce:true},{fine:false}]){
    const r=await runtime(options);r.move(300,350);r.paint();
    assert.equal(r.surface.style.getPropertyValue('--tilt-x'),'');
    if(options.reduce)assert.equal(r.reveal.classList.contains('reveal-pending'),false);
    r.controller.destroy();
  }
  const r=await runtime();r.move(300,350,'touch');r.paint();
  assert.equal(r.frames.size,0);assert.equal(r.book.classList.contains('is-tilting'),false);
  r.controller.destroy();
});
test('elements reveal once and remain readable without IntersectionObserver',async()=>{
  const r=await runtime();
  assert.equal(r.reveal.classList.contains('reveal-pending'),true);
  r.observer.callback([{target:r.reveal,isIntersecting:true}]);
  assert.equal(r.reveal.classList.contains('is-visible'),true);
  assert.equal(r.reveal.classList.contains('reveal-pending'),false);
  assert.equal(r.observer.observed.size,0);
  r.controller.destroy();
  const fallback=await runtime({intersection:false});
  assert.equal(fallback.reveal.classList.contains('reveal-pending'),false);
  fallback.controller.destroy();
});
test('route changes, opening transitions and cleanup cancel queued pointer updates',async()=>{
  const r=await runtime();r.move(300,350);assert.equal(r.frames.size,1);
  r.host.dispatch('hashchange');assert.equal(r.frames.size,0);r.paint();
  assert.equal(r.surface.style.getPropertyValue('--tilt-y'),'');
  r.doc.body.classList.add('opening-book');r.move(300,350);assert.equal(r.frames.size,0);
  r.doc.body.classList.remove('opening-book');r.move(300,350);r.paint();
  r.reduced.matches=true;r.reduced.dispatch('change');
  assert.equal(r.surface.style.getPropertyValue('--tilt-y'),'');
  assert.equal(r.reveal.classList.contains('reveal-pending'),false);
  r.controller.destroy();
  assert.equal(r.doc.listenerCount,0);assert.equal(r.host.listenerCount,0);
});
