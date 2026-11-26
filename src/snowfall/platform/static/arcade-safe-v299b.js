/* v2.9.9b — fully interactive Frozen Safecracker.
   Shared Arcade 2.0 renderer/input/sound host; server owns code and result. */
(function(global){
"use strict";
const W=640,H=360,LIMIT=90000,NOTCHES=40,STEP=Math.PI*2/NOTCHES;
const CX=326,CY=179,R=106;
const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
const mod=n=>(n%NOTCHES+NOTCHES)%NOTCHES;
const ORDER=["CLOCKWISE","ANTICLOCKWISE","CLOCKWISE"];
const HINTS={
 "turn":"Keep rotating in the required direction; a full turn seats the mechanism.",
 "quiet":"No resistance yet. Keep searching for the soft mechanical tick.",
 "faint":"A faint ticking sound… you're getting closer.",
 "near":"Almost there! Fine-tune the dial.",
 "click":"CLEAR CLICK! Press SET TUMBLER to lock this number.",
 "open":"The lock has released!"
};
function tickPositions(dial,ring=85){
 const positions=[];
 for(let n=0;n<NOTCHES;n++){
  const theta=(dial-n)*STEP-Math.PI/2;
  positions.push({n,x:CX+Math.cos(theta)*ring,y:CY+Math.sin(theta)*ring,theta});
 }
 return positions;
}
function mount({root,session,start,control,move,refresh,fetchRecord,onExit,
               recoveredAction}){
 if(!global.SnowfallArcadeV299?.mountScene)
  throw Error("Arcade 2.0 game screen is not available.");
 let current=session,reference=performance.now(),lastRefresh=0,refreshing=false;
 let record=null,recordBusy=false,pending=recoveredAction||null;
 let dragging=false,pointerId=null,lastAngle=null,angleSum=0;
 let dialPreview=null,operationBusy=false,host=null;
 const asset=global.SnowfallArcadeV299?.loadArt?.("/art/v290/arcade/safe.webp")||(()=>{const image=new Image();image.src="/art/v290/arcade/safe.webp";return image})();
 const load=name=>{const img=global.SnowfallArcadeV299?.loadArt?.("/art/v290/arcade/v299k3/"+name+".webp")||(()=>{const image=new Image();image.src="/art/v290/arcade/v299k3/"+name+".webp";return image})();return img};
 const stageArt=load("safe-stage"),panel=load("safe-panel"),wheel=load("safe-wheel");
 const ready=img=>img.complete&&img.naturalWidth;
 function apply(value){
  if(!value||value.mode!=="safe"||typeof value.action_seq!=="number")
   throw Error("Invalid Safecracker session.");
  if(value.session_id!==current.session_id){
   pending=null;record=null;dragging=false;dialPreview=null;
  }
  current=value;reference=performance.now();
  if(pending&&current.action_seq>pending.action_seq)pending=null;
  if(value.status==="finished"&&!record&&!recordBusy&&fetchRecord){
   recordBusy=true;
   void fetchRecord().then(data=>{record=data}).catch(()=>{})
    .finally(()=>{recordBusy=false});
  }
  host?.update();
 }
 function elapsed(){
  return clamp(Math.round(current.elapsed_ms+(current.status==="active"?
   Math.max(0,performance.now()-reference):0)),0,LIMIT);
 }
 function cue(){
  if(current.status==="finished")return current.unlocked?"VAULT OPEN!":"Time's up.";
  if(current.stage===3)return "All three tumblers unlocked.";
  if(current.signal==="click")return HINTS.click;
  return HINTS[current.signal]||"Turn the dial to locate the correct notch.";
 }
 async function resync(){
  if(refreshing||current.status!=="active")return;
  refreshing=true;
  const sessionId=current.session_id,actionSeq=current.action_seq;
  try{
   const view=await refresh(sessionId);
   if(current.session_id===sessionId&&view.action_seq>=actionSeq){
    apply(view);
   }
  }finally{refreshing=false}
 }
 async function begin(){
  if(current.status==="active")return;
  let view=current.status==="finished"?await start():current;
  if(view.status==="paused")view=await control(view.session_id,"resume");
  apply(view);
 }
 async function pause(){
  dragging=false;dialPreview=null;
  if(current.status==="active")apply(await control(current.session_id,"pause"));
 }
 async function finish(){
  dragging=false;dialPreview=null;
  if(current.status!=="finished")apply(await control(current.session_id,"finish"));
 }
 async function close(){
  if(current.status==="active")await pause();
  onExit?.();
 }
 async function action(name,ticks=0){
  if(current.status!=="active")return;
  if(operationBusy)return;
  operationBusy=true;
  const body=pending||{session_id:current.session_id,
   action_seq:current.action_seq,action:name,ticks};
  try{
   if(pending&&(body.action!==name||body.ticks!==ticks)){
    // Reconcile uncertain progress before accepting a different gesture.
    const recent=await refresh(current.session_id);
    if(recent.action_seq>pending.action_seq){
     apply(recent);pending=null;
     throw Error("Previous action confirmed. Repeat your new gesture.");
    }
    throw Error("Interrupted action pending. Use Retry last action.");
   }
   const before=current.stage,signal=current.signal;
   const view=await move(body);
   apply(view);
   pending=null;
   if(current.stage>before||current.signal==="click"&&signal!=="click")
    host?.tone(true);
   host?.setFeedback(current.stage>before?current.feedback:cue());
  }catch(e){
   if([400,409,422].includes(e?.status)){
    // A definite server rejection is NOT an uncertain write. Let players
    // retry a corrected gesture with a new sequence-safe request.
    pending=null;
    try{apply(await refresh(body.session_id))}catch{}
    host?.setFeedback(e.message||"The dial rejected that turn.");
    throw e;
   }
   if(!pending)pending=body;
   // Recovery never invents a move, score, or new idempotency key.
   try{
    const result=await refresh(body.session_id);
    if(result.action_seq>body.action_seq){
     apply(result);pending=null;
     host?.setFeedback("Previously interrupted action confirmed. "+cue());
     return;
    }
   }catch{}
   host?.setFeedback("Action not confirmed. Retry the same action before continuing.");
   throw e;
  }finally{operationBusy=false;dialPreview=null}
 }
 async function retry(){
  if(!pending){
   host?.setFeedback("No interrupted action needs retrying.");
   return;
  }
  const body=pending;
  // Explicit retry is allowed without changing the original action ID/body.
  operationBusy=false;
  return action(body.action,body.ticks);
 }
 function draw(ctx,{time,reduced}){
  let sky=ctx.createLinearGradient(0,0,0,H);
  sky.addColorStop(0,"#0f273b");sky.addColorStop(1,"#315067");
  ctx.fillStyle=sky;ctx.fillRect(0,0,W,H);
  const custom=ready(stageArt)&&ready(panel)&&ready(wheel);
  if(custom){ctx.drawImage(stageArt,0,0,W,H)}else if(asset.complete&&asset.naturalWidth){
   ctx.save();ctx.globalAlpha=.22;ctx.drawImage(asset,0,0,W,H);ctx.restore();
  }
  if(!custom){
  ctx.strokeStyle="#8f734b";ctx.lineWidth=6;
  ctx.fillStyle="#253a46";ctx.fillRect(132,58,390,285);
  ctx.strokeRect(132,58,390,285);
  ctx.fillStyle="#172d3c";ctx.fillRect(142,68,371,265);
  const pins=[[157,83],[496,83],[157,312],[496,312]];
  for(const [x,y] of pins){
   ctx.fillStyle="#b6986d";ctx.beginPath();ctx.arc(x,y,6,0,Math.PI*2);ctx.fill();
  }
  }
  ctx.fillStyle="#dfc48e";ctx.font="bold 19px Georgia";
  ctx.textAlign="center";ctx.fillText("FROZEN SAFECRACKER",320,34);
  ctx.font="12px sans-serif";ctx.fillStyle="#d0e1e7";
  ctx.fillText("ROTATE THE LOCK • LISTEN FOR THE CLICK • SET EACH TUMBLER",320,53);
  const dial=dialPreview===null?current.dial:dialPreview;
  if(custom){
   ctx.drawImage(panel,95,75,110,220);
   ctx.save();ctx.translate(CX,CY);ctx.rotate(dial*STEP);ctx.drawImage(wheel,-R,-R,2*R,2*R);ctx.restore();
   ctx.fillStyle="#fff2c9";ctx.font="bold 20px Georgia";ctx.fillText(String(mod(dial)).padStart(2,"0"),CX,CY+7);
  }else{
  ctx.save();
  ctx.shadowColor="#000";ctx.shadowBlur=12;
  fillCircle(ctx,CX,CY,R+12,"#b18c53");
  fillCircle(ctx,CX,CY,R+6,"#6d583d");
  fillCircle(ctx,CX,CY,R,"#111f30");
  ctx.restore();
  fillCircle(ctx,CX,CY,88,"#263d50");
  for(const p of tickPositions(dial,91)){
   const major=p.n%5===0;
   const x2=CX+Math.cos(p.theta)*(major?104:100);
   const y2=CY+Math.sin(p.theta)*(major?104:100);
   ctx.strokeStyle=major?"#f2dda8":"#99adba";
   ctx.lineWidth=major?2.5:1;
   ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(x2,y2);ctx.stroke();
   if(major){
    const x3=CX+Math.cos(p.theta)*72,y3=CY+Math.sin(p.theta)*72;
    ctx.fillStyle="#f1e1c2";ctx.font="bold 12px sans-serif";
    ctx.fillText(String(p.n).padStart(2,"0"),x3,y3+4);
   }
  }
  // Number 0..39 under a fixed pointer, a tactile rotary dial.
  fillCircle(ctx,CX,CY,55,"#b89a67");
  fillCircle(ctx,CX,CY,48,"#273d4b");
  ctx.fillStyle="#fff2c9";ctx.font="bold 30px Georgia";
  ctx.fillText(String(mod(dial)).padStart(2,"0"),CX,CY+10);
  }
  ctx.fillStyle="#182d3d";ctx.beginPath();
  ctx.moveTo(CX,CY-106);ctx.lineTo(CX-13,CY-133);
  ctx.lineTo(CX+13,CY-133);ctx.closePath();ctx.fill();
  ctx.strokeStyle="#e8d0a5";ctx.lineWidth=2;ctx.stroke();
  // External stage lights display which tumbler has clicked into place.
  const stage=current.stage;
  for(let i=0;i<3;i++){
   const x=custom?150:460,y=custom?133+i*42:140+i*48;
   fillCircle(ctx,x,y,17,i<stage?"#e3cb8b":i===stage?"#7ab2c4":"#364d57");
   fillCircle(ctx,x,y,11,i<stage?"#467d66":i===stage?"#335d70":"#263944");
   ctx.fillStyle="#f7edcf";ctx.font="bold 15px sans-serif";
   ctx.fillText(i<stage?"✓":String(i+1),x,y+5);
  }
  ctx.fillStyle="#f2deb9";ctx.font="bold 14px Georgia";
  if(!custom)ctx.fillText("TUMBLERS",463,107);
  ctx.textAlign="left";
  ctx.font="bold 14px sans-serif";
  ctx.fillStyle="#e9dcba";
  ctx.fillText(stage>=3?"OPEN!":ORDER[stage],165,292);
  ctx.font="12px sans-serif";ctx.fillStyle="#cadfe5";
  ctx.fillText(stage>=3?"The lock is released":("Complete "+Math.max(0,current.turn_required-current.travel)+" more ticks"),165,312);
  ctx.textAlign="center";
  const signal=current.signal;
  const light=signal==="click"?"#f7d77d":signal==="near"?"#a9e4de":
   signal==="faint"?"#9dbdcb":"#637a85";
  fillCircle(ctx,custom?150:463,custom?270:286,8,light);
  ctx.fillStyle="#e3ebef";ctx.font="bold 12px sans-serif";
  ctx.fillText(signal==="click"?"CLICK!":"SIGNAL",463,314);
  if(current.status!=="active"){
   ctx.fillStyle="rgba(8,22,32,.87)";ctx.fillRect(133,72,390,266);
   ctx.strokeStyle="#e2c18b";ctx.lineWidth=2;ctx.strokeRect(133,72,390,266);
   ctx.fillStyle="#ffe5b6";ctx.font="bold 25px Georgia";
   ctx.fillText(current.status==="finished"?
    current.unlocked?"THE VAULT IS OPEN":"THE SAFE REMAINS LOCKED":
    "READY TO CRACK THE SAFE",328,142);
   ctx.font="16px sans-serif";ctx.fillStyle="#e4ebef";
   ctx.fillText(current.status==="finished"?
    current.unlocked?"Code: "+current.combination.join(" • "):
    "Combination revealed after the round":
    "Clockwise → Anticlockwise → Clockwise",328,187);
   ctx.fillText(current.status==="finished"?
    current.unlocked?"Practice score "+current.score+"/100":
    "Try again to break the ice":
    "Turn 40 notches in each direction, then set each tumbler",328,220);
   if(current.status==="finished"&&record){
    ctx.font="14px sans-serif";ctx.fillStyle="#f2d398";
    ctx.fillText("Personal best "+record.personal_best+"/100 · "+
     record.vaults_opened+" safes cracked",328,254);
   }
  }
 }
 function fillCircle(ctx,x,y,r,color){
  ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
 }
 function hud(){
  return {
   time:Math.ceil((LIMIT-elapsed())/1000)+"s remaining",
   stage:"Tumbler "+Math.min(3,current.stage+1)+" / 3",
   dial:"Dial "+String(mod(dialPreview===null?current.dial:dialPreview)).padStart(2,"0"),
   signal:current.signal==="click"?"CLEAR CLICK":current.signal.toUpperCase(),
   mistakes:current.mistakes+" slips · "+current.attempts+" tries",
   score:current.score+"/100 · "+(current.unlocked?"OPEN":"QA practice"),
   feedback:cue(),
  };
 }
 function dialAngle(p){return Math.atan2(p.y-CY,p.x-CX)}
 function pointer(p){
  if(p.type==="pointerdown"){
   if(current.status!=="active"||operationBusy)return;
   const distance=Math.hypot(p.x-CX,p.y-CY);
   if(distance<65||distance>142)return;
   dragging=true;pointerId=p.pointerId;lastAngle=dialAngle(p);
   angleSum=0;dialPreview=current.dial;host?.update();
  }else if(p.type==="pointermove"&&dragging&&pointerId===p.pointerId){
   const distance=Math.hypot(p.x-CX,p.y-CY);
   if(distance<42||distance>183){lastAngle=dialAngle(p);return}
   const theta=dialAngle(p);
   let delta=theta-lastAngle;
   if(delta>Math.PI)delta-=Math.PI*2;
   if(delta< -Math.PI)delta+=Math.PI*2;
   if(Math.abs(delta)<2.6)angleSum+=delta;
   lastAngle=theta;
   dialPreview=mod(current.dial+Math.round(angleSum/STEP));
  }else if((p.type==="pointerup"||p.type==="pointercancel")
           &&dragging&&pointerId===p.pointerId){
   dragging=false;pointerId=null;
   const ticks=Math.round(angleSum/STEP);
   dialPreview=null;
   if(p.type==="pointerup"&&ticks!==0){
    // A multi-revolution gesture may exceed a single server action.
    // Avoid sending unverifiable huge rotations: limit to 80 notches.
    if(Math.abs(ticks)>80){
     host?.setFeedback("Rotate at most two full turns per gesture.");
     return;
    }
    void action("turn",ticks).catch(()=>{});
   }
  }
 }
 function key({key,shiftKey}){
  if(key==="ArrowRight"||key==="ArrowLeft"){
   if(current.status==="active"&&!operationBusy)
    void action("turn",(key==="ArrowRight"?1:-1)*(shiftKey?4:1)).catch(()=>{});
   return true;
  }
  if(key===" "||key==="Enter"){
   if(current.status==="active"&&!operationBusy)
    void action("set",0).catch(()=>{});
   return true;
  }
  return false;
 }
 function tick(){
  if(current.status==="active"&&(performance.now()-lastRefresh>5500||
      elapsed()>=LIMIT)){
   lastRefresh=performance.now();
   void resync().catch(()=>{});
  }
 }
 host=global.SnowfallArcadeV299.mountScene({
  root,title:"Frozen Safecracker",
  canvasLabel:"Frozen Safecracker dial. Drag around the outside ring, or use Left and Right arrows to rotate. Shift plus arrows turns four notches. Press Enter to set a tumbler.",
  guide:[
   "Turn the dial clockwise for tumbler one, anticlockwise for two, then clockwise for three.",
   "Mouse or touch: drag along the outside ring to spin the dial. Each tumbler requires at least one complete turn in its direction.",
   "Keyboard: Left/Right arrows turn one notch (Shift for four). Press Enter or Space to set the tumbler when aligned.",
   "Signals progress from quiet to faint, near and CLICK. The practice hint window is slightly wider, but only the exact CLICK sets a tumbler.",
   "Wrong-direction turns and failed sets cost practice points. Use Retry after an interrupted move; your original turn is preserved.",
  ],
  help:"Rotate the dial clockwise, reverse anticlockwise, then clockwise again. Hear/see subtle resistance near each hidden number; press Set Tumbler on the clear click. Unlimited, unranked QA practice.",
  getStatus:()=>current.status,getHud:hud,draw,onStart:begin,
  onPause:pause,onFinish:finish,onExit:close,onTick:tick,
  onPointer:pointer,onKey:key,showAim:false,
  hudFields:[{key:"time",initial:"90s"},{key:"stage",initial:"Tumbler 1/3"},
   {key:"dial",initial:"Dial 00"},{key:"signal",initial:"TURN"},
   {key:"mistakes",initial:"0 slips"},{key:"score",initial:"0/100"}],
  extraActions:[{key:"cw",label:"↻ Clockwise +4"},
   {key:"ccw",label:"↺ Anticlockwise −4"},
   {key:"set",label:"SET TUMBLER"},
   {key:"retry",label:"Retry last action"}],
  onExtraAction:async name=>{
   if(name==="set")return action("set",0);
   if(name==="cw")return action("turn",4);
   if(name==="ccw")return action("turn",-4);
   return retry();
  },
  welcome:"Click Start, then drag the outer dial clockwise. Listen for the lock.",
 });
 return {dispose:host.dispose,pause:host.pause,getSnapshot:()=>current,
         getPending:()=>pending,dialAngle,tickPositions};
}
global.SnowfallSafecrackerV299b=Object.freeze({mount,tickPositions,mod,HINTS});
})(window);
