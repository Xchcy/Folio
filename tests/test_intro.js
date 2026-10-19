const {test}=require('node:test');
const assert=require('node:assert/strict');

test('logo sampling preserves the blue and orange silhouette and ignores empty pixels',async()=>{
  const {sampleLogo}=await import('../web/intro.js');
  const data=new Uint8ClampedArray(12*4);
  data.set([40,78,232,255],0);
  data.set([255,120,79,255],12);
  data.set([40,78,232,0],24);
  data.set([0,0,0,255],36);
  const points=sampleLogo({data,width:12,height:1});
  assert.deepEqual(points.map(p=>p.color),['#284ee8','#ff784f']);
  assert.ok(points.every(p=>p.u>0&&p.u<1&&p.v>0&&p.v<1));
  assert.equal(sampleLogo({data,width:12,height:1},1).length,1);
});

test('particles travel from their scattered start to the exact logo outline with bounded delay',async()=>{
  const {particlePosition}=await import('../web/intro.js');
  const particle={sx:-100,sy:600,tx:300,ty:200,delay:.18,curl:70};
  for(const t of [-1,0,.18])assert.deepEqual(particlePosition(particle,t),{x:-100,y:600});
  for(const t of [1,2])assert.deepEqual(particlePosition(particle,t),{x:300,y:200});
  const halfway=particlePosition(particle,.5);
  assert.ok(halfway.x>-100&&halfway.x<300);
  assert.ok(halfway.y>200&&halfway.y<600);
});

test('workspace links and reduced-motion preferences enter immediately without creating an overlay',async()=>{
  const {initIntro}=await import('../web/intro.js');
  for(const [hash,matches] of [['#workspace',false],['#home',true],['',true]]){
    const controller=initIntro({document:{createElement(){assert.fail('Unexpected intro overlay');}},
      window:{location:{hash},matchMedia:()=>({matches})}});
    await controller.done;
    controller.skip();
  }
});
