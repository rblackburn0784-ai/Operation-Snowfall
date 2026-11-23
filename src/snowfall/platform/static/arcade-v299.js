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
 let progress={...session.state},revision=session.revision,running=false,disposed=false;
 let raf=0,last=0,lastSave=0,dirty=false,saving=false,pointer=false,sound=false,audio=null;
 let target={x:200,y:160,r:32},basketX=320,flakeX=280,flakeY=0;
 let selected=false,arcAngle=Number(progress.angle)||0,arcDir=0,lastDial=null;
 let localChanged=0,feedback="Practice mode · results are not ranked.";
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
  play.disabled=progress.elapsed_ms>=limit||session.status==="finished";
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
  if(saving||!dirty&&!finish)return;
  saving=true;
  const snapshot={...progress},expected=revision,changeCount=JSON.stringify(snapshot);
  try{
   const updated=await save({session_id:session.session_id,revision:expected,state:snapshot,finish});
   revision=updated.revision;
   if(JSON.stringify(progress)===changeCount)dirty=false;
   if(updated.status==="finished")running=false;
   report("Practice checkpoint saved on the server.");
  }catch(e){report("Save failed: "+(e.message||"retry after reconnect"));dirty=true}
  finally{saving=false}
 }
 function tick(t){
  if(disposed)return;
  if(running){
   if(last)progress.elapsed_ms=clamp(progress.elapsed_ms+Math.min(80,Math.max(0,t-last)),0,limit);
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
  if(action==="play"&&progress.elapsed_ms<limit&&session.status!=="finished"){
   running=true;last=0;report("Practice running. Good luck!");canvas.focus();
  }
  if(action==="pause"){running=false;void checkpoint(false);report("Paused — progress saved when connected.");}
  if(action==="sound"){sound=!sound;button.textContent="Sound "+(sound?"on":"off");button.setAttribute("aria-pressed",String(sound))}
  if(action==="finish"){running=false;void checkpoint(true)}
  if(action==="exit"){
   running=false;void checkpoint(false).then(()=>{dispose();onExit?.()});
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
global.SnowfallArcadeV299=Object.freeze({mount,modes:Object.freeze(Object.keys(MODES))});
})(window);
