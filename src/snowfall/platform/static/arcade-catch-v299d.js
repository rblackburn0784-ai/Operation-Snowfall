/* v2.9.9d — real Snowflake Catch mini-game, shared Arcade 2.0 canvas.
   Smooth pointer/touch/keyboard basket with server-audited crossing events,
   shifting wind, hazards, golden/crystal bonuses and unranked practice scores. */
(function(global){
"use strict";
const W=640,H=360,LIMIT=60000,MIN=66,MAX=574,BASKET_Y=306;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function position(item,ms){
 const p=clamp((ms-item.start)/item.flight,0,1);
 return {
  x:item.x0+item.wind*p+
    item.sway*(Math.sin(item.phase+p*Math.PI*2)-Math.sin(item.phase)),
  y:38+(300-38)*p,
 };
}
function wave(ms){return clamp(Math.floor(ms/20000)+1,1,3)}
function mount({root,session,start,control,update,refresh,fetchRecord,onExit,
                recoveredAction}){
 if(!global.SnowfallArcadeV299?.mountScene)
  throw Error("Arcade 2.0 game scene is unavailable.");
 let current=session,reference=performance.now(),lastRefresh=0;
 let targetX=Number(session.basket_x)||320,visualX=targetX,lastFrame=0;
 let updating=false,refreshing=false,pending=recoveredAction||null;
 let lastSend=0,dragging=false,pointerId=null,record=null,recordBusy=false,host=null;
 let lastFeedbackSeq=current.action_seq||0,latestFeedback=null;
 const backdrop=new Image();backdrop.src="/art/v290/arcade/catch.webp";
 function elapsed(){
  return clamp(Math.round((Number(current.elapsed_ms)||0)+
   (current.status==="active"?Math.max(0,performance.now()-reference):0)),
   0,LIMIT);
 }
 function apply(view){
  if(!view||view.mode!=="catch"||!Array.isArray(view.schedule)||
     typeof view.action_seq!=="number")throw Error("Unexpected catch game response.");
  const newGame=view.session_id!==current.session_id;
  current=view;reference=performance.now();
  if(newGame){
   pending=null;record=null;
   targetX=view.basket_x;visualX=view.basket_x;
   lastFeedbackSeq=0;latestFeedback=null;
  }
  if(pending&&view.action_seq>pending.action_seq)pending=null;
  if(view.events?.length){
   latestFeedback=view.events.at(-1).feedback;
   if(view.action_seq>=lastFeedbackSeq){
    const hit=view.events.some(e=>e.outcome==="caught");
    host?.tone(hit);
   }
   lastFeedbackSeq=view.action_seq;
   host?.setFeedback(latestFeedback);
  }
  if(view.status==="finished"&&!record&&!recordBusy&&fetchRecord){
   recordBusy=true;
   void fetchRecord().then(v=>{record=v}).catch(()=>{})
    .finally(()=>{recordBusy=false});
  }
  host?.update();
 }
 async function begin(){
  if(current.status==="active")return;
  let view=current.status==="finished"?await start():current;
  if(view.status==="paused")view=await control(view.session_id,"resume");
  apply(view);
 }
 async function pause(){
  if(current.status==="active"){
   if(updating)await new Promise(r=>setTimeout(r,180));
   apply(await control(current.session_id,"pause"));
  }
  dragging=false;
 }
 async function finish(){
  if(current.status!=="finished")apply(await control(current.session_id,"finish"));
  dragging=false;
 }
 async function close(){if(current.status==="active")await pause();onExit?.()}
 async function sync(){
  if(refreshing||current.status!=="active")return;
  refreshing=true;
  const id=current.session_id,seq=current.action_seq;
  try{
   const view=await refresh(id);
   if(id===current.session_id&&view.action_seq>=seq)apply(view);
  }finally{refreshing=false}
 }
 async function transmit(){
  if(current.status!=="active"||updating)return;
  updating=true;
  const body=pending||{
   session_id:current.session_id,action_seq:current.action_seq,
   x:clamp(Math.round(visualX),MIN,MAX),
  };
  try{
   const result=await update(body);
   apply(result);pending=null;
  }catch(e){
   if([400,409,422].includes(e?.status)){
    pending=null;
    try{
     const view=await refresh(body.session_id);
     apply(view);visualX=view.basket_x;
     // A rejected high-speed motion cannot be sent repeatedly.
     targetX=visualX;
    }catch{}
    host?.setFeedback(e.message||"Basket position rejected; aim more slowly.");
   }else{
    if(!pending)pending=body;
    try{
     const view=await refresh(body.session_id);
     if(view.action_seq>body.action_seq){
      apply(view);pending=null;
      host?.setFeedback("Last basket update was safely recovered.");
      return;
     }
    }catch{}
    host?.setFeedback("Connection interrupted. Retrying the same basket update.");
   }
  }finally{updating=false}
 }
 function basketPointer(p){
  if(current.status!=="active")return;
  if(p.type==="pointerdown"){
   pointerId=p.pointerId;dragging=true;
   targetX=clamp(p.x,MIN,MAX);
  }else if(p.type==="pointermove"&&dragging&&pointerId===p.pointerId){
   targetX=clamp(p.x,MIN,MAX);
  }else if((p.type==="pointerup"||p.type==="pointercancel")&&
           pointerId===p.pointerId){
   if(p.type==="pointerup")targetX=clamp(p.x,MIN,MAX);
   dragging=false;pointerId=null;
  }
 }
 function key({key,shiftKey}){
  if(current.status!=="active")return false;
  const step=shiftKey?65:30;
  if(key==="ArrowLeft"||key==="a"||key==="A")targetX=clamp(targetX-step,MIN,MAX);
  else if(key==="ArrowRight"||key==="d"||key==="D")
   targetX=clamp(targetX+step,MIN,MAX);
  else if(key==="Home")targetX=MIN;
  else if(key==="End")targetX=MAX;
  else return false;
  return true;
 }
 function oval(ctx,x,y,rx,ry,fill){
  ctx.fillStyle=fill;ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);ctx.fill();
 }
 function snowflake(ctx,x,y,size,golden=false){
  ctx.strokeStyle=golden?"#ffdd82":"#e9f8ff";
  ctx.lineWidth=Math.max(1.8,size/5);
  ctx.lineCap="round";
  for(let i=0;i<6;i++){
   const a=i*Math.PI/3;
   ctx.beginPath();ctx.moveTo(x,y);
   ctx.lineTo(x+Math.cos(a)*size,y+Math.sin(a)*size);ctx.stroke();
   const fork=size*.67,fx=x+Math.cos(a)*fork,fy=y+Math.sin(a)*fork;
   for(const side of [-1,1]){
    ctx.beginPath();ctx.moveTo(fx,fy);
    ctx.lineTo(fx-Math.cos(a+side*.62)*size*.28,
     fy-Math.sin(a+side*.62)*size*.28);ctx.stroke();
   }
  }
  ctx.beginPath();ctx.arc(x,y,2.5,0,Math.PI*2);
  ctx.fillStyle=golden?"#fff1b4":"#e8f7fa";ctx.fill();
 }
 function crystal(ctx,x,y){
  ctx.fillStyle="#80edec";
  ctx.strokeStyle="#dcffff";ctx.lineWidth=2.1;
  ctx.beginPath();ctx.moveTo(x,y-19);ctx.lineTo(x+14,y-6);
  ctx.lineTo(x+9,y+17);ctx.lineTo(x-9,y+17);ctx.lineTo(x-14,y-6);
  ctx.closePath();ctx.fill();ctx.stroke();
  ctx.strokeStyle="#b3faff";ctx.beginPath();ctx.moveTo(x,y-18);
  ctx.lineTo(x,y+15);ctx.lineTo(x+13,y-6);ctx.stroke();
 }
 function hazard(ctx,x,y){
  ctx.save();
  ctx.translate(x,y);ctx.rotate(Math.sin(performance.now()/380)*.18);
  ctx.fillStyle="#59778c";ctx.strokeStyle="#dfdbdf";ctx.lineWidth=2.5;
  ctx.beginPath();ctx.moveTo(0,-22);ctx.lineTo(17,12);
  ctx.lineTo(0,21);ctx.lineTo(-16,8);ctx.closePath();ctx.fill();ctx.stroke();
  ctx.strokeStyle="#ee8591";ctx.lineWidth=3;
  ctx.beginPath();ctx.moveTo(-6,-5);ctx.lineTo(6,6);
  ctx.moveTo(6,-5);ctx.lineTo(-6,6);ctx.stroke();
  ctx.restore();
 }
 function draw(ctx,{time,reduced}){
  let delta=lastFrame?Math.min(100,Math.max(0,time-lastFrame)):16;
  lastFrame=time;
  // Browser basket is smoothed to <server speed even when touch teleports.
  const maxStep=delta*.78;
  visualX=clamp(visualX+clamp(targetX-visualX,-maxStep,maxStep),MIN,MAX);
  if(current.status==="active"&&!updating){
   const interval=time-lastSend;
   if(interval>=(Math.abs(visualX-current.basket_x)>2?260:650)){
    lastSend=time;
    void transmit();
   }
  }
  const ms=elapsed(),stage=wave(ms);
  const background=ctx.createLinearGradient(0,0,0,H);
  background.addColorStop(0,"#0c2941");background.addColorStop(1,"#49768f");
  ctx.fillStyle=background;ctx.fillRect(0,0,W,H);
  if(backdrop.complete&&backdrop.naturalWidth){
   ctx.save();ctx.globalAlpha=.23;
   ctx.drawImage(backdrop,0,0,W,H);ctx.restore();
  }
  // The arena is independent of the HUD and scales with the shared stage.
  ctx.fillStyle="#e6eff6";ctx.fillRect(0,326,W,34);
  ctx.fillStyle="#b6d5e8";ctx.fillRect(0,337,W,13);
  ctx.fillStyle="#dfc48e";ctx.font="bold 20px Georgia";
  ctx.textAlign="center";ctx.fillText("SNOWFLAKE CATCH",320,30);
  ctx.fillStyle="#dae9ed";ctx.font="13px sans-serif";
  ctx.fillText("WAVE "+stage+"/3  •  "+
   ["Light snowfall","Gusty flurries","Blizzard finale"][stage-1],320,53);
  // Wave-specific wind cue, aligned with server-issued item drift.
  const upcoming=current.schedule.find(f=>f.start>=ms&&f.start<ms+3000);
  const wind=upcoming?.wind||current.schedule.find(f=>f.start<=ms&&
   f.impact>ms)?.wind||0;
  ctx.fillStyle="#eff4e1";ctx.font="bold 15px sans-serif";
  ctx.textAlign="right";ctx.fillText("WIND "+(wind<0?"←":"→")+
   (Math.abs(wind)>70?" STRONG":" LIGHT"),628,76);
  ctx.textAlign="left";
  if(!reduced){
   for(let i=0;i<25;i++){
    ctx.fillStyle="rgba(221,244,249,.54)";
    const fx=(i*131+time*.007*(i%4+1))%W;
    const fy=(i*61+time*.014*(i%5+1))%300+15;
    ctx.beginPath();ctx.arc(fx,fy,1.4,0,Math.PI*2);ctx.fill();
   }
  }
  const resolved=new Set(current.settled);
  for(const item of current.schedule){
   if(resolved.has(item.id)||ms<item.start||ms>item.impact+120)continue;
   const p=position(item,ms);
   ctx.save();
   ctx.shadowColor=item.kind==="gold"?"#ffcf68":"#c9ebfa";
   ctx.shadowBlur=item.kind==="gold"?16:5;
   if(item.kind==="hazard")hazard(ctx,p.x,p.y);
   else if(item.kind==="crystal")crystal(ctx,p.x,p.y);
   else snowflake(ctx,p.x,p.y,item.kind==="gold"?18:14,item.kind==="gold");
   ctx.restore();
  }
  // Catch basket: rounded snow basket, centered at authoritative-smoothed x.
  ctx.save();
  ctx.shadowColor="#000";ctx.shadowBlur=10;
  oval(ctx,visualX,BASKET_Y+8,54,12,"#192f43");
  ctx.fillStyle="#936f46";ctx.beginPath();
  ctx.moveTo(visualX-52,BASKET_Y+3);ctx.lineTo(visualX-37,BASKET_Y+29);
  ctx.quadraticCurveTo(visualX,BASKET_Y+38,visualX+37,BASKET_Y+29);
  ctx.lineTo(visualX+52,BASKET_Y+3);ctx.closePath();ctx.fill();
  ctx.fillStyle="#d4a96a";ctx.fillRect(visualX-55,BASKET_Y-3,110,12);
  ctx.strokeStyle="#f2d39f";ctx.lineWidth=3;
  for(let offset=-30;offset<=30;offset+=15){
   ctx.beginPath();ctx.moveTo(visualX+offset,BASKET_Y+10);
   ctx.lineTo(visualX+offset*.8,BASKET_Y+31);ctx.stroke();
  }
  ctx.restore();
  ctx.font="13px sans-serif";ctx.fillStyle="#cfe4ed";
  ctx.fillText("✦ White +3     ✦ Gold +10     ♦ Crystal +6     ◇ Ice shard −12",30,353);
  if(current.status!=="active"){
   ctx.fillStyle="rgba(11,29,43,.89)";ctx.fillRect(75,91,490,210);
   ctx.strokeStyle="#d5b989";ctx.lineWidth=2;ctx.strokeRect(75,91,490,210);
   ctx.textAlign="center";
   ctx.fillStyle="#f5e1b3";ctx.font="bold 28px Georgia";
   ctx.fillText(current.status==="finished"?
    "STORM FINISHED!":"CATCH THE SNOWFLAKES!",320,149);
   ctx.font="17px sans-serif";ctx.fillStyle="#e4f1f2";
   ctx.fillText(current.status==="finished"?
    current.result+" · "+current.score+"/100":
    "60 seconds · 3 waves · bonuses and icy hazards",320,196);
   ctx.font="15px sans-serif";
   ctx.fillText(current.status==="finished"?
    current.caught+" caught · "+current.hazards+" hazards · Best streak "+current.best_combo:
    "Move the basket with touch, mouse or arrow keys",320,232);
   if(current.status==="finished"&&record){
    ctx.font="14px sans-serif";ctx.fillStyle="#ebd19a";
    ctx.fillText("Personal best: "+record.personal_best+
     "/100 · "+record.finished_runs+" completed",320,271);
   }
   ctx.textAlign="left";
  }
 }
 function hud(){
  const ms=elapsed();
  return {
   time:Math.ceil((LIMIT-ms)/1000)+"s remaining",
   wave:"Wave "+wave(ms)+"/3",
   score:current.score+"/100 practice",
   caught:current.caught+" caught",
   hazards:current.hazards+" icy hits",
   combo:current.combo+" streak",
   feedback:latestFeedback||current.feedback||"Catch snowflakes, avoid icy shards!",
  };
 }
 function tick(){
  if(current.status==="active"&&(elapsed()>=LIMIT||
     performance.now()-lastRefresh>=6000)){
   lastRefresh=performance.now();
   void sync().catch(()=>{});
  }
 }
 host=global.SnowfallArcadeV299.mountScene({
  root,title:"Snowflake Catch",
  help:"Steer the basket to catch falling snowflakes, blue crystals and golden bonuses. Avoid jagged ice! Wind changes across three waves. Unlimited QA practice only.",
  getStatus:()=>current.status,getHud:hud,draw,
  onStart:begin,onPause:pause,onFinish:finish,onExit:close,onTick:tick,
  onPointer:basketPointer,onKey:key,showAim:false,
  hudFields:[{key:"time",initial:"60s"},{key:"wave",initial:"Wave 1/3"},
   {key:"score",initial:"0/100"},{key:"caught",initial:"0 caught"},
   {key:"hazards",initial:"0 icy hits"},{key:"combo",initial:"0 streak"}],
  extraActions:[{key:"left",label:"◀ Move left"},
   {key:"right",label:"Move right ▶"},
   {key:"center",label:"Center basket"},
   {key:"retry",label:"Retry basket update"}],
  onExtraAction:async name=>{
   if(name==="retry"){if(pending)await transmit();else host?.setFeedback(
    "No interrupted basket update.");return}
   targetX=name==="center"?320:clamp(
    targetX+(name==="left"?-75:75),MIN,MAX);
  },
  welcome:"Use mouse, touch, left/right arrows or the on-screen basket controls.",
 });
 return {dispose:host.dispose,pause:host.pause,getSnapshot:()=>current,
  getPending:()=>pending,getBasket:()=>visualX,setTarget:x=>{
   targetX=clamp(x,MIN,MAX)},
  send:transmit};
}
global.SnowfallCatchV299d=Object.freeze({mount,position,wave});
})(window);
