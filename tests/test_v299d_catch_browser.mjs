// v2.9.9d — Snowflake Catch animation, basket input, server-only scores.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const core=readFileSync(path.join(root,"arcade-v299.js"),"utf8");
const source=readFileSync(path.join(root,"arcade-catch-v299d.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const app=readFileSync(path.join(root,"app.js"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
let now=100,animation=null;
const win={
 requestAnimationFrame(fn){animation=fn;return 1},
 cancelAnimationFrame(){animation=null},
 matchMedia:()=>({matches:false}),
 document:{hidden:false,addEventListener(){},removeEventListener(){}},
};
const fakeCtx=new Proxy({},{
 get(_target,key){
  if(key==="createLinearGradient")return ()=>({addColorStop(){}});
  return ()=>{};
 },
 set(){return true},
});
const sandbox={window:win,console,performance:{now:()=>now},
 Image:class {src="";complete=false;naturalWidth=0}};
vm.runInNewContext(core,sandbox);
vm.runInNewContext(source,sandbox);
const schedule=[{
 id:0,kind:"snowflake",wave:1,start:650,flight:2550,impact:3200,
 x0:300,wind:40,sway:12,phase:0.2,
}];
const fresh=()=>({
 session_id:"a".repeat(32),mode:"catch",status:"paused",day:1,
 practice:true,competitive:false,duration_ms:60000,elapsed_ms:0,
 basket_x:320,action_seq:0,caught:0,missed:0,hazards:0,
 bonus:0,combo:0,best_combo:0,score:0,events:[],settled:[],
 schedule,feedback:"",
});
function ui(){
 const stage={},controls={},nodes={};
 const make=()=>({textContent:"",disabled:false,attrs:{},dataset:{},
  setAttribute(k,v){this.attrs[k]=v}});
 const canvas={
  getContext:()=>fakeCtx,getBoundingClientRect:()=>({
   left:0,top:0,width:640,height:360,
  }),
  setPointerCapture(){},focus(){},
  addEventListener(k,fn){stage[k]=fn},
  removeEventListener(k){delete stage[k]}
 };
 const element={
  innerHTML:"",classList:{remove(){},add(){}},
  querySelector(sel){
   if(sel==="canvas")return canvas;
   if(sel===".arcade-training-feedback")return nodes.feedback??(nodes.feedback=make());
   const action=sel.match(/data-scene='([^']+)'/);
   if(action)return nodes[action[1]]??(nodes[action[1]]=make());
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
 const pointer=(type,x,pointerId=1)=>stage[type]({
  type,clientX:x,clientY:303,pointerId,preventDefault(){}
 });
 const key=(name,shiftKey=false)=>stage.keydown({
  key:name,shiftKey,preventDefault(){}
 });
 function frame(t){
  now=t;
  const callback=animation;
  assert.equal(typeof callback,"function");
  callback(t);
 }
 return {element,nodes,button,pointer,key,frame,stage};
}
async function drain(){
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
}
function launch(view,handler){
 let snapshot=fresh();
 const actions=[];
 const runtime=win.SnowfallCatchV299d.mount({
  root:view.element,session:snapshot,
  start:async()=>snapshot={...fresh(),session_id:"b".repeat(32)},
  control:async(_id,action)=>snapshot={...snapshot,status:
   action==="resume"?"active":action==="finish"?"finished":"paused"},
  update:async body=>{
   actions.push(body);
   if(handler)return snapshot=await handler(body,snapshot);
   return snapshot={...snapshot,action_seq:snapshot.action_seq+1,
    basket_x:body.x,events:[]};
  },
  refresh:async()=>snapshot,
  fetchRecord:async()=>({personal_best:84,finished_runs:2}),
  onExit:()=>{},
 });
 return {runtime,actions,snapshot:()=>snapshot};
}
test("Catch shares the same scene and does not remove other arcade modes",()=>{
 assert.equal(typeof win.SnowfallArcadeV299.mountScene,"function");
 assert.equal(typeof win.SnowfallCatchV299d.mount,"function");
 assert.ok(html.indexOf("arcade-v299.js")<html.indexOf("arcade-catch-v299d.js"));
 assert.match(html,/arcade-catch-v299d\.js\?v=299g/);
 assert.match(html,/id="arcadeCatch"/);
 assert.match(css,/arcade-full-catch/);
 assert.match(css,/touch-action:none/);
 assert.match(app,/catch_v299d_enabled/);
 assert.match(app,/\/v1\/game\/arcade\/catch\/update/);
 assert.match(app,/\/v1\/game\/arcade\/gallery\/shot/);
 assert.match(app,/\/v1\/game\/arcade\/safecracker\/move/);
 assert.match(app,/\/v1\/game\/arcade\/snowman\/place/);
 assert.match(app,/\/v1\/game\/arcade\/move/); // classic choice-based Discord game
});
test("falling positions match the server's deterministic wind drift and timings",()=>{
 const item=schedule[0],position=win.SnowfallCatchV299d.position;
 const first=position(item,item.start),last=position(item,item.impact);
 assert.equal(first.y,38);
 assert.equal(last.y,300);
 assert.ok(Math.abs(first.x-300)<1e-6);
 assert.ok(Math.abs(last.x-340)<1e-6);
 assert.deepEqual(Array.from([win.SnowfallCatchV299d.wave(0),
  win.SnowfallCatchV299d.wave(25000),win.SnowfallCatchV299d.wave(51000)]),
 [1,2,3]);
});
test("pointer moves smooth basket, sends only coordinate and sequence to server",async()=>{
 now=100;const view=ui(),game=launch(view);
 assert.match(view.element.innerHTML,/Move left/);
 view.button("start");await drain();
 assert.equal(game.snapshot().status,"active");
 view.pointer("pointerdown",500);
 view.pointer("pointermove",560);
 view.frame(400);
 await drain();
 assert.equal(game.actions.length,1);
 assert.equal(game.actions[0].session_id,"a".repeat(32));
 assert.equal(game.actions[0].action_seq,0);
 assert.ok(game.actions[0].x>320&&game.actions[0].x<560);
 assert.equal(Object.hasOwn(game.actions[0],"score"),false);
 assert.equal(Object.hasOwn(game.actions[0],"caught"),false);
 assert.equal(game.runtime.getSnapshot().basket_x,game.actions[0].x);
 view.pointer("pointerup",560);
 game.runtime.dispose();
 assert.equal(view.stage.pointerdown,undefined);
});
test("keyboard directions and touchscreen-safe buttons shift the basket",async()=>{
 now=100;const view=ui(),game=launch(view);
 view.button("start");await drain();
 view.key("ArrowRight");
 view.button("right");
 view.frame(400);
 await drain();
 assert.equal(game.actions.length,1);
 assert.ok(game.actions[0].x>320);
 const old=game.runtime.getBasket();
 view.key("ArrowLeft",true);
 view.button("left");
 view.frame(700);
 await drain();
 assert.ok(game.runtime.getBasket()<old+85);
 game.runtime.dispose();
});
test("server catch and hazard outcomes are reflected, client never chooses them",async()=>{
 now=100;const view=ui();
 const game=launch(view,async(body,snapshot)=>({
  ...snapshot,action_seq:snapshot.action_seq+1,basket_x:body.x,
  caught:1,hazards:1,score:0,settled:[0],
  events:[{id:0,kind:"hazard",outcome:"hazard",
   feedback:"Icy shard! −12",score_after:0}],
 }));
 view.button("start");await drain();
 // Stationary baskets checkpoint every ~650ms, not every frame.
 view.frame(1000);await drain();
 assert.equal(game.runtime.getSnapshot().hazards,1);
 assert.equal(game.runtime.getSnapshot().score,0);
 assert.match(view.nodes.feedback.textContent,/Icy shard/);
 game.runtime.dispose();
});
