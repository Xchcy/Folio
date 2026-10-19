const LOGO='/assets/folio-logo.png';
const BLUE='#284ee8',ORANGE='#ff784f';
const GATHER_RATE=.7,TRAVEL_RATE=.5;
const GATHER_START=120,GATHER_DURATION=1480/GATHER_RATE;
const NAMED_AT=GATHER_START+930/GATHER_RATE;
const FORMED_AT=GATHER_START+GATHER_DURATION+70;
const EXIT_AT=FORMED_AT+450,TRAVEL_DURATION=480/TRAVEL_RATE;

export function sampleLogo({data,width,height},maximum=1400){
  const points=[];
  for(let y=0;y<height;y+=3){
    for(let x=0;x<width;x+=3){
      const offset=(y*width+x)*4,r=data[offset],g=data[offset+1],b=data[offset+2];
      if(data[offset+3]<120||Math.max(r,g,b)<60)continue;
      points.push({u:(x+.5)/width,v:(y+.5)/height,color:r>b*1.15?ORANGE:BLUE});
    }
  }
  if(points.length<=maximum)return points;
  return Array.from({length:maximum},(_,i)=>points[Math.floor(i*points.length/maximum)]);
}

export function particlePosition(particle,progress){
  const t=Math.max(0,Math.min(1,(progress-particle.delay)/(1-particle.delay)));
  const ease=1-Math.pow(1-t,3),arc=Math.sin(t*Math.PI)*(1-t)*particle.curl;
  return {x:particle.sx+(particle.tx-particle.sx)*ease+arc,
          y:particle.sy+(particle.ty-particle.sy)*ease-arc*.65};
}

