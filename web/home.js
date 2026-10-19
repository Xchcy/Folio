(function(root){
  // Navigation is committed once, after the visual effect; animation errors cannot block entry.
  function createEntrance({play,enter,onError=()=>{}}){
    let pending=null,controller;
    return {
      open(){
        if(pending)return pending;
        controller=new AbortController();const signal=controller.signal;
        pending=Promise.resolve().then(()=>{if(!signal.aborted)return play(signal);}).catch(error=>{if(!signal.aborted)onError(error);}).then(()=>{if(!signal.aborted)enter();}).finally(()=>{pending=null;});
        return pending;
      },
      cancel(){controller?.abort();},
      get active(){return !!pending;}
    };
  }
  if(typeof module!=='undefined'&&module.exports){module.exports={createEntrance};return;}
  const doc=root.document,byId=id=>doc.getElementById(id);
  function boot(){
    const book=byId('memory-book'),button=byId('open-memory'),library=byId('library-dialog');
    let entrance;
    function enter(){
      doc.body.classList.add('workspace-reveal');
      root.location.hash='workspace';doc.dispatchEvent(new Event('memory:navigate'));
      byId('workspace').focus({preventScroll:true});
    }
    async function play(signal){
      if(root.matchMedia('(prefers-reduced-motion: reduce)').matches||typeof book.animate!=='function')return;
      const rect=book.getBoundingClientRect();
      const initialTransform=root.getComputedStyle(book.querySelector('.book-object')).transform;
      const initialTilt=root.getComputedStyle(book.querySelector('.book-parallax')).transform;
      const overlay=doc.createElement('div');overlay.className='book-transition';overlay.setAttribute('aria-hidden','true');
      const wipe=doc.createElement('div');wipe.className='book-wipe';
      const flight=doc.createElement('div');flight.className='book-flight';
      Object.assign(flight.style,{left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px'});
      const object=book.querySelector('.book-object').cloneNode(true);object.style.transform=initialTransform;flight.append(object);overlay.append(wipe,flight);doc.body.append(overlay);
      const animations=[];let finish;
      const abort=()=>animations.forEach(animation=>animation.cancel());
      signal.addEventListener('abort',abort,{once:true});
      const animate=(node,frames,options)=>{const animation=node.animate(frames,{fill:'forwards',...options});animation.playbackRate=.7;animations.push(animation);return animation;};
      try{
        doc.body.classList.add('opening-book');book.setAttribute('aria-busy','true');
        finish=root.MemoryUI.busyButton(button,'正在打开…');
        const scale=Math.min(1.28,(root.innerWidth-42)/(rect.width*1.82),(root.innerHeight-80)/rect.height);
        const dx=root.innerWidth/2-rect.left-rect.width*.17;
        const dy=root.innerHeight/2-rect.top-rect.height/2;
        const movement=animate(flight,[{transform:'translate(0,0) scale(1)'},{transform:`translate(${dx}px,${dy}px) scale(${scale})`}],{duration:350,easing:'cubic-bezier(.2,.75,.2,1)'});
        animate(object,[{transform:initialTransform},{transform:'rotateX(0deg) rotateY(0deg) rotateZ(0deg)'}],{duration:350,easing:'ease-out'});
        animate(object.querySelector('.book-parallax'),[{transform:initialTilt},{transform:'rotateX(0deg) rotateY(0deg)'}],{duration:350,easing:'ease-out'});
        await movement.finished;if(signal.aborted)return;
        animate(object.querySelector('.book-cover'),[{transform:'translateZ(1px) rotateY(0deg)'},{transform:'translateZ(1px) rotateY(-163deg)'}],{duration:430,easing:'cubic-bezier(.3,.1,.3,1)'});
        const leaves=[...object.querySelectorAll('.book-leaf')].reverse();
        leaves.forEach((leaf,index)=>animate(leaf,[{transform:`translateZ(${-1-index*2}px) rotateY(0deg)`},{transform:`translateZ(${-1-index*2}px) rotateY(${-157+index*5}deg)`}],{duration:400,delay:75+index*65,easing:'cubic-bezier(.35,.05,.25,1)'}));
        const reveal=animate(wipe,[{opacity:0},{opacity:1}],{duration:220,delay:400});
        animate(flight,[{opacity:1},{opacity:0}],{duration:180,delay:460});
        await reveal.finished;
      }finally{
        signal.removeEventListener('abort',abort);abort();overlay.remove();
        doc.body.classList.remove('opening-book');book.removeAttribute('aria-busy');finish?.();
        if(signal.aborted&&doc.body.classList.contains('home-view')&&doc.visibilityState!=='hidden')book.focus({preventScroll:true});
      }
    }
    entrance=createEntrance({play,enter});
    book.onclick=button.onclick=()=>entrance.open();
    byId('skip-book').addEventListener('click',()=>entrance.cancel());
    const showLibrary=()=>{if(!library.open)library.showModal();};
    byId('home-library').onclick=byId('nav-library').onclick=showLibrary;
    byId('close-library').onclick=()=>library.close();
    library.addEventListener('click',event=>{if(event.target.closest('[data-open-topic],a[href="#workspace"],#empty-import'))library.close();});
    doc.querySelector('.app-nav').addEventListener('click',event=>{if(event.target.closest('.nav-more-panel button'))doc.querySelector('.nav-more').open=false;});
    doc.addEventListener('click',event=>{if(!event.target.closest('.nav-more'))doc.querySelector('.nav-more').open=false;});
    doc.addEventListener('keydown',event=>{if(event.key==='Escape'){doc.querySelector('.nav-more').open=false;if(entrance.active)entrance.cancel();}});
    root.addEventListener('hashchange',()=>{if(root.location.hash!=='#home'&&root.location.hash!=='')entrance.cancel();});
    root.addEventListener('pagehide',()=>entrance.cancel(),{once:true});
    byId('workspace').addEventListener('animationend',()=>doc.body.classList.remove('workspace-reveal'));
  }
  if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})(typeof window!=='undefined'?window:globalThis);
