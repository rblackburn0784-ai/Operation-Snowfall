// v2.9.9e — interactive quiz present cards, letter tiles, touch/keyboard and API.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const core=readFileSync(path.join(root,"arcade-v299.js"),"utf8");
const source=readFileSync(path.join(root,"arcade-trivia-v299e.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const app=readFileSync(path.join(root,"app.js"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
let clock=100,animation=null;
const win={
 requestAnimationFrame(fn){animation=fn;return 1;},
 cancelAnimationFrame(){animation=null;},
 matchMedia:()=>({matches:false}),
 document:{hidden:false,addEventListener(){},removeEventListener(){}},
};
const canvasCtx=new Proxy({},{
 get(_target,key){
  if(key==="createLinearGradient")return ()=>({addColorStop(){}});
  if(key==="measureText")return text=>({width:String(text).length*8});
  return ()=>{};
 },
 set(){return true},
});
const sandbox={window:win,console,performance:{now:()=>clock},
 Image:class {src="";complete=false;naturalWidth=0}};
vm.runInNewContext(core,sandbox);
vm.runInNewContext(source,sandbox);
const q=(kind,level=1)=>{
 if(kind==="scramble")return {id:"tiles",kind,level,level_name:"Snowy Warmup",
  prompt:"Unscramble this festive decoration.",options:[],
  tiles:["N","I","T","L","E","S"],limit_ms:16000};
 if(kind==="truefalse")return {id:"boolean",kind,level,level_name:"Snowy Warmup",
  prompt:"Christmas is in December.",options:["True","False"],tiles:[],
  limit_ms:16000};
 return {id:"gift",kind:"gift",level,level_name:"Snowy Warmup",
  prompt:"Which animal pulls Santa's sleigh?",
  options:["Reindeer","Penguins","Horses","Polar bears"],tiles:[],
  limit_ms:16000};
};
const fresh=(kind="gift",step=0)=>({
 session_id:"a".repeat(32),mode:"trivia",status:"paused",day:1,
 practice:true,competitive:false,step,total_questions:15,round:1,total_rounds:3,
 duration_ms:210000,elapsed_ms:0,question_remaining_ms:16000,
 question:q(kind),correct:0,wrong:0,timeouts:0,streak:0,best_streak:0,
 score:0,feedback:"",history:[],last_answer:null,
});
function fakeUI(){
 const stage={},controls={},nodes={};
 const make=()=>({textContent:"",disabled:false,attrs:{},dataset:{},
  setAttribute(k,v){this.attrs[k]=v}});
 const canvas={
  getContext:()=>canvasCtx,getBoundingClientRect:()=>({
   left:0,top:0,width:640,height:360,
  }),setPointerCapture(){},focus(){},
  addEventListener(k,fn){stage[k]=fn},
  removeEventListener(k){delete stage[k]}
 };
 const element={
  innerHTML:"",classList:{remove(){},add(){}},
  querySelector(sel){
   if(sel==="canvas")return canvas;
   if(sel===".arcade-training-feedback")
    return nodes.feedback??(nodes.feedback=make());
   const button=sel.match(/data-scene='([^']+)'/);
   if(button)return nodes[button[1]]??(nodes[button[1]]=make());
   const label=sel.match(/data-scene-label='([^']+)'/);
   if(label)return nodes[label[1]]??(nodes[label[1]]=make());
   throw Error("Unexpected selector "+sel);
  },
  addEventListener(k,fn){controls[k]=fn},
  removeEventListener(k){delete controls[k]}
 };
 const button=name=>controls.click({
  target:{closest:()=>({dataset:{scene:name}})}
 });
 const pointer=(type,x,y,ptr=1)=>stage[type]({
  type,clientX:x,clientY:y,pointerId:ptr,preventDefault(){}
 });
 const key=(name,shiftKey=false)=>stage.keydown({
  key:name,shiftKey,preventDefault(){}
 });
 function frame(t){
  clock=t;const f=animation;
  assert.equal(typeof f,"function");f(t);
 }
 return {element,stage,controls,nodes,button,pointer,key,frame};
}
async function drain(){
 await new Promise(r=>setImmediate(r));
 await new Promise(r=>setImmediate(r));
}
function boot(ui,source=fresh()){
 let saved=source;
 const submitted=[];
 const game=win.SnowfallTriviaV299e.mount({
  root:ui.element,session:saved,
  start:async()=>saved={...fresh(),session_id:"b".repeat(32)},
  control:async(_sid,op)=>saved={...saved,status:
   op==="resume"?"active":op==="finish"?"finished":"paused"},
  answer:async body=>{
   submitted.push(body);
   const step=saved.step+1,kind=saved.question.kind;
   saved={...saved,step,question:q("gift"),correct:saved.correct+1,
    score:saved.score+7,question_remaining_ms:16000,
    last_answer:{step:body.step,kind,selected:body.answer,
     answer:"Correct server answer",verdict:"correct",
     explanation:"Festive success!",points:7},
    feedback:"Correct! +7",};
   return saved;
  },
  refresh:async()=>saved,
  fetchRecord:async()=>({personal_best:99,finished_runs:1}),
  onExit:()=>{},
 });
 return {game,submitted,get:()=>saved};
}
test("Trivia is full shared Arcade mode with independent QA switch",()=>{
 assert.equal(typeof win.SnowfallTriviaV299e.mount,"function");
 assert.equal(typeof win.SnowfallArcadeV299.mountScene,"function");
 assert.match(html,/arcade-trivia-v299e\.js\?v=299e/);
 assert.match(html,/id="arcadeTrivia"/);
 assert.ok(html.indexOf("arcade-v299.js")<html.indexOf("arcade-trivia-v299e.js"));
 assert.match(css,/arcade-full-trivia/);
 assert.match(css,/touch-action:none/);
 assert.match(app,/trivia_v299e_enabled/);
 assert.match(app,/\/v1\/game\/arcade\/trivia\/answer/);
 for(const path of ["gallery/shot","safecracker/move","snowman/place",
                     "catch/update","move"])
  assert.ok(app.includes("/v1/game/arcade/"+path));
});
test("tap a gift sends selected server option but never a score or win flag",async()=>{
 clock=100;
 const ui=fakeUI(),run=boot(ui);
 assert.match(ui.element.innerHTML,/Check selected/);
 ui.button("start");await drain();
 assert.equal(run.get().status,"active");
 ui.pointer("pointerdown",70,180);
 ui.pointer("pointerup",70,180);
 await drain();
 assert.deepEqual(JSON.parse(JSON.stringify(run.submitted)),[
  {session_id:"a".repeat(32),step:0,answer:"Reindeer"},
 ]);
 assert.equal(run.game.getSnapshot().step,1);
 assert.equal(Object.hasOwn(run.submitted[0],"score"),false);
 assert.equal(Object.hasOwn(run.submitted[0],"correct"),false);
 assert.match(ui.nodes.feedback.textContent,/Correct/);
 run.game.dispose();
 assert.equal(ui.stage.pointerup,undefined);
});
test("True/False can be answered with large touch cards and number keys",async()=>{
 clock=100;
 const ui=fakeUI(),run=boot(ui,fresh("truefalse",2));
 ui.button("start");await drain();
 ui.pointer("pointerup",400,216);await drain();
 assert.equal(run.submitted.length,1);
 assert.equal(run.submitted[0].answer,"False");
 assert.equal(run.submitted[0].step,2);
 run.game.dispose();
 const ui2=fakeUI(),other=boot(ui2,fresh("truefalse",2));
 ui2.button("start");await drain();
 ui2.key("1");await drain();
 assert.equal(other.submitted[0].answer,"True");
 other.game.dispose();
});
test("scrambled-letter tap controls build each letter in the chosen order",async()=>{
 clock=100;
 const ui=fakeUI(),run=boot(ui,fresh("scramble",4));
 ui.button("start");await drain();
 const rects=win.SnowfallTriviaV299e.tileRects(q("scramble").tiles);
 assert.equal(rects.length,6);
 assert.ok(rects.every(b=>b.y>=155&&b.x>=0&&b.x+b.w<=640));
 // TINSEL needs tile indices 2,1,0,5,4,3.
 for(const index of [2,1,0,5,4,3]){
  const box=rects[index];
  ui.pointer("pointerup",box.x+box.w/2,box.y+23);
 }
 assert.equal(run.game.getLetters().join(","),"2,1,0,5,4,3");
 ui.pointer("pointerup",495,293);
 await drain();
 assert.equal(run.submitted[0].answer,"TINSEL");
 assert.equal(run.submitted[0].step,4);
 run.game.dispose();
});
test("letter mistake correction works with Undo, Clear and keyboard",async()=>{
 clock=100;
 const ui=fakeUI(),run=boot(ui,fresh("scramble",4));
 ui.button("start");await drain();
 ui.key("1");ui.key("2");
 assert.deepEqual(JSON.parse(JSON.stringify(run.game.getLetters())),[0,1]);
 ui.key("Backspace");
 assert.deepEqual(JSON.parse(JSON.stringify(run.game.getLetters())),[0]);
 ui.button("clear");await drain();
 assert.equal(run.game.getLetters().length,0);
 ui.button("check");await drain();
 assert.equal(run.submitted.length,0);
 assert.match(ui.nodes.feedback.textContent,/Use every letter/);
 ui.key("3");ui.key("2");ui.key("1");ui.key("6");ui.key("5");ui.key("4");
 ui.key("Enter");await drain();
 assert.equal(run.submitted[0].answer,"TINSEL");
 run.game.dispose();
});
test("question timer and render frame work without revealing solutions",async()=>{
 clock=100;const ui=fakeUI(),run=boot(ui);
 ui.button("start");await drain();
 ui.frame(400);
 assert.ok(run.game.remaining()<=16000&&run.game.remaining()>0);
 assert.doesNotMatch(source,/clientScore|clientCorrect|setTimeout\(.*award/);
 assert.match(source,/onPointer:pointer,onKey:keyboard,showAim:false/);
 assert.ok(ui.nodes.question.textContent.includes("/15"));
 run.game.dispose();
});