export function initIntro({document:doc=document,window:host=window}={}){
  const reduced=host.matchMedia('(prefers-reduced-motion: reduce)');
  if(reduced.matches||!['','#home'].includes(host.location.hash))return {done:Promise.resolve(),skip(){}};
  const overlay=doc.createElement('section');
  overlay.className='folio-intro';
  overlay.style.setProperty('--intro-outro-duration',`${TRAVEL_DURATION}ms`);
  overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');
  overlay.setAttribute('aria-label','Folio 品牌开场');
  overlay.innerHTML=`<canvas class="intro-particles" aria-hidden="true"></canvas>
    <div class="intro-lockup"><div class="intro-emblem" aria-hidden="true">
      <svg viewBox="265 168 786 955"><image href="${LOGO}" width="1254" height="1254"/></svg>
    </div><div class="intro-name">Folio</div><p class="intro-caption">个人工作记忆助手</p></div>
    <button class="intro-skip" type="button">跳过动画 <span aria-hidden="true">↗</span></button>`;
  doc.body.append(overlay);doc.body.classList.add('intro-active');
  const canvas=overlay.querySelector('canvas'),emblem=overlay.querySelector('.intro-emblem');
  const skip=overlay.querySelector('.intro-skip'),previous=doc.activeElement;
  let resolve,raf=null,exitTimer=null,watchdog=null,disposed=false,leaving=false;
  let points=[],particles=[],width=0,height=0,started=null,context;
  const animations=[];
  const done=new Promise(complete=>{resolve=complete;});
  function cleanup(){
    if(disposed)return;
    disposed=true;
    if(raf!==null)host.cancelAnimationFrame(raf);
    host.clearTimeout(exitTimer);host.clearTimeout(watchdog);
    animations.forEach(animation=>animation.cancel());
    doc.removeEventListener('keydown',keydown,true);
    doc.removeEventListener('visibilitychange',visibility);
    host.removeEventListener('resize',resize);
    host.removeEventListener('hashchange',routeChanged);
    host.removeEventListener('pagehide',cleanup);
    reduced.removeEventListener('change',preferenceChanged);
    const restore=overlay.contains(doc.activeElement);
    overlay.remove();doc.body.classList.remove('intro-active');
    if(restore&&doc.visibilityState!=='hidden'){
      const target=previous&&previous!==doc.body&&previous.isConnected&&!previous.closest('[hidden]')?previous:
        doc.getElementById(host.location.hash==='#workspace'?'workspace':'home');
      target?.focus({preventScroll:true});
    }
    resolve();
  }
  function finish(){
    if(disposed||leaving)return;
    leaving=true;raf=null;
    overlay.classList.add('is-leaving');
    const target=doc.querySelector('.app-nav .folio-mark');
    if(target&&typeof emblem.animate==='function'){
      const from=emblem.getBoundingClientRect(),to=target.getBoundingClientRect();
      if(from.width&&to.width){
        animations.push(emblem.animate([{transform:'translate(0,0) scale(1)'},
          {transform:`translate(${to.left-from.left}px,${to.top-from.top}px) scale(${to.width/from.width})`}],
          {duration:TRAVEL_DURATION,easing:'cubic-bezier(.4,0,.2,1)',fill:'forwards'}));
      }
    }
    exitTimer=host.setTimeout(cleanup,TRAVEL_DURATION+20);
  }
  function keydown(event){
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();cleanup();}
    if(event.key==='Tab'){event.preventDefault();skip.focus({preventScroll:true});}
  }
  function visibility(){if(doc.hidden)cleanup();}
  function routeChanged(){if(!['','#home'].includes(host.location.hash))cleanup();}
  function preferenceChanged(){if(reduced.matches)cleanup();}
  function resize(){
    if(disposed||leaving||!context||!points.length)return;
    width=host.innerWidth;height=host.innerHeight;
    const ratio=Math.min(host.devicePixelRatio||1,2);
    canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
    context.setTransform(ratio,0,0,ratio,0,0);
    const bounds=emblem.getBoundingClientRect();
    particles=points.map((point,index)=>({color:point.color,
      sx:width/2+(Math.random()-.5)*width*1.3,sy:height/2+(Math.random()-.5)*height*1.3,
      tx:bounds.left+point.u*bounds.width,ty:bounds.top+point.v*bounds.height,
      delay:(index%19)/100,curl:(Math.random()-.5)*130,radius:.85+(index%4)*.2}));
  }
  function draw(time){
    if(disposed)return;
    try{
      if(started===null)started=time;
      const elapsed=time-started;
      context.clearRect(0,0,width,height);
      const progress=Math.max(0,Math.min(1,(elapsed-GATHER_START)/GATHER_DURATION));
      context.globalAlpha=Math.min(1,elapsed/200);
      for(const particle of particles){
        const position=particlePosition(particle,progress);
        context.fillStyle=particle.color;context.beginPath();
        context.arc(position.x,position.y,particle.radius,0,Math.PI*2);context.fill();
      }
      if(elapsed>NAMED_AT)overlay.classList.add('is-named');
      if(elapsed>FORMED_AT)overlay.classList.add('is-formed');
      if(elapsed>=EXIT_AT){finish();return;}
      raf=host.requestAnimationFrame(draw);
    }catch{cleanup();}
  }
  async function prepare(){
    try{
      context=canvas.getContext('2d');
      if(!context){cleanup();return;}
      const image=new host.Image();image.src=LOGO;
      await image.decode();
      if(disposed)return;
      const mask=doc.createElement('canvas');mask.width=176;mask.height=216;
      const sampler=mask.getContext('2d',{willReadFrequently:true});
      if(!sampler){cleanup();return;}
      sampler.drawImage(image,275,178,766,935,0,0,176,216);
      points=sampleLogo(sampler.getImageData(0,0,176,216),width<690?650:1400);
      if(!points.length){cleanup();return;}
      resize();raf=host.requestAnimationFrame(draw);
    }catch{cleanup();}
  }
  width=host.innerWidth;
  skip.onclick=cleanup;skip.focus({preventScroll:true});
  doc.addEventListener('keydown',keydown,true);
  doc.addEventListener('visibilitychange',visibility);
  host.addEventListener('resize',resize);
  host.addEventListener('hashchange',routeChanged);
  host.addEventListener('pagehide',cleanup,{once:true});
  reduced.addEventListener('change',preferenceChanged);
  watchdog=host.setTimeout(cleanup,8000);
  prepare();
  return {done,skip:cleanup};
}
