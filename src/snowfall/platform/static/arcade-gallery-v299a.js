/* v2.9.9a — full illustrated Snowball Target Gallery using the reusable
   v2.9.9 mountScene host. Server decides every hit, time and practice score. */
(function(global){
"use strict";
const WIDTH=640,HEIGHT=360,LIMIT=45000;
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
function mount({root,session,start,control,shot,refresh,onExit}){
 if(!global.SnowfallArcadeV299?.mountScene)
  throw Error("Arcade 2.0 screen is not available.");
 let current=session,reference=performance.now(),lastRefresh=0;
 let refreshing=false,unconfirmed=null,impact=null,record=null;
 const backdrop=new Image();
 backdrop.src="/art/v290/arcade/gallery.webp";
 function apply(next){
  if(!next||!Array.isArray(next.schedule)||next.mode!=="gallery")
   throw Error("Invalid gallery session response.");
  if(next.session_id!==current.session_id){
   unconfirmed=null;record=null;
  }
  current=next;reference=performance.now();
  host?.update();
 }
 function elapsed(){
  const ms=Number(current.elapsed_ms)||0;
  return clamp(Math.round(ms+(current.status==="active"?
   Math.max(0,performance.now()-reference):0)),0,LIMIT);
 }
 function position(t,ms){
  return {x:t.x0+t.amp*Math.sin(t.phase+(ms-t.start)/1000*t.rate),y:t.y};
 }
 const path="/v1/game/arcade/gallery";
 async function resync(){
  if(refreshing||current.status!=="active")return;
  refreshing=true;
  const id=current.session_id,shots=current.shots_used;
  try{
   const next=await refresh(id);
   if(current.session_id===id&&next.shots_used>=shots)apply(next);
  }finally{refreshing=false}
 }
 async function begin(){
  const result=current.status==="finished"?
   await start():
   current.status==="paused"?await control(current.session_id,"resume"):current;
  apply(result);
 }
 async function pause(){
  if(current.status==="active")apply(await control(current.session_id,"pause"));
 }
 async function finish(){
  if(current.status!=="finished")apply(await control(current.session_id,"finish"));
 }
 async function shootAt({x,y}){
  if(current.status!=="active"||current.ammo<=0)return null;
  const body=unconfirmed||{session_id:current.session_id,shot_index:current.shots_used,x,y};
  try{
   const next=await shot(body);
   apply(next);
   unconfirmed=null;
   const effect=next.last_event||{};
   impact={x:body.x,y:body.y,until:performance.now()+450,
    outcome:effect.outcome||"miss"};
   return effect;
  }catch(e){
   // Preserve the exact body/idempotency key on uncertain requests. New taps
   // retry the SAME shot; never spend another ball to paper over a timeout.
   unconfirmed=body;
   try{
    const snap=await refresh(body.session_id);
    if(snap.shots_used>body.shot_index){
     apply(snap);unconfirmed=null;
     return {outcome:"hit",feedback:"Previous throw confirmed; gallery resynchronised."};
    }
   }catch{}
   throw e;
  }
 }
 async function close(){
  if(current.status==="active")await pause();
  onExit?.();
 }
 function render(ctx,{time,aim,reduced}){
  const ms=elapsed(),seconds=ms/1000,wave=clamp(Math.floor(ms/15000)+1,1,3);
  let gradient=ctx.createLinearGradient(0,0,0,HEIGHT);
  gradient.addColorStop(0,"#142b3c");gradient.addColorStop(1,"#274b5b");
  ctx.fillStyle=gradient;ctx.fillRect(0,0,WIDTH,HEIGHT);
  if(backdrop.complete&&backdrop.naturalWidth){
   ctx.save();ctx.globalAlpha=.24;
   ctx.drawImage(backdrop,0,0,WIDTH,HEIGHT);ctx.restore();
  }
  // Mid-century fairground booth / three shooting lanes, fixed geometry.
  ctx.fillStyle="#513d31";ctx.fillRect(0,64,WIDTH,12);
  ctx.fillStyle="#74523a";ctx.fillRect(0,99,WIDTH,10);
  for(let row=0;row<3;row++){
   const top=116+row*73;
   ctx.fillStyle=row%2?"#233e4b":"#19323f";
   ctx.fillRect(22,top,596,62);
   ctx.strokeStyle="#9f7e55";ctx.lineWidth=4;ctx.strokeRect(22,top,596,62);
  }
  ctx.fillStyle="#73543e";ctx.fillRect(0,322,WIDTH,38);
  ctx.fillStyle="#edc98b";ctx.font="bold 16px Georgia";
  ctx.fillText("THE FROSTED SHOOTING GALLERY",123,40);
  ctx.font="13px sans-serif";ctx.fillStyle="#d9e8ed";
  ctx.fillText("WAVE "+wave+"  •  "+["Easy rollers","Quick pop-ups","Blizzard blitz"][wave-1],202,61);
  if(!reduced){
   ctx.fillStyle="rgba(233,247,251,.5)";
   for(let i=0;i<26;i++){
    const px=(i*107+13+time*.006*(i%3+1))%640;
    const py=(i*61+time*.012*(i%4+1))%320;
    ctx.beginPath();ctx.arc(px,py,1.4,0,Math.PI*2);ctx.fill();
   }
  }
  const claimed=new Set(current.claimed||[]);
  for(const t of current.schedule){
   if(claimed.has(t.id)||ms<t.start||ms>=t.start+t.life)continue;
   const p=position(t,ms),r=t.radius;
   ctx.save();
   ctx.shadowColor=t.kind==="gold"?"#ffda71":"#b1def1";ctx.shadowBlur=t.kind==="gold"?23:7;
   ctx.fillStyle="#1f242c";ctx.fillRect(p.x-4,p.y+r,8,26);
   if(t.kind==="decoy"){
    circle(ctx,p.x,p.y,r+3,"#dbe5eb");
    circle(ctx,p.x,p.y,r-5,"#293941");
    ctx.fillStyle="#ffe2ae";ctx.font="bold 15px sans-serif";
    ctx.textAlign="center";ctx.fillText("NO",p.x,p.y+6);
   }else if(t.kind==="gold"){
    circle(ctx,p.x,p.y,r+6,"#8a5d22");
    circle(ctx,p.x,p.y,r,"#ffe195");
    star(ctx,p.x,p.y,5,r*.76,r*.36,"#ae762e");
   }else{
    circle(ctx,p.x,p.y,r+6,"#b9d8e4");
    circle(ctx,p.x,p.y,r,"#b74648");
    circle(ctx,p.x,p.y,r*.64,"#f3f1dc");
    circle(ctx,p.x,p.y,r*.32,"#bb3f45");
   }
   ctx.restore();
  }
  if(impact&&impact.until>time){
   ctx.save();ctx.globalAlpha=(impact.until-time)/450;
   circle(ctx,impact.x,impact.y,Math.max(8,(450-(impact.until-time))*.19),
    impact.outcome==="gold"?"#ffd778":"#e9f6ff");
   ctx.restore();
  }
  ctx.fillStyle="#e8d3aa";ctx.font="bold 14px sans-serif";
  ctx.fillText("🎯 Standard +7    ✦ Gold +15    ⊘ Decoy −9    Miss −2",89,346);
  if(current.status!=="active"){
   ctx.fillStyle="rgba(9,25,34,.8)";
   ctx.fillRect(65,100,510,214);
   ctx.strokeStyle="#dbc28b";ctx.lineWidth=2;ctx.strokeRect(65,100,510,214);
   ctx.fillStyle="#f9e9c8";ctx.font="bold 27px Georgia";
   ctx.textAlign="center";
   ctx.fillText(current.status==="finished"?"GALLERY COMPLETE":"READY WHEN YOU ARE",320,164);
   ctx.font="bold 20px sans-serif";
   ctx.fillText(current.status==="finished"?
    current.result+"  "+current.score+"/100": "45 seconds · 3 waves · 32 snowballs",320,205);
   ctx.font="16px sans-serif";
   ctx.fillStyle="#d5e7ed";
   ctx.fillText(current.status==="finished"?
    current.hits+" hits · "+current.accuracy+"% accuracy · Best streak "+current.best_combo:
    "Press Start / resume to begin",320,245);
   ctx.textAlign="start";
  }
 }
 function circle(ctx,x,y,r,color){
  ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
 }
 function star(ctx,x,y,points,outer,inner,color){
  ctx.fillStyle=color;ctx.beginPath();
  for(let i=0;i<points*2;i++){
   const a=i*Math.PI/points-Math.PI/2,r=i%2?inner:outer;
   if(i===0)ctx.moveTo(x+Math.cos(a)*r,y+Math.sin(a)*r);
   else ctx.lineTo(x+Math.cos(a)*r,y+Math.sin(a)*r);
  }
  ctx.closePath();ctx.fill();
 }
 function hud(){
  const ms=elapsed();
  return {
   time:Math.ceil((LIMIT-ms)/1000)+"s remaining",
   wave:"Wave "+clamp(Math.floor(ms/15000)+1,1,3)+" / 3",
   score:current.score+" / 100",
   ammo:current.ammo+" snowballs",
   combo:current.combo+" streak",
   accuracy:current.accuracy+"% accuracy",
   feedback:current.feedback||(current.status==="finished"?"Run complete.": "Aim for targets, not decoys."),
  };
 }
 function tick(){
  const now=performance.now();
  if(current.status==="active"&&(elapsed()>=LIMIT||now-lastRefresh>7000)){
   lastRefresh=now;
   void resync().catch(()=>{});
  }
 }
 let host=global.SnowfallArcadeV299.mountScene({
  root,title:"Snowball Target Gallery",help:
   "Shoot moving bullseyes, catch golden bonuses and avoid decoys. Three increasingly fast waves; no snowball resources used. Scores are QA practice-only.",
  getStatus:()=>current.status,getHud:hud,draw:render,
  onStart:begin,onPause:pause,onFinish:finish,
  onShot:shootAt,onExit:close,onTick:tick,
 });
 // The scene host owns canvas, focus, sizing, keyboard, sounds and animation.
 return {dispose:host.dispose,pause:host.pause,getSnapshot:()=>current};
}
global.SnowfallGalleryV299a=Object.freeze({mount,position});
})(window);
