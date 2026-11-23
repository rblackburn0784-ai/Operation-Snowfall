/* v2.9.9e — Christmas Trivia on the shared Arcade 2.0 game scene.
   Three difficulty levels, gift-wrapped answers, True/False, interactive
   letter scramble, keyboard/touch and opt-in audio. All scoring is server-owned. */
(function(global){
"use strict";
const W=640,H=360,MAX=15,PALETTE={
 gold:"#eac98b",snow:"#e7f2fa",navy:"#11283e",red:"#ae3f4c",
 pine:"#18544e",ice:"#70c9cf",
};
const clamp=(v,min,max)=>Math.min(max,Math.max(min,v));
const giftBoxes=[
 {x:37,y:157,w:270,h:66},{x:333,y:157,w:270,h:66},
 {x:37,y:234,w:270,h:66},{x:333,y:234,w:270,h:66},
];
const tfBoxes=[{x:56,y:180,w:248,h:98},{x:336,y:180,w:248,h:98}];
const wordActions={
 confirm:{x:443,y:271,w:150,h:47},undo:{x:192,y:281,w:99,h:38},
 clear:{x:46,y:281,w:129,h:38},
};
function rectHit(x,y,rect){
 return x>=rect.x&&x<=rect.x+rect.w&&y>=rect.y&&y<=rect.y+rect.h;
}
function tileRects(tiles){
 const n=tiles.length, width=clamp((530-(n-1)*8)/n,35,55);
 const start=(W-(n*width+(n-1)*8))/2;
 return tiles.map((letter,i)=>({x:start+i*(width+8),y:161,w:width,h:49,
  letter,index:i}));
}
function rounded(ctx,x,y,w,h,r,fill,stroke){
 ctx.beginPath();ctx.roundRect(x,y,w,h,r);
 ctx.fillStyle=fill;ctx.fill();
 if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.stroke()}
}
function wrapped(ctx,x,y,w,h,index,highlighted,hasText){
 const fill=highlighted?"#6d4d5e":index%2?"#14544c":"#933d50";
 rounded(ctx,x,y,w,h,13,fill,highlighted?"#ffdf8c":"#8ea3a8");
 ctx.fillStyle="rgba(248,222,170,.24)";
 ctx.fillRect(x+w*.18,y+3,10,h-6);
 ctx.fillRect(x+3,y+h*.44,w-6,7);
 ctx.strokeStyle="#dfc38b";ctx.lineWidth=1.6;
 ctx.beginPath();ctx.arc(x+w*.18+6,y+7,8,Math.PI,2*Math.PI);ctx.stroke();
 if(!hasText)return;
}
function wrapText(ctx,text,x,y,maxWidth,lineHeight,maxLines=3){
 const words=String(text).split(/\s+/),lines=[];
 let line="";
 for(const word of words){
  const trial=line?line+" "+word:word;
  if(line&&ctx.measureText(trial).width>maxWidth){
   lines.push(line);line=word;
  }else line=trial;
 }
 if(line)lines.push(line);
 for(let i=0;i<Math.min(lines.length,maxLines);i++){
  const lineText=i===maxLines-1&&lines.length>maxLines?
    lines[i].slice(0,-2)+"…":lines[i];
  ctx.fillText(lineText,x,y+i*lineHeight);
 }
}
function mount({root,session,start,control,answer,refresh,fetchRecord,
                onExit,recoveredAction}){
 if(!global.SnowfallArcadeV299?.mountScene)
  throw Error("Arcade 2.0 shared scene unavailable.");
 let state=session,anchor=performance.now(),host=null;
 let selected=0,letters=[],busy=false,pending=recoveredAction||null;
 let refreshing=false,recordBusy=false,record=null;
 let lastRefresh=0,glowUntil=0,glowCorrect=null;
 const art=new Image();art.src="/art/v290/arcade/trivia.webp";

 function duration(){
  return state.status==="active"?
   Math.max(0,performance.now()-anchor):0;
 }
 function remaining(){
  return Math.max(0,Math.round((state.question_remaining_ms||0)-duration()));
 }
 function stage(){return Math.min(3,Math.floor(state.step/5)+1)}
 function active(){return state.status==="active"&&!!state.question}
 function currentAnswer(){return letters.map(i=>state.question?.tiles?.[i]||"").join("")}
 function summary(){
  return (state.score||0)+"/100 · "+(state.correct||0)+" correct · "+
    (state.best_streak||0)+" best streak";
 }
 function apply(view){
  if(!view||view.mode!=="trivia"||typeof view.step!=="number")
   throw Error("Invalid Christmas Trivia response.");
  const previous=state,changed=view.session_id!==state.session_id||
    view.step!==state.step;
  if(view.session_id!==state.session_id){record=null;pending=null}
  state=view;anchor=performance.now();
  if(changed){selected=0;letters=[]}
  if(pending&&view.step>pending.step)pending=null;
  if(changed&&view.last_answer&&view.last_answer.step===view.step-1){
   glowCorrect=view.last_answer.verdict==="correct";
   glowUntil=performance.now()+1150;
   host?.tone(glowCorrect);
   host?.setFeedback((glowCorrect?"✓ ":"✕ ")+
    (view.feedback||view.last_answer.explanation));
  }else if(view.feedback&&view.feedback!==previous.feedback)
   host?.setFeedback(view.feedback);
  if(view.status==="finished"&&!record&&!recordBusy&&fetchRecord){
   recordBusy=true;
   void fetchRecord().then(v=>{record=v}).catch(()=>{})
    .finally(()=>{recordBusy=false});
  }
  host?.update();
 }
 async function begin(){
  if(state.status==="active")return;
  let view=state.status==="finished"?await start():state;
  if(view.status==="paused")
   view=await control(view.session_id,"resume");
  apply(view);
 }
 async function pause(){
  if(state.status==="active")apply(await control(state.session_id,"pause"));
 }
 async function finish(){
  if(state.status!=="finished")apply(await control(state.session_id,"finish"));
 }
 async function close(){if(state.status==="active")await pause();onExit?.()}
 async function resync(){
  if(refreshing||state.status!=="active")return;
  refreshing=true;
  const sid=state.session_id,step=state.step;
  try{
   const v=await refresh(sid);
   if(sid===state.session_id&&v.step>=step)apply(v);
  }finally{refreshing=false}
 }
 async function submit(choice){
  if(!active()||busy)return;
  const q=state.question;
  let value=choice;
  if(q.kind==="scramble"){
   value=currentAnswer();
   if(value.length!==q.tiles.length){
    host?.setFeedback("Use every letter, then press Check word.");
    return;
   }
  }
  if(typeof value!=="string"||!value)return;
  if(pending&&(pending.step!==state.step||pending.answer!==value)){
   host?.setFeedback("Please retry the interrupted answer first.");
   return;
  }
  busy=true;
  const body=pending||{session_id:state.session_id,step:state.step,answer:value};
  try{
   const result=await answer(body);
   apply(result);pending=null;
  }catch(e){
   if([400,409,422].includes(e?.status)){
    pending=null;
    try{apply(await refresh(body.session_id))}catch{}
    host?.setFeedback(e.message||"Answer was rejected. Try again.");
   }else{
    if(!pending)pending=body;
    try{
     const latest=await refresh(body.session_id);
     if(latest.step>body.step){
      apply(latest);pending=null;
      host?.setFeedback("Last answer confirmed and saved.");
      return;
     }
   }catch{}
   host?.setFeedback("Connection interrupted. Retry the same answer.");
   }
  }finally{busy=false}
 }
 function addTile(index){
  const q=state.question;
  if(!q||q.kind!=="scramble"||letters.includes(index)||
      !Number.isInteger(index)||index<0||index>=q.tiles.length)return;
  letters.push(index);
 }
 function undoTile(){letters.pop()}
 function clearTiles(){letters=[]}
 async function retry(){
  if(pending)return submit(pending.answer);
  host?.setFeedback("No interrupted answer to retry.");
 }
 function pointer(p){
  if(!active()||busy||p.type!=="pointerup")return;
  const q=state.question;
  if(q.kind==="scramble"){
   if(rectHit(p.x,p.y,wordActions.confirm)){
    void submit(currentAnswer());return;
   }
   if(rectHit(p.x,p.y,wordActions.undo)){undoTile();return}
   if(rectHit(p.x,p.y,wordActions.clear)){clearTiles();return}
   const rect=tileRects(q.tiles).find(b=>rectHit(p.x,p.y,b));
   if(rect){addTile(rect.index);return}
   // Tap an assembled slot to remove its final tile.
   if(p.y>220&&p.y<268){undoTile();return}
  }else{
   const cards=q.kind==="truefalse"?tfBoxes:giftBoxes;
   const index=cards.findIndex(card=>rectHit(p.x,p.y,card));
   if(index>=0&&q.options[index]){
    selected=index;void submit(q.options[index]);
   }
  }
 }
 function keyboard({key}){
  if(!active()||busy)return false;
  const q=state.question;
  if(q.kind==="scramble"){
   if(/^[1-9]$/.test(key)){
    const index=Number(key)-1;
    if(index<q.tiles.length)addTile(index);
   }else if(key==="Backspace"){undoTile()}
   else if(key==="Escape"){clearTiles()}
   else if(key===" "||key==="Enter"){void submit(currentAnswer())}
   else return false;
   return true;
  }
  const n=q.options.length;
  if(/^[1-4]$/.test(key)&&Number(key)<=n){
   selected=Number(key)-1;
   void submit(q.options[selected]);return true;
  }
  if(key==="ArrowLeft"||key==="ArrowUp"){
   selected=(selected+n-1)%n;return true;
  }
  if(key==="ArrowRight"||key==="ArrowDown"){
   selected=(selected+1)%n;return true;
  }
  if(key===" "||key==="Enter"){void submit(q.options[selected]);return true}
  return false;
 }
 function snowParticle(ctx,x,y){
  ctx.strokeStyle="#d7edf7";ctx.lineWidth=1.5;
  for(let i=0;i<3;i++){
   const a=i*Math.PI/3;
   ctx.beginPath();ctx.moveTo(x-Math.cos(a)*5,y-Math.sin(a)*5);
   ctx.lineTo(x+Math.cos(a)*5,y+Math.sin(a)*5);ctx.stroke();
  }
 }
 function draw(ctx,{time,reduced}){
  const bg=ctx.createLinearGradient(0,0,W,H);
  bg.addColorStop(0,"#102b3c");bg.addColorStop(.55,"#23485a");
  bg.addColorStop(1,"#412e43");
  ctx.fillStyle=bg;ctx.fillRect(0,0,W,H);
  if(art.complete&&art.naturalWidth){
   ctx.save();ctx.globalAlpha=.17;ctx.drawImage(art,0,0,W,H);ctx.restore();
  }
  if(!reduced){
   for(let i=0;i<27;i++){
    const x=(i*111+time*.012*(i%3+1))%W,
          y=(i*43+time*.008*(i%4+1))%H;
    snowParticle(ctx,x,y);
   }
  }
  ctx.fillStyle=PALETTE.gold;ctx.font="bold 22px Georgia";
  ctx.textAlign="center";ctx.fillText("CHRISTMAS TRIVIA",W/2,30);
  ctx.font="bold 12px sans-serif";ctx.fillStyle="#e1e6ec";
  ctx.fillText("THE NORTH POLE QUIZ SHOW • 3 ROUNDS • UNRANKED QA",W/2,49);
  const q=state.question;
  if(q){
   const ticks=remaining(),frac=clamp(ticks/q.limit_ms,0,1);
   ctx.fillStyle="#152536";ctx.fillRect(30,58,580,7);
   ctx.fillStyle=ticks<3500?"#e06e6d":"#83d2cb";
   ctx.fillRect(30,58,580*frac,7);
   rounded(ctx,29,74,582,73,13,"rgba(6,25,37,.88)","#8eb0b6");
   ctx.font="bold 15px sans-serif";ctx.fillStyle=PALETTE.gold;
   ctx.textAlign="left";
   ctx.fillText("QUESTION "+(state.step+1)+" / "+MAX+
    " · "+q.level_name+" · "+
    (q.kind==="scramble"?"LETTER LOCK":q.kind==="truefalse"?
     "TRUE OR FALSE":"MYSTERY PRESENTS"),42,95);
   ctx.font="17px sans-serif";ctx.fillStyle="#f4f3ee";
   wrapText(ctx,q.prompt,42,116,554,19,2);
   ctx.font="bold 14px sans-serif";
   ctx.fillStyle=ticks<3500?"#ffd5bc":"#d1f4eb";
   ctx.textAlign="right";ctx.fillText(Math.ceil(ticks/1000)+"s",599,94);
  }
  if(q?.kind==="gift"||q?.kind==="truefalse"){
   const cards=q.kind==="gift"?giftBoxes:tfBoxes;
   cards.forEach((box,index)=>{
    if(!q.options[index])return;
    const highlighted=index===selected;
    if(q.kind==="gift"){
     wrapped(ctx,box.x,box.y,box.w,box.h,index,highlighted,true);
     ctx.fillStyle="#fff4dc";ctx.textAlign="center";
     ctx.font="bold 15px sans-serif";
     wrapText(ctx,String(index+1)+". "+q.options[index],
      box.x+box.w/2,box.y+28,box.w-38,18,2);
    }else{
     rounded(ctx,box.x,box.y,box.w,box.h,17,
      highlighted?"#425967":index===0?"#14635e":"#924955",
      highlighted?"#fae6b0":"#aec4c2");
     ctx.fillStyle="#f1e9ce";ctx.font="bold 30px Georgia";
     ctx.textAlign="center";
     ctx.fillText(index===0?"✓ TRUE":"✕ FALSE",
      box.x+box.w/2,box.y+52);
     ctx.font="13px sans-serif";ctx.fillText("Press "+(index+1),
      box.x+box.w/2,box.y+78);
    }
   });
  }else if(q?.kind==="scramble"){
   const tiles=tileRects(q.tiles);
   ctx.fillStyle="#f2d59d";ctx.font="bold 14px sans-serif";
   ctx.textAlign="center";ctx.fillText("TAP LETTERS IN ORDER TO UNLOCK THE WORD",
    320,155);
   tiles.forEach(t=>{
    const used=letters.includes(t.index);
    rounded(ctx,t.x,t.y,t.w,t.h,8,used?"#3b5763":"#a74f51",
     used?"#486f79":"#f1d8a0");
    ctx.fillStyle=used?"#82a6ad":"#fff2dd";
    ctx.font="bold 23px Georgia";
    ctx.fillText(t.letter,t.x+t.w/2,t.y+32);
    ctx.fillStyle=used?"#82a6ad":"#e7d6b8";
    ctx.font="10px sans-serif";
    ctx.fillText(String(t.index+1),t.x+t.w-10,t.y+12);
   });
   const answerText=letters.map(i=>q.tiles[i]).join("");
   rounded(ctx,95,222,450,44,8,"#17293a","#91bbc5");
   ctx.fillStyle="#f0e2ba";ctx.font="bold 24px Georgia";
   ctx.fillText((answerText||"—")+"  ".repeat(Math.max(0,q.tiles.length-letters.length)),
    320,251);
   rounded(ctx,wordActions.clear.x,wordActions.clear.y,
    wordActions.clear.w,wordActions.clear.h,9,"#355569","#8eb0b6");
   rounded(ctx,wordActions.undo.x,wordActions.undo.y,
    wordActions.undo.w,wordActions.undo.h,9,"#355569","#8eb0b6");
   rounded(ctx,wordActions.confirm.x,wordActions.confirm.y,
    wordActions.confirm.w,wordActions.confirm.h,10,
    letters.length===q.tiles.length?"#b9914f":"#596459","#e9d28b");
   ctx.font="bold 15px sans-serif";ctx.fillStyle="#fff5dc";
   ctx.fillText("CLEAR",111,305);ctx.fillText("UNDO",241,305);
   ctx.fillText("CHECK WORD",518,300);
  }
  ctx.textAlign="left";
  ctx.font="12px sans-serif";ctx.fillStyle="#dae6e9";
  ctx.fillText(q?.kind==="scramble"?
   "1–9: select letter • Backspace: undo • Enter: check":
   "Tap a present / card, or use number keys and Enter",33,346);
  if(time<glowUntil){
   ctx.save();
   ctx.fillStyle=glowCorrect?"rgba(58,149,114,.2)":"rgba(180,70,71,.2)";
   ctx.fillRect(0,0,W,H);ctx.restore();
  }
  if(state.status!=="active"){
   ctx.fillStyle="rgba(6,22,35,.93)";ctx.fillRect(60,84,520,224);
   ctx.strokeStyle="#e4c38d";ctx.lineWidth=2;ctx.strokeRect(60,84,520,224);
   ctx.textAlign="center";ctx.fillStyle="#f7e0aa";
   ctx.font="bold 26px Georgia";
   ctx.fillText(state.status==="finished"?"QUIZ COMPLETE!":
    "READY FOR CHRISTMAS TRIVIA?",320,143);
   ctx.font="16px sans-serif";ctx.fillStyle="#e4eef1";
   ctx.fillText(state.status==="finished"?state.result:
    "15 festive questions • 3 levels • Answer quickly for bonuses",
    320,190);
   ctx.fillText(state.status==="finished"?summary():
    "Choose presents, judge true/false and unscramble letters",
    320,226);
   if(state.status==="finished"&&record){
    ctx.font="15px sans-serif";ctx.fillStyle="#f1d398";
    ctx.fillText("Personal best: "+record.personal_best+"/100 · "+
     record.finished_runs+" completed",320,273);
   }
   ctx.textAlign="left";
  }
 }
 function hud(){
  const remainingMs=remaining();
  return {
   time:Math.ceil(remainingMs/1000)+"s",
   round:"Round "+stage()+"/3",
   question:(Math.min(MAX,state.step+1))+"/"+MAX+" questions",
   score:state.score+"/100",
   streak:state.streak+" in a row",
   correct:state.correct+" correct",
   feedback:state.feedback||"Choose an answer before the timer runs out.",
  };
 }
 function tick(){
  if(state.status!=="active")return;
  const time=performance.now();
  if(remaining()===0||time-lastRefresh>=4300){
   lastRefresh=time;void resync().catch(()=>{});
  }
 }
 host=global.SnowfallArcadeV299.mountScene({
  root,title:"Christmas Trivia",
  help:"Unwrap mystery presents, decide True or False, and arrange scrambled letters. Fifteen timed questions over three rising difficulty levels. Correct streaks and quick thinking earn practice points.",
  getStatus:()=>state.status,getHud:hud,draw,
  onStart:begin,onPause:pause,onFinish:finish,onExit:close,
  onTick:tick,onPointer:pointer,onKey:keyboard,showAim:false,
  hudFields:[{key:"time",initial:"16s"},{key:"round",initial:"Round 1/3"},
   {key:"question",initial:"1/15 questions"},{key:"score",initial:"0/100"},
   {key:"streak",initial:"0 in a row"},{key:"correct",initial:"0 correct"}],
  extraActions:[{key:"check",label:"Check selected / word"},
   {key:"undo",label:"Undo letter"},
   {key:"clear",label:"Clear letters"},
   {key:"retry",label:"Retry last answer"}],
  onExtraAction:async actionType=>{
   if(actionType==="retry"){await retry();return}
   if(actionType==="undo"){undoTile();return}
   if(actionType==="clear"){clearTiles();return}
   if(state.question?.kind==="scramble")
    await submit(currentAnswer());
   else if(state.question?.options?.[selected])
    await submit(state.question.options[selected]);
  },
  welcome:"Tap Start to play the Christmas Quiz Show. No daily arcade starts used.",
 });
 return {dispose:host.dispose,pause:host.pause,getSnapshot:()=>state,
   getPending:()=>pending,getLetters:()=>letters.slice(),selectLetter:addTile,
   clearLetters:clearTiles,submit,remaining};
}
global.SnowfallTriviaV299e=Object.freeze({mount,tileRects,rectHit,giftBoxes,
 tfBoxes,wordActions});
})(window);
