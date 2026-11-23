// v2.9.9: isolated browser mini-game core, input and server-checkpoint smoke.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const dir=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const source=readFileSync(path.join(dir,"arcade-v299.js"),"utf8");
const app=readFileSync(path.join(dir,"app.js"),"utf8");
const html=readFileSync(path.join(dir,"index.html"),"utf8");
const css=readFileSync(path.join(dir,"app.css"),"utf8");
const window={
 requestAnimationFrame:()=>1,cancelAnimationFrame(){},
 matchMedia:()=>({matches:false}),
 document:{addEventListener(){},removeEventListener(){}}
};
vm.runInNewContext(source,{window,console});

function setup(){
 const events={},stageEvents={},labels={};
 const node=()=>({textContent:"",disabled:false,attributes:{},dataset:{},
  setAttribute(k,v){this.attributes[k]=v},focus(){}});
 const canvas={events:stageEvents,getContext:()=>({}),getBoundingClientRect:()=>({left:0,top:0,width:640,height:360}),
  setPointerCapture(){},addEventListener(k,fn){stageEvents[k]=fn},
  removeEventListener(k){delete stageEvents[k]},focus(){}};
 const control={play:node(),pause:node(),sound:node(),finish:node(),exit:node()};
 const root={
  innerHTML:"",classList:{remove(){},add(){}},querySelector(selector){
   if(selector==="canvas")return canvas;
   const label=selector.match(/data-training-label="(.+?)"/);
   if(label)return labels[label[1]]??(labels[label[1]]=node());
   const key=selector.match(/data-training='(.+?)'/);
   if(key)return control[key[1]];
   if(selector===".arcade-training-feedback")return labels.feedback??(labels.feedback=node());
   throw Error("Unexpected selector "+selector);
  },
  addEventListener(k,fn){events[k]=fn},removeEventListener(k){delete events[k]}
 };
 function press(action){
  assert.equal(typeof events.click,"function");
  events.click({target:{closest:()=>({dataset:{training:action}})}});
 }
 const session={mode:"gallery",session_id:"a".repeat(32),revision:0,status:"active",
  duration_ms:60000,state:{elapsed_ms:0,hits:0,misses:0,progress:0,position:.5,angle:0}};
 return {root,events,stageEvents,press,session};
}
test("five modes share one canvas component, never touch legacy Discord actions",()=>{
 assert.deepEqual(Array.from(window.SnowfallArcadeV299.modes),
  ["gallery","safe","snowman","catch","trivia"]);
 assert.match(source,/requestAnimationFrame/);
 assert.match(source,/pointerdown/);
 assert.match(source,/keydown/);
 assert.match(source,/AudioContext/);
 assert.match(source,/visibilitychange/);
 assert.match(app,/\/v1\/game\/arcade\/practice\/start/);
 assert.match(app,/\/v1\/game\/arcade\/practice\/save/);
 assert.match(app,/\/v1\/game\/arcade\/move/); // still classic
 assert.match(html,/id="arcadePractice"/);
 assert.match(html,/arcade-v299\.js\?v=299/);
 assert.match(css,/touch-action:none/);
});
test("touch click produces checkpoint with server revision, not a shared score",async()=>{
 const ui=setup();const writes=[];
 const runtime=window.SnowfallArcadeV299.mount({
  root:ui.root,session:ui.session,
  save:async data=>{writes.push(data);return {...ui.session,revision:writes.length,status:"active"}}
 });
 ui.press("play");
 assert.ok(ui.stageEvents.pointerdown);
 ui.stageEvents.pointerdown({clientX:200,clientY:160,pointerId:1,preventDefault(){}});
 assert.equal(await runtime.save(),true);
 assert.equal(writes.length,1);
 assert.equal(writes[0].state.hits,1);
 assert.equal(writes[0].revision,0);
 assert.equal(Object.hasOwn(writes[0],"score"),false);
 runtime.dispose();
 assert.equal(ui.stageEvents.pointerdown,undefined);
});
test("each drill mounts the same runtime without writing to the Discord engine",()=>{
 for(const mode of window.SnowfallArcadeV299.modes){
  const ui=setup();ui.session.mode=mode;
  const runtime=window.SnowfallArcadeV299.mount({
   root:ui.root,session:ui.session,save:async()=>ui.session
  });
  assert.ok(ui.root.innerHTML.includes("PRACTICE PREVIEW"));
  runtime.dispose();
 }
});
