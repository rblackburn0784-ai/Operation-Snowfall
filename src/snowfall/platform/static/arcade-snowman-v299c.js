/* v2.9.9c — full interactive Snowman Builder, on the shared Arcade 2.0 stage.
   Three server-provided blueprints, pointer/touch drag/drop, keyboard placement,
   and server-authoritative collision checks, time and practice-only scores. */
(function(global){
"use strict";
const W=640,H=360,LIMIT=150000,TRAY_X=473,TRAY_Y=70,ITEM_H=25;
const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
const labels={
 base:"Big snowball",torso:"Middle snowball",head:"Small snowball",
 hat:"Top hat",scarf:"Winter scarf",nose:"Carrot",arm_left:"Left twig",
 arm_right:"Right twig",buttons:"Coal buttons",sunhat:"Summer hat",
 beachball:"Beach ball"
};
function circle(ctx,x,y,r,color){
 ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
}
function oval(ctx,x,y,rx,ry,color){
 ctx.fillStyle=color;ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);ctx.fill();
}
const spriteSizes={base:[82,82],torso:[70,70],head:[58,58],hat:[60,46],scarf:[56,58],nose:[37,14],arm_left:[48,40],arm_right:[48,40],buttons:[12,42],sunhat:[76,36],beachball:[48,48]};
const sprites={};
function sprite(type){
 if(!sprites[type]&&typeof Image!=="undefined"){
  const img=new Image();img.src="/art/v290/arcade/v299k5/snowman-"+type+".webp";sprites[type]=img;
 }
 return sprites[type];
}
function partArt(ctx,type,x,y,{ghost=false,scale=1}={}){
 ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);
 ctx.globalAlpha=ghost ? 0.24 : 1;
 const img=sprite(type),size=spriteSizes[type];
 if(img?.complete&&img.naturalWidth&&size){
  const [w,h]=size;
  ctx.drawImage(img,-w/2,-h/2,w,h);
  ctx.restore();return;
 }
 const snow=ghost?"#f0ece2":"#f2f6f6";
 const ice=ghost?"#d9dfe1":"#c8e0e7";
 ctx.lineWidth=ghost?2.5:3;
 ctx.strokeStyle=ice;
 const ball=r=>{
  circle(ctx,0,0,r,snow);
  ctx.beginPath();ctx.arc(0,0,r,0,Math.PI*2);ctx.stroke();
  if(!ghost){circle(ctx,-r*.29,-r*.32,r*.13,"#ffffff")}
 };
 if(type==="base")ball(41);
 else if(type==="torso")ball(35);
 else if(type==="head"){
  ball(29);
  if(!ghost){
   circle(ctx,-11,-7,3.4,"#27384a");
   circle(ctx,9,-7,3.4,"#27384a");
   ctx.strokeStyle="#4b6d78";ctx.lineWidth=2;
   ctx.beginPath();ctx.arc(0,5,12,.28,Math.PI-.28);ctx.stroke();
  }
 }else if(type==="hat"){
  ctx.fillStyle=ghost?"#d9dfe1":"#253b49";
  ctx.fillRect(-20,-24,40,38);ctx.fillRect(-30,12,60,10);
  if(!ghost){ctx.fillStyle="#bb5956";ctx.fillRect(-19,3,38,8)}
 }else if(type==="scarf"){
  ctx.strokeStyle=ghost?"#e5e4d3":"#bb3c53";ctx.lineWidth=12;
  ctx.beginPath();ctx.arc(0,-2,20,Math.PI*.1,Math.PI*.95);ctx.stroke();
  ctx.beginPath();ctx.moveTo(16,4);ctx.lineTo(23,31);ctx.stroke();
 }else if(type==="nose"){
  ctx.fillStyle=ghost?"#e4cfaa":"#e79d48";
  ctx.beginPath();ctx.moveTo(-10,-5);ctx.lineTo(27,1);ctx.lineTo(-8,7);
  ctx.closePath();ctx.fill();
 }else if(type==="arm_left"||type==="arm_right"){
  const d=type==="arm_left"?-1:1;
  ctx.strokeStyle=ghost?"#b4b2ad":"#775941";ctx.lineWidth=8;
  ctx.beginPath();ctx.moveTo(-d*9,10);ctx.lineTo(d*24,-13);ctx.lineTo(d*33,-18);ctx.stroke();
  ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(d*20,-10);ctx.lineTo(d*25,-26);ctx.stroke();
 }else if(type==="buttons"){
  for(const dy of [-15,0,15])circle(ctx,0,dy,5,ghost?"#bcc6ce":"#324554");
 }else if(type==="sunhat"){
  oval(ctx,0,11,38,8,"#ead6a0");
  ctx.fillStyle="#e2bf81";ctx.fillRect(-19,-16,38,29);
  ctx.fillStyle="#b47a5c";ctx.fillRect(-19,1,38,7);
 }else if(type==="beachball"){
  circle(ctx,0,0,24,"#e9d28e");
  ctx.fillStyle="#4a90a3";ctx.fillRect(-24,-4,48,10);
  ctx.fillStyle="#c65d58";ctx.fillRect(-5,-23,11,46);
 }
 ctx.restore();
}
function trayBounds(index){return {x:TRAY_X,y:TRAY_Y+index*ITEM_H,w:157,h:23}}
function mount({root,session,start,control,place,refresh,fetchRecord,onExit,
                recoveredAction}){
 if(!global.SnowfallArcadeV299?.mountScene)
  throw Error("Arcade 2.0 game screen is not available.");
 let current=session,reference=performance.now(),lastRefresh=0,refreshing=false;
 let selected=null,dragging=false,pointerId=null,startPoint=null,hover=null;
 let cursor={x:249,y:205},guide=true,record=null,recordBusy=false;
 let busy=false,pending=recoveredAction||null,host=null;
 const art=new Image();art.src="/art/v290/arcade/snowman.webp";
 const scenery=new Image();scenery.src="/art/v290/arcade/v299k5/snowman-stage.webp";
 function elapsed(){
  return clamp(Math.round(current.elapsed_ms+(current.status==="active"?
   Math.max(0,performance.now()-reference):0)),0,LIMIT);
 }
 function apply(view){
  if(!view||view.mode!=="snowman"||!view.blueprint||
     typeof view.action_seq!=="number")
   throw Error("Unexpected Snowman Builder response.");
  const changed=view.session_id!==current.session_id||view.stage!==current.stage;
  if(view.session_id!==current.session_id){pending=null;record=null}
  current=view;reference=performance.now();
  if(changed){
   selected=null;dragging=false;hover=null;
   const first=view.blueprint.slots.find(s=>!view.placed.includes(s.id));
   if(first)cursor={x:first.x,y:first.y};
  }
  if(pending&&view.action_seq>pending.action_seq)pending=null;
  if(view.status==="finished"&&!record&&!recordBusy&&fetchRecord){
   recordBusy=true;
   void fetchRecord().then(value=>{record=value}).catch(()=>{})
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
  dragging=false;hover=null;
  if(current.status==="active")apply(await control(current.session_id,"pause"));
 }
 async function finish(){
  dragging=false;hover=null;
  if(current.status!=="finished")apply(await control(current.session_id,"finish"));
 }
 async function close(){if(current.status==="active")await pause();onExit?.()}
 async function resync(){
  if(refreshing||current.status!=="active")return;
  refreshing=true;
  const sid=current.session_id,seq=current.action_seq;
  try{
   const next=await refresh(sid);
   if(current.session_id===sid&&next.action_seq>=seq)apply(next);
  }finally{refreshing=false}
 }
 async function submit(piece,x,y){
  if(busy||current.status!=="active")return;
  if(!piece&&pending)return retry();
  if(!piece)return;
  busy=true;
  const body=pending||{
   session_id:current.session_id,action_seq:current.action_seq,
   piece_id:piece,x:Math.round(x),y:Math.round(y)
  };
  try{
   if(pending&&(pending.piece_id!==piece||pending.x!==Math.round(x)||pending.y!==Math.round(y))){
    const snap=await refresh(current.session_id);
    if(snap.action_seq>pending.action_seq){
     apply(snap);pending=null;
    }
    throw Error("Retry the interrupted placement first.");
   }
   const response=await place(body),oldStage=current.stage;
   apply(response);pending=null;
   const action=response.last_action||{};
   if(action.outcome==="placed"){
    host?.tone(true);
    selected=null;hover=null;
    host?.setFeedback(response.stage>oldStage?
     response.feedback:"Perfect! "+labels[body.piece_id]+" placed.");
   }else{
    host?.tone(false);
    host?.setFeedback(action.feedback||"Match the ghost outline.");
   }
  }catch(e){
   if([400,409,422].includes(e?.status)){
    pending=null;
    try{apply(await refresh(body.session_id))}catch{}
    host?.setFeedback(e.message||"Placement rejected; try a new position.");
    throw e;
   }
   if(!pending)pending=body;
   try{
    const snap=await refresh(body.session_id);
    if(snap.action_seq>body.action_seq){
     apply(snap);pending=null;selected=null;
     host?.setFeedback("Interrupted placement confirmed and saved.");
     return;
    }
   }catch{}
   host?.setFeedback("Placement not confirmed. Retry last placement to continue.");
   throw e;
  }finally{busy=false}
 }
 async function retry(){
  if(!pending){host?.setFeedback("No interrupted placement to retry.");return}
  return submit(pending.piece_id,pending.x,pending.y);
 }
 function trayParts(){return current.blueprint.parts.filter(
  p=>!current.placed.includes(p.id));
 }
 function itemAt(p){
  const parts=trayParts();
  for(let i=0;i<parts.length;i++){
   const box=trayBounds(i);
   if(p.x>=box.x&&p.x<=box.x+box.w&&p.y>=box.y&&p.y<=box.y+box.h)
    return parts[i];
  }
  return null;
 }
 function pointer(p){
  if(current.status!=="active"||busy)return;
  if(p.type==="pointerdown"){
   const part=itemAt(p);
   if(part){
    selected=part.id;dragging=true;pointerId=p.pointerId;
    startPoint={x:p.x,y:p.y};hover={x:p.x,y:p.y};cursor={x:p.x,y:p.y};
   }else if(selected&&p.x<459&&p.y>=59){
    dragging=true;pointerId=p.pointerId;
    startPoint={x:p.x,y:p.y};hover={x:p.x,y:p.y};
   }
  }else if(p.type==="pointermove"&&dragging&&pointerId===p.pointerId){
   hover={x:p.x,y:p.y};cursor={x:p.x,y:p.y};
  }else if((p.type==="pointerup"||p.type==="pointercancel")&&
           dragging&&pointerId===p.pointerId){
   const from=startPoint,selectedPiece=selected;
   const moved=from?Math.hypot(p.x-from.x,p.y-from.y):0;
   dragging=false;pointerId=null;hover=null;
   if(p.type==="pointerup"&&selectedPiece&&p.x<460&&p.y>=57&&p.y<=340&&
      (moved>10||from?.x<460)){
    cursor={x:p.x,y:p.y};
    void submit(selectedPiece,p.x,p.y).catch(()=>{});
   }else if(p.type==="pointerup"&&selectedPiece){
    host?.setFeedback("Part selected: "+labels[selectedPiece]+
     ". Drag or tap its matching outline.");
   }
  }
 }
 function keyboard(e){
  if(current.status!=="active")return false;
  const key=e.key,parts=trayParts(),step=e.shiftKey?24:12;
  if(key==="ArrowLeft")cursor.x=clamp(cursor.x-step,30,449);
  else if(key==="ArrowRight")cursor.x=clamp(cursor.x+step,30,449);
  else if(key==="ArrowUp")cursor.y=clamp(cursor.y-step,60,330);
  else if(key==="ArrowDown")cursor.y=clamp(cursor.y+step,60,330);
  else if(key===" "||key==="Enter"){
   if(selected)void submit(selected,cursor.x,cursor.y).catch(()=>{});
   else host?.setFeedback("Select a part first using number keys or the tray.");
  }else if(key==="Escape"){selected=null;hover=null}
  else if(/^[0-9]$/.test(key)||key==="-"){
   const index=key==="0"?9:key==="-"?10:Number(key)-1;
   if(parts[index]){selected=parts[index].id;host?.setFeedback(
    labels[selected]+" selected. Move with arrows and press Enter to place.");}
  }else if(key.toLowerCase()==="h"){guide=!guide}
  else return false;
  return true;
 }
 function draw(ctx,{time,reduced}){
  const gradient=ctx.createLinearGradient(0,0,0,H);
  gradient.addColorStop(0,"#132e43");gradient.addColorStop(1,"#477c8c");
  ctx.fillStyle=gradient;ctx.fillRect(0,0,W,H);
  const custom=scenery.complete&&scenery.naturalWidth;
  if(custom){ctx.drawImage(scenery,0,0,W,H)}
  else if(art.complete&&art.naturalWidth){
   ctx.save();ctx.globalAlpha=.18;ctx.drawImage(art,0,0,W,H);ctx.restore();
  }
  // The blueprint and the tray share the same canvas coordinates as
  // server-side collision detection.
  ctx.fillStyle=custom?"rgba(8,28,41,.22)":"rgba(8,28,41,.48)";ctx.fillRect(16,54,440,285);
  ctx.strokeStyle="#a4c9d4";ctx.lineWidth=2;ctx.strokeRect(16,54,440,285);
  ctx.fillStyle="#e8f4f6";ctx.font="bold 18px Georgia";
  ctx.fillText("SNOWMAN WORKSHOP",23,30);
  ctx.fillStyle="#f0d8a7";ctx.font="13px sans-serif";
  ctx.fillText("BLUEPRINT "+Math.min(current.stage+1,3)+
   "/3 · "+current.blueprint.name,23,48);
  if(!custom){ctx.fillStyle="#dbe9ee";ctx.fillRect(21,315,428,22);
  ctx.fillStyle="#aac8d1";ctx.fillRect(21,328,428,10);}
  const placed=new Set(current.placed);
  const slots=current.blueprint.slots;
  const order=["arm_left","arm_right","base","torso","head","buttons","nose","scarf","hat"];
  for(const type of order){
   const slot=slots.find(v=>v.id===type);
   if(!slot)continue;
   if(!placed.has(type)){
    if(guide){
     ctx.save();ctx.globalAlpha=.3;ctx.strokeStyle="#f1e1b9";
     ctx.lineWidth=2;ctx.setLineDash([4,5]);
     ctx.beginPath();ctx.arc(slot.x,slot.y,slot.radius,0,Math.PI*2);
     ctx.stroke();ctx.setLineDash([]);
     ctx.restore();
     partArt(ctx,type,slot.x,slot.y,{ghost:true,scale:.78});
    }
   }else partArt(ctx,type,slot.x,slot.y);
  }
  ctx.fillStyle="#182e3d";ctx.fillRect(469,55,165,283);
  ctx.strokeStyle="#d6ba8a";ctx.lineWidth=2;ctx.strokeRect(469,55,165,283);
  ctx.fillStyle="#f4e1b2";ctx.font="bold 13px Georgia";
  ctx.fillText("PARTS TRAY",487,47);
  const parts=trayParts();
  for(let i=0;i<parts.length;i++){
   const p=parts[i],box=trayBounds(i),chosen=selected===p.id;
   ctx.fillStyle=chosen?"#886c43":p.decoy?"#4b343d":"#2d5162";
   ctx.fillRect(box.x,box.y,box.w,box.h);
   ctx.strokeStyle=chosen?"#fbe4b0":"#6d8b91";
   ctx.lineWidth=chosen?2.5:1;ctx.strokeRect(box.x,box.y,box.w,box.h);
   partArt(ctx,p.id,box.x+16,box.y+12,{scale:.24});
   ctx.fillStyle="#ecf2ef";ctx.font="12px sans-serif";
   ctx.fillText((i+1<=9?String(i+1):i===9?"0":"-")+
    ". "+p.label,box.x+30,box.y+16);
  }
  if(selected&&current.status==="active"){
   const location=hover&&hover.x<460?hover:cursor;
   const shade=selected==="sunhat"||selected==="beachball"?"#f1c9a8":"#e2f1ff";
   ctx.save();ctx.strokeStyle=shade;ctx.setLineDash([5,5]);ctx.lineWidth=2;
   ctx.beginPath();ctx.arc(location.x,location.y,21,0,Math.PI*2);ctx.stroke();
   ctx.setLineDash([]);
   partArt(ctx,selected,location.x,location.y,{ghost:false,scale:.48});
   ctx.restore();
  }
  ctx.font="13px sans-serif";ctx.fillStyle="#f3e4be";
  ctx.fillText("Drag parts to outlines · tap to select · arrows + Enter",22,353);
  if(!reduced){
   ctx.fillStyle="rgba(236,247,255,.6)";
   for(let i=0;i<25;i++){
    const px=(i*137+time*.01*(i%3+1))%465;
    const py=(i*61+time*.009*(i%4+1))%H;
    circle(ctx,px,py,1.2,"rgba(238,249,255,.65)");
   }
  }
  if(current.status!=="active"){
   ctx.fillStyle="rgba(9,28,39,.89)";ctx.fillRect(62,93,480,208);
   ctx.strokeStyle="#e4c793";ctx.lineWidth=2;ctx.strokeRect(62,93,480,208);
   ctx.textAlign="center";ctx.font="bold 24px Georgia";
   ctx.fillStyle="#ffe7bc";
   ctx.fillText(current.status==="finished"?
    current.complete?"FROSTY MASTERPIECE!":"WORKSHOP CLOSED":
    "READY TO BUILD?",302,145);
   ctx.font="17px sans-serif";ctx.fillStyle="#e8eff0";
   ctx.fillText(current.status==="finished"?
    current.placed_total+" of 20 parts fitted · "+current.score+"/100":
    "Three festive blueprints · 150 seconds · 20 parts",302,185);
   ctx.font="15px sans-serif";
   ctx.fillText(current.status==="finished"?
    current.result:"Tap Start / resume to enter the workshop",302,221);
   if(current.status==="finished"&&record){
    ctx.font="14px sans-serif";ctx.fillStyle="#f0c98e";
    ctx.fillText("Personal best: "+record.personal_best+"/100 · "+
     record.completed_builds+" full builds",302,263);
   }
   ctx.textAlign="left";
  }
 }
 function hud(){
  return {
   time:Math.ceil((LIMIT-elapsed())/1000)+"s left",
   round:"Blueprint "+Math.min(3,current.round)+"/3",
   parts:current.placed_total+"/20 parts",
   score:current.score+"/100",
   mistakes:current.mistakes+" slips",
   selection:selected?labels[selected]:"Select a part",
   feedback:current.feedback||"Build the snowman to match its ghost outlines.",
  };
 }
 function onTick(){
  if(current.status==="active"&&(elapsed()>=LIMIT||
     performance.now()-lastRefresh>=6500)){
   lastRefresh=performance.now();
   void resync().catch(()=>{});
  }
 }
 host=global.SnowfallArcadeV299.mountScene({
  root,title:"Snowman Builder",
  canvasLabel:"Build a snowman. Select a part in the right tray, then drag or tap it into a matching ghost outline. Keyboard: number keys select parts, arrows move, Enter places, H toggles outlines.",
  guide:[
   "Touch or mouse: select a part from the right tray, then drag or tap the matching ghost outline on the blueprint.",
   "Build three snowmen with 4, 7 and 9 correctly fitted parts. Some later tray pieces are decoys.",
   "Keyboard: number keys 1–9, 0 and minus select tray parts; arrow keys move the cursor; Enter places.",
   "Press H or Show / hide outlines to practise without the guides. Later blueprints have a slightly more forgiving touch target.",
   "A correct fit scores points; wrong locations and decoys incur practice penalties. Only the server verifies placements.",
  ],
  help:"Build three increasingly detailed snowmen by dragging real parts onto their ghost outlines. Beware decoys! 150-second unranked QA game.",
  getStatus:()=>current.status,getHud:hud,draw,
  onStart:begin,onPause:pause,onFinish:finish,onExit:close,
  onTick,onPointer:pointer,onKey:keyboard,showAim:false,
  hudFields:[
   {key:"time",initial:"150s"},{key:"round",initial:"Blueprint 1/3"},
   {key:"parts",initial:"0/20 parts"},{key:"score",initial:"0/100"},
   {key:"mistakes",initial:"0 slips"},{key:"selection",initial:"Select a part"}
  ],
  extraActions:[{key:"drop",label:"Place selected part"},
   {key:"guide",label:"Show / hide outlines"},
   {key:"retry",label:"Retry last placement"}],
  onExtraAction:async action=>{
   if(action==="guide"){guide=!guide;host?.setFeedback(
    guide?"Ghost outlines enabled.":"Outlines hidden for a harder challenge.");return}
   if(action==="retry")return retry();
   if(!selected)throw Error("Select a part from the tray first.");
   return submit(selected,cursor.x,cursor.y);
  },
  welcome:"Select a piece in the tray. Drag it to its matching blueprint outline.",
 });
 return {dispose:host.dispose,pause:host.pause,getSnapshot:()=>current,
  getPending:()=>pending,parts:()=>trayParts(),cursor:()=>cursor};
}
global.SnowfallSnowmanV299c=Object.freeze({mount,trayBounds,partArt,labels});
})(window);
