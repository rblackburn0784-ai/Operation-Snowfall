/* v2.9.9 — reusable web-only practice stage for all five upcoming mini-games.
   The shared render/input/timer/audio/save loop is intentionally independent
   of the existing Discord arcade. Interactive scores are TRAINING ONLY. */
(function(global){
"use strict";
const MODES={
 gallery:{name:"Target Gallery",help:"Tap the moving target. Practice your timing before the full gallery arrives."},
 safe:{name:"Frozen Safecracker",help:"Turn the dial clockwise, anticlockwise, then clockwise. This is a dial-control drill, not the final combination puzzle."},
 snowman:{name:"Snowman Builder",help:"Drag the floating accessory onto the snowman, or tap it then tap the snowman."},
 catch:{name:"Snowflake Catch",help:"Move the basket underneath the falling snowflakes. Avoid missing them."},
 trivia:{name:"Christmas Trivia",help:"Tap the correct answer card. Keyboard: keys 1, 2 or 3."}
};
const W=640,H=360;
const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
const reduced=()=>!!global.matchMedia&&global.matchMedia("(prefers-reduced-motion: reduce)").matches;
function mount({root,session,save,onExit}){
 if(!root||!session||!MODES[session.mode]||typeof save!=="function")throw Error("Invalid arcade practice stage");
 const mode=session.mode,config=MODES[mode],limit=session.duration_ms;
 let progress={...session.state},revision=session.revision,running=false,disposed=false,finished=session.status==="finished";
 let raf=0,last=0,lastSave=0,dirty=false,saving=false,pointer=false,sound=false,audio=null;
 let target={x:200,y:160,r:32},basketX=320,flakeX=280,flakeY=0;
 let selected=false,arcAngle=Number(progress.angle)||0,arcDir=0,lastDial=null;
 let localChanged=0,feedback="Practice mode · results are not ranked.",pendingSave=null;
 root.classList.remove("hidden");
 root.innerHTML="<div class='arcade-training-head'><div><p class='eyebrow'>WINTER ARCADE 2.0 · PRACTICE PREVIEW</p><h3>"+config.name+"</h3><p>"+config.help+"</p></div><button type='button' class='button button-outline' data-training='exit'>Save & close</button></div>"+
 "<div class='arcade-training-status'><span data-training-label='time' aria-live='off'>Time</span><span data-training-label='score'>Training points</span><span data-training-label='hits'>Hits</span></div>"+
 "<canvas class='arcade-training-canvas' width='640' height='360' tabindex='0' role='application' aria-label='"+config.name+" interactive practice stage; use pointer, touch or arrow keys and Space'></canvas>"+
 "<p class='arcade-training-feedback' role='status' aria-live='polite'></p><div class='arcade-training-controls'>"+
 "<button type='button' class='button button-gold' data-training='play'>Start / resume</button>"+
 "<button type='button' class='button button-outline' data-training='pause'>Pause & save</button>"+
 "<button type='button' class='button button-outline' data-training='sound' aria-pressed='false'>Sound off</button>"+
 "<button type='button' class='button button-outline' data-training='finish'>Finish drill</button></div>";
 const canvas=root.querySelector("canvas"),ctx=canvas.getContext("2d"),status=root.querySelector(".arcade-training-feedback");
 const play=root.querySelector("[data-training='play']"),pause=root.querySelector("[data-training='pause']");
 const label=key=>root.querySelector('[data-training-label="'+key+'"]');
 function tone(ok=true){
  if(!sound)return;
  try{
   const C=global.AudioContext||global.webkitAudioContext;
   if(!C)return;
   if(!audio)audio=new C();
   const osc=audio.createOscillator(),gain=audio.createGain(),at=audio.currentTime;
   osc.type="sine";osc.frequency.setValueAtTime(ok?690:220,at);
   gain.gain.setValueAtTime(.035,at);gain.gain.exponentialRampToValueAtTime(.001,at+.1);
   osc.connect(gain);gain.connect(audio.destination);osc.start(at);osc.stop(at+.11);
  }catch{} // muted/sandbox browsers still work
 }
 function score(){return clamp(progress.hits*10-progress.misses*2,0,100)}
 function report(message){
  feedback=message;status.textContent=message;
  label("time").textContent="Time "+Math.ceil((limit-progress.elapsed_ms)/1000)+"s";
  label("score").textContent="Practice "+score()+" / 100";
  label("hits").textContent="Success "+progress.hits+" · Misses "+progress.misses;
  play.disabled=progress.elapsed_ms>=limit||finished;
  pause.disabled=!running;
 }
 function mark(ok,message){
  if(progress.hits+progress.misses>=300)return;
  if(localChanged && progress.elapsed_ms-localChanged<160)return;
  localChanged=progress.elapsed_ms||1;
  if(ok)progress.hits+=1;else progress.misses+=1;
  dirty=true;tone(ok);report(message);
 }
 function coords(event){
  const rect=canvas.getBoundingClientRect();
  return {x:clamp((event.clientX-rect.left)*W/rect.width,0,W),
          y:clamp((event.clientY-rect.top)*H/rect.height,0,H)};
 }
 function background(){
  const g=ctx.createLinearGradient(0,0,0,H);
  g.addColorStop(0,"#122e45");g.addColorStop(1,"#23485b");
  ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
  ctx.fillStyle="#5d8292";ctx.fillRect(0,H-34,W,34);
  ctx.fillStyle="rgba(255,255,255,.1)";
  for(let i=0;i<22;i++){const x=(i*107+47)%W,y=(i*79+31)%300;ctx.beginPath();ctx.arc(x,y,2,0,Math.PI*2);ctx.fill()}
  ctx.fillStyle="#f1d6a0";ctx.font="bold 19px Georgia";ctx.fillText(config.name,22,33);
  ctx.fillStyle="#bfd4dc";ctx.font="14px sans-serif";ctx.fillText("UNRANKED PRACTICE · "+Math.ceil((limit-progress.elapsed_ms)/1000)+"s",22,55);
 }
 function disk(x,y,r,color){
  ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
 }
 function frame(){
  background();
  const seconds=progress.elapsed_ms/1000;
  if(mode==="gallery"){
   const drift=reduced()?0:Math.sin(seconds*2.1)*150;
   target={x:320+drift,y:178+Math.cos(seconds*1.25)*44,r:36};
   disk(target.x,target.y,41,"#e5bf7c");disk(target.x,target.y,32,"#b84543");
   disk(target.x,target.y,22,"#f8eed8");disk(target.x,target.y,10,"#b84543");
   ctx.fillStyle="#e7f4f6";ctx.font="17px sans-serif";ctx.fillText("Touch the moving target",205,308);
  }else if(mode==="safe"){
   const cx=320,cy=195,r=104;
   disk(cx,cy,r+9,"#a17947");disk(cx,cy,r,"#182a36");
   ctx.save();ctx.translate(cx,cy);ctx.rotate(arcAngle*Math.PI/180);
   for(let i=0;i<40;i++){
    const a=i*Math.PI/20;ctx.strokeStyle=i%5===0?"#f6ddb0":"#9faeb7";
    ctx.lineWidth=i%5===0?3:1.4;ctx.beginPath();
    ctx.moveTo(Math.sin(a)*78,-Math.cos(a)*78);
    ctx.lineTo(Math.sin(a)*(i%5===0?94:89),-Math.cos(a)*(i%5===0?94:89));ctx.stroke();
   }
   ctx.restore();disk(cx,cy,36,"#c8ad7e");disk(cx,cy,22,"#233747");
   ctx.fillStyle="#fff0c0";ctx.beginPath();ctx.moveTo(cx,cy-r-14);ctx.lineTo(cx-12,cy-r-32);ctx.lineTo(cx+12,cy-r-32);ctx.fill();
   ctx.fillStyle="#dcebf0";ctx.font="16px sans-serif";
   ctx.fillText(["Clockwise →","← Anticlockwise","Clockwise →","Practice tumbler open!"][clamp(progress.progress,0,3)],245,330);
  }else if(mode==="snowman"){
   disk(315,269,72,"#e6eef5");disk(315,185,53,"#f4f8fa");disk(315,119,37,"#f4f8fa");
   disk(303,111,4,"#263442");disk(327,111,4,"#263442");
   ctx.fillStyle="#dc8c36";ctx.beginPath();ctx.moveTo(316,125);ctx.lineTo(338,131);ctx.lineTo(315,133);ctx.fill();
   target={x:145+Math.sin(seconds)*15,y:195,r:26};
   ctx.fillStyle="#ba3f42";ctx.fillRect(target.x-23,target.y-20,46,40);
   ctx.fillStyle="#e5d6ab";ctx.font="14px sans-serif";ctx.fillText(selected?"Tap snowman!":"Drag / select accessory",48,320);
  }else if(mode==="catch"){
   const period=1500,phase=(progress.elapsed_ms%period)/period;
   flakeX=90+((Math.floor(progress.elapsed_ms/period)*149)%450);
   flakeY=70+phase*255;
   basketX=clamp(progress.position*W,45,W-45);
   ctx.font="38px Georgia";ctx.fillText("❄",flakeX-16,flakeY+12);
   ctx.fillStyle="#bd8150";ctx.fillRect(basketX-53,307,106,22);
   ctx.strokeStyle="#e7c8a1";ctx.lineWidth=6;ctx.beginPath();ctx.arc(basketX,311,45,Math.PI,0);ctx.stroke();
   ctx.fillStyle="#e5eff4";ctx.font="15px sans-serif";ctx.fillText("Move the basket to catch flakes",185,95);
  }else{
   ctx.fillStyle="#e8f2f6";ctx.font="bold 21px Georgia";ctx.fillText("Which one is a traditional snowman nose?",75,130);
   const choices=["Carrot","Teapot","Pineapple"];
   choices.forEach((choice,i)=>{
    const x=64+i*182;ctx.fillStyle="#314f61";ctx.fillRect(x,178,164,86);
    ctx.strokeStyle="#d9c394";ctx.lineWidth=2;ctx.strokeRect(x,178,164,86);
    ctx.fillStyle="#f7ecdc";ctx.font="18px sans-serif";ctx.fillText((i+1)+". "+choice,x+15,227);
   });
  }
 }
 function interact(x,y){
  if(!running)return;
  if(mode==="gallery"){
   const ok=Math.hypot(x-target.x,y-target.y)<target.r+5;mark(ok,ok?"Bullseye!":"Missed — try again.");
  }else if(mode==="snowman"){
   if(Math.hypot(x-target.x,y-target.y)<48){selected=true;report("Accessory selected. Drop it on the snowman.");}
   else if(selected&&Math.hypot(x-315,y-185)<90){selected=false;progress.progress=Math.min(30,progress.progress+1);mark(true,"Accessory fitted!");}
   else mark(false,"Select an accessory first.");
  }else if(mode==="trivia"){
   if(y>=178&&y<=264&&x>=64&&x<64+3*182){
    const n=Math.floor((x-64)/182),ok=n===0;mark(ok,ok?"Correct — carrot!":"Not quite. Try the carrot.");
   }
  }
 }
 function dial(x,y){
  const angle=Math.atan2(y-195,x-320)*180/Math.PI;
  if(lastDial===null){lastDial=angle;return}
  let delta=angle-lastDial;
  if(delta>180)delta-=360;
  if(delta< -180)delta+=360;
  lastDial=angle;
  if(Math.abs(delta)>80)return;
  arcAngle=clamp(arcAngle+delta,-720,720);progress.angle=Math.round(arcAngle);
  const dir=delta>=0?1:-1,required=[1,-1,1][progress.progress]||1;
  if(Math.abs(delta)>1 && dir===required){arcDir+=Math.abs(delta);}
  else if(Math.abs(delta)>1)arcDir=0;
  if(arcDir>=110&&progress.progress<3){
   arcDir=0;progress.progress++;mark(true,"Tumbler "+progress.progress+" unlocked!");
  }
  dirty=true;
 }
 function inputDown(event){
  if(!running)return;
  const p=coords(event);pointer=true;try{canvas.setPointerCapture(event.pointerId)}catch{}
  if(mode==="safe"){lastDial=null;dial(p.x,p.y);}
  else if(mode==="catch"){progress.position=p.x/W;dirty=true;}
  else interact(p.x,p.y);
  event.preventDefault();
 }
 function inputMove(event){
  if(!pointer||!running)return;
  const p=coords(event);
  if(mode==="safe")dial(p.x,p.y);
  if(mode==="catch"){progress.position=p.x/W;dirty=true;}
  if(mode==="snowman"&&selected&&Math.hypot(p.x-315,p.y-185)<78){
   selected=false;progress.progress=Math.min(30,progress.progress+1);mark(true,"Accessory fitted!");
  }
  event.preventDefault();
 }
 function inputUp(){pointer=false;lastDial=null}
 function keyboard(event){
  if(!running)return;
  if(mode==="trivia"&&["1","2","3"].includes(event.key)){
   mark(event.key==="1",event.key==="1"?"Correct — carrot!":"Wrong answer");event.preventDefault();return;
  }
  if(["ArrowLeft","ArrowRight"].includes(event.key)){
   const direction=event.key==="ArrowLeft"?-1:1;
   progress.position=clamp(progress.position+direction*.08,0,1);
   if(mode==="safe")dial(320+Math.cos(arcAngle*Math.PI/180+direction*.35)*90,
                         195+Math.sin(arcAngle*Math.PI/180+direction*.35)*90);
   dirty=true;event.preventDefault();
  }
  if([" ","Enter"].includes(event.key)){
   if(mode==="gallery")interact(target.x,target.y);
   else if(mode==="snowman"){selected=true;interact(315,185)}
   else if(mode==="catch")progress.position=flakeX/W;
   else if(mode==="trivia")mark(true,"Correct — carrot!");
   event.preventDefault();
  }
 }
 async function checkpoint(finish=false){
  if(pendingSave){
   await pendingSave;
   return finish||dirty?checkpoint(finish):true;
  }
  if(!dirty&&!finish)return true;
  const snapshot={...progress},expected=revision,changeCount=JSON.stringify(snapshot);
  pendingSave=(async()=>{
   try{
    const updated=await save({session_id:session.session_id,revision:expected,state:snapshot,finish});
    revision=updated.revision;
    if(JSON.stringify(progress)===changeCount)dirty=false;
    if(updated.status==="finished"){running=false;finished=true;}
    report("Practice checkpoint saved on the server.");
    return true;
   }catch(e){report("Save failed: "+(e.message||"retry after reconnect"));dirty=true;return false}
  })();
  try{return await pendingSave}
  finally{pendingSave=null}
 }
 function tick(t){
  if(disposed)return;
  if(running){
   if(last)progress.elapsed_ms=clamp(Math.round(progress.elapsed_ms+Math.min(80,Math.max(0,t-last))),0,limit);
   dirty=true;
   if(mode==="catch"){
    const phase=progress.elapsed_ms%1500;
    if(phase>=1420&&lastSave!==Math.floor(progress.elapsed_ms/1500)){
     lastSave=Math.floor(progress.elapsed_ms/1500);
     const x=90+(((lastSave-1)*149)%450),ok=Math.abs(x-progress.position*W)<75;
     mark(ok,ok?"Snowflake caught!":"Missed a snowflake.");
    }
   }
   if(progress.elapsed_ms===limit){running=false;void checkpoint(true)}
  }
  last=t;
  frame();
  report(feedback);
  if(dirty&&!saving&&t-(tick.lastSync||0)>7000){
   tick.lastSync=t;void checkpoint(false);
  }
  raf=global.requestAnimationFrame(tick);
 }
 function onControl(event){
  const button=event.target.closest("button[data-training]");if(!button)return;
  const action=button.dataset.training;
  if(action==="play"&&progress.elapsed_ms<limit&&!finished){
   running=true;last=0;report("Practice running. Good luck!");canvas.focus();
  }
  if(action==="pause"){running=false;void checkpoint(false);report("Paused — progress saved when connected.");}
  if(action==="sound"){sound=!sound;button.textContent="Sound "+(sound?"on":"off");button.setAttribute("aria-pressed",String(sound))}
  if(action==="finish"){running=false;void checkpoint(true)}
  if(action==="exit"){
   running=false;void checkpoint(false).then(ok=>{if(ok){dispose();onExit?.()}});
  }
 }
 function visibility(){if(global.document.hidden&&running){running=false;void checkpoint(false);report("Paused automatically while away.")}}
 function dispose(){
  if(disposed)return;disposed=true;running=false;global.cancelAnimationFrame(raf);
  canvas.removeEventListener("pointerdown",inputDown);canvas.removeEventListener("pointermove",inputMove);
  canvas.removeEventListener("pointerup",inputUp);canvas.removeEventListener("pointercancel",inputUp);
  canvas.removeEventListener("keydown",keyboard);root.removeEventListener("click",onControl);
  global.document.removeEventListener("visibilitychange",visibility);
  try{audio?.close()}catch{}
 }
 canvas.addEventListener("pointerdown",inputDown);canvas.addEventListener("pointermove",inputMove);
 canvas.addEventListener("pointerup",inputUp);canvas.addEventListener("pointercancel",inputUp);
 canvas.addEventListener("keydown",keyboard);root.addEventListener("click",onControl);
 global.document.addEventListener("visibilitychange",visibility);
 report("Ready to train — press Start / resume.");
 raf=global.requestAnimationFrame(tick);
 return {dispose,pause:()=>{running=false;void checkpoint(false)},save:checkpoint};
}

/* Shared scene host: reusable for the full Gallery and later Safecracker,
   Snowman, Catch and Trivia. Gameplay/validation remain in mode controllers. */
function mountScene({root,title,help,getStatus,getHud,draw,onStart,onPause,
                     onFinish,onShot,onExit,onTick,hudFields,extraActions,onExtraAction,
                     onPointer,onKey,showAim=true,welcome}){
 if(!root||typeof draw!=="function"||(typeof onShot!=="function"&&typeof onPointer!=="function"))
  throw Error("Invalid arcade scene");
 let disposed=false,busy=false,shotBusy=false,muted=true,audio=null,frame=0;
 let lastHud=0,lastTick=0,aim={x:320,y:182},particles=[];
 const fields=Array.isArray(hudFields)&&hudFields.length?hudFields:[
  {key:"time",initial:"45s"},{key:"wave",initial:"Wave 1/3"},
  {key:"score",initial:"0/100"},{key:"ammo",initial:"32 balls"},
  {key:"combo",initial:"0 streak"},{key:"accuracy",initial:"0% accurate"}];
 const additional=Array.isArray(extraActions)?extraActions:[];
 const safe=s=>String(s).replace(/[&<>"']/g,ch=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
 root.classList.remove("hidden");
 root.innerHTML="<div class='arcade-training-head'><div>"+
  "<p class='eyebrow'>WINTER ARCADE 2.0 · SKILL GAME · UNRANKED QA</p>"+
  "<h3>"+safe(title)+"</h3><p>"+safe(help)+"</p></div>"+
  "<button type='button' class='button button-outline' data-scene='exit'>Save & close</button></div>"+
  "<div class='arcade-training-status arcade-gallery-hud' aria-live='off'>"+
  fields.map(f=>"<span data-scene-label='"+safe(f.key)+"'>"+safe(f.initial||"—")+"</span>").join("")+"</div>"+
  "<canvas class='arcade-training-canvas' width='640' height='360' tabindex='0' "+
  "aria-label='"+safe(title)+"; move the crosshair with pointer or arrows and throw with touch, click, Space or Enter'></canvas>"+
  "<p class='arcade-training-feedback' role='status' aria-live='polite'></p>"+
  "<div class='arcade-training-controls'>"+
  "<button type='button' class='button button-gold' data-scene='start'>Start / resume</button>"+
  "<button type='button' class='button button-outline' data-scene='pause'>Pause</button>"+
  "<button type='button' class='button button-outline' data-scene='sound' aria-pressed='false'>Sound off</button>"+
  "<button type='button' class='button button-outline' data-scene='finish'>End run</button>"+
  additional.map(a=>"<button type='button' class='button button-gold' data-scene='"+
    safe(a.key)+"'>"+safe(a.label)+"</button>").join("")+"</div>";
 const canvas=root.querySelector("canvas"),ctx=canvas.getContext("2d");
 if(!ctx)throw Error("Canvas 2D support required.");
 const message=root.querySelector(".arcade-training-feedback");
 const button=name=>root.querySelector("[data-scene='"+name+"']");
 const label=name=>root.querySelector("[data-scene-label='"+name+"']");
 const playable=()=>getStatus()==="active";
 function feedback(text){if(message.textContent!==text)message.textContent=text}
 function sound(ok=true){
  if(muted)return;
  try{
   const C=global.AudioContext||global.webkitAudioContext;
   if(!C)return;
   audio=audio||new C();
   const oscillator=audio.createOscillator(),gain=audio.createGain();
   const time=audio.currentTime;
   oscillator.type=ok?"triangle":"square";
   oscillator.frequency.setValueAtTime(ok?740:210,time);
   oscillator.frequency.exponentialRampToValueAtTime(ok?1060:110,time+.1);
   gain.gain.setValueAtTime(.025,time);
   gain.gain.exponentialRampToValueAtTime(.001,time+.14);
   oscillator.connect(gain);gain.connect(audio.destination);
   oscillator.start(time);oscillator.stop(time+.15);
  }catch{}
 }
 function mouse(event){
  const b=canvas.getBoundingClientRect();
  const x=Math.min(640,Math.max(0,(event.clientX-b.left)*640/b.width));
  const y=Math.min(360,Math.max(0,(event.clientY-b.top)*360/b.height));
  return {x:Math.round(x),y:Math.round(y)};
 }
 async function act(fn,action){
  if(busy||disposed)return;
  busy=true;
  try{await fn();feedback(getHud().feedback||"Ready.")}
  catch(e){feedback((action||"Action")+" failed: "+(e.message||"Refresh and retry."))}
  finally{busy=false;updateHud()}
 }
 async function shoot(){
  if(!playable()||shotBusy||busy||disposed)return;
  shotBusy=true;
  const x=Math.round(aim.x),y=Math.round(aim.y);
  try{
   const outcome=await onShot({x,y});
   const ok=outcome?.outcome==="hit"||outcome?.outcome==="gold";
   particles.push({x,y,until:performance.now()+330,ok});
   sound(ok);
   feedback(outcome?.feedback||"Snowball thrown.");
  }catch(e){feedback("Shot not confirmed: "+(e.message||"check your connection"))}
  finally{shotBusy=false;updateHud()}
 }
 function pointer(event){
  aim=mouse(event);
  if(onPointer){
   if(event.type==="pointerdown"){
    canvas.focus();
    try{canvas.setPointerCapture(event.pointerId)}catch{}
   }
   onPointer({type:event.type,x:aim.x,y:aim.y,pointerId:event.pointerId},event);
   event.preventDefault();
   return;
  }
  if(event.type==="pointerdown"){
   canvas.focus();
   if(playable())void shoot();
   event.preventDefault();
  }
 }
 function keyboard(event){
  if(onKey&&onKey({key:event.key,shiftKey:!!event.shiftKey},event)){
   event.preventDefault();return;
  }
  const step=event.shiftKey?22:12;
  if(event.key==="ArrowLeft")aim.x=Math.max(0,aim.x-step);
  else if(event.key==="ArrowRight")aim.x=Math.min(640,aim.x+step);
  else if(event.key==="ArrowUp")aim.y=Math.max(0,aim.y-step);
  else if(event.key==="ArrowDown")aim.y=Math.min(360,aim.y+step);
  else if(event.key===" "||event.key==="Enter")void shoot();
  else return;
  event.preventDefault();
 }
 function updateHud(){
  if(disposed)return;
  const values=getHud()||{};
  for(const {key} of fields){
   const node=label(key);
   if(node&&values[key]!==undefined)node.textContent=String(values[key]);
  }
  button("start").disabled=busy||shotBusy;
  button("start").textContent=getStatus()==="finished"?"Play again":playable()?"Playing":"Start / resume";
  button("pause").disabled=busy||shotBusy||!playable();
  button("finish").disabled=busy||shotBusy||getStatus()==="finished";
  for(const action of additional){
   const control=button(action.key);
   if(control)control.disabled=busy||shotBusy||!playable();
  }
 }
 function tick(time){
  if(disposed)return;
  try{
   draw(ctx,{time,aim,reduced:reduced(),width:640,height:360});
   particles=particles.filter(p=>p.until>time);
   for(const p of particles){
    ctx.save();
    const r=7+(.33-(p.until-time)/1000)*55;
    ctx.globalAlpha=Math.max(0,(p.until-time)/330);
    ctx.strokeStyle=p.ok?"#ffdd83":"#f2f7ff";
    ctx.lineWidth=3;
    ctx.beginPath();ctx.arc(p.x,p.y,Math.max(4,r),0,Math.PI*2);ctx.stroke();
    ctx.restore();
   }
   if(showAim){
    // Crosshair overlay is optional: the safe uses a physical dial.
    ctx.strokeStyle="#f8e8cc";ctx.lineWidth=2;
    ctx.beginPath();ctx.arc(aim.x,aim.y,17,0,Math.PI*2);
    ctx.moveTo(aim.x-25,aim.y);ctx.lineTo(aim.x-9,aim.y);
    ctx.moveTo(aim.x+9,aim.y);ctx.lineTo(aim.x+25,aim.y);
    ctx.moveTo(aim.x,aim.y-25);ctx.lineTo(aim.x,aim.y-9);
    ctx.moveTo(aim.x,aim.y+9);ctx.lineTo(aim.x,aim.y+25);ctx.stroke();
   }
   if(time-lastHud>=250){lastHud=time;updateHud()}
   if(time-lastTick>=900){lastTick=time;onTick?.()}
  }catch(e){feedback("Drawing error: "+(e.message||"try reloading."))}
  frame=global.requestAnimationFrame(tick);
 }
 function controls(event){
  const node=event.target.closest("button[data-scene]");
  if(!node||disposed)return;
  const cmd=node.dataset.scene;
  if(cmd==="start")void act(onStart,"Start");
  if(cmd==="pause")void act(onPause,"Pause");
  if(cmd==="finish")void act(onFinish,"Finish");
  if(additional.some(a=>a.key===cmd)&&onExtraAction)
   void act(()=>onExtraAction(cmd),cmd);
  if(cmd==="sound"){
   muted=!muted;node.textContent="Sound "+(muted?"off":"on");
   node.setAttribute("aria-pressed",String(!muted));
   if(!muted)sound();
  }
  if(cmd==="exit")void act(async()=>{
   await onExit();dispose();
  },"Close");
 }
 function visibility(){
  if(global.document.hidden&&playable())void act(onPause,"Pause");
 }
 function dispose(){
  if(disposed)return;disposed=true;
  global.cancelAnimationFrame(frame);
  canvas.removeEventListener("pointerdown",pointer);
  canvas.removeEventListener("pointermove",pointer);
  canvas.removeEventListener("pointerup",pointer);
  canvas.removeEventListener("pointercancel",pointer);
  canvas.removeEventListener("keydown",keyboard);
  root.removeEventListener("click",controls);
  global.document.removeEventListener("visibilitychange",visibility);
  try{audio?.close()}catch{}
 }
 canvas.addEventListener("pointerdown",pointer);
 canvas.addEventListener("pointermove",pointer);
 canvas.addEventListener("pointerup",pointer);
 canvas.addEventListener("pointercancel",pointer);
 canvas.addEventListener("keydown",keyboard);
 root.addEventListener("click",controls);
 global.document.addEventListener("visibilitychange",visibility);
 feedback(welcome||"Ready to enter the gallery. Aim with mouse, touch or arrow keys.");
 updateHud();
 frame=global.requestAnimationFrame(tick);
 return {dispose,pause:()=>act(onPause,"Pause"),update:updateHud,
         setFeedback:feedback,tone:sound};
}

global.SnowfallArcadeV299=Object.freeze({mount,mountScene,modes:Object.freeze(Object.keys(MODES))});
})(window);
