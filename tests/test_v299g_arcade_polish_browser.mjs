// v2.9.9g — shared arcade usability, reduced effects and safe controls.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const src=readFileSync(path.join(root,"arcade-v299.js"),"utf8");
const gallery=readFileSync(path.join(root,"arcade-gallery-v299a.js"),"utf8");
const safe=readFileSync(path.join(root,"arcade-safe-v299b.js"),"utf8");
const snowman=readFileSync(path.join(root,"arcade-snowman-v299c.js"),"utf8");
const catchJs=readFileSync(path.join(root,"arcade-catch-v299d.js"),"utf8");
const trivia=readFileSync(path.join(root,"arcade-trivia-v299e.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
let now=1000,reduced=false;
const req={current:null},win={
 requestAnimationFrame(cb){req.current=cb;return 1;},
 cancelAnimationFrame(){req.current=null},
 matchMedia:()=>({matches:reduced}),
 document:{hidden:false,addEventListener(){},removeEventListener(){}},
};
const sandbox={window:win,console,performance:{now:()=>now}};
vm.runInNewContext(src,sandbox);
function makeScene({showAim=false,guide=["Touch then tap", "Use arrows"],
 onShot,finish,draw}={}){
 const nodes={},listeners={},cssClasses=new Set();
 const element=()=>({dataset:{},textContent:"",disabled:false,attrs:{},
  setAttribute(k,v){this.attrs[k]=v},
  classList:{toggle(){},add(){},remove(){}},
 });
 const ctxCalls={fillRect:0};
 const ctx=new Proxy({},{
  get(_obj,key){
   if(key==="fillRect")return ()=>{ctxCalls.fillRect++};
   if(key==="createLinearGradient")return ()=>({addColorStop(){}});
   if(key==="measureText")return s=>({width:String(s).length*8});
   return ()=>{};
  },
  set(){return true},
 });
 const canvas={
  getContext:()=>ctx,
  getBoundingClientRect:()=>({left:0,top:0,width:640,height:360}),
  focus(){},setPointerCapture(){},
  addEventListener(name,fn){listeners[name]=fn},
  removeEventListener(name){delete listeners[name]},
 };
 const rootNode={
  innerHTML:"",classList:{
   add(name){cssClasses.add(name)},remove(name){cssClasses.delete(name)},
  },
  querySelector(sel){
   if(sel==="canvas")return canvas;
   if(sel===".arcade-training-feedback")return nodes.feedback??(nodes.feedback=element());
   const c=sel.match(/data-scene='([^']+)'/);
   if(c)return nodes[c[1]]??(nodes[c[1]]=element());
   const h=sel.match(/data-scene-label='([^']+)'/);
   if(h)return nodes[h[1]]??(nodes[h[1]]=element());
   throw Error("Unexpected selector "+sel);
  },
  addEventListener(name,fn){listeners[name]=fn},
  removeEventListener(name){delete listeners[name]},
 };
 let phase="paused",seconds=45,finishes=0,shots=[],renders=[];
 const api=win.SnowfallArcadeV299.mountScene({
  root:rootNode,title:"Arcade Test",guide,help:"Do not spend snowballs.",
  getStatus:()=>phase,getHud:()=>({time:seconds+"s",score:"0/100"}),
  draw:(ctx,opt)=>{renders.push(opt.reduced);draw?.(ctx,opt)},
  onStart:async()=>{phase="active"},
  onPause:async()=>{phase="paused"},
  onFinish:async()=>{phase="finished";finishes++;finish?.()},
  onExit:async()=>{},onShot:onShot?async args=>{
   shots.push(args);return onShot(args);
  }:undefined,
  onPointer:!onShot?()=>{}:undefined,
  showAim,
  extraActions:onShot?[{key:"throw",label:"Throw snowball"}]:[],
  hudFields:[{key:"time",initial:"45s"},{key:"score",initial:"0/100"}],
 });
 const button=name=>listeners.click({target:{
  closest:()=>({dataset:{scene:name},setAttribute(){} ,textContent:""}),
 }});
 const frame=value=>{now=value;assert.equal(typeof req.current,"function");req.current(value)};
 return {
  root:rootNode,api,nodes,listeners,classes:cssClasses,
  state:()=>phase,finishes:()=>finishes,shots,renders,ctxCalls,
  button,frame,setSeconds:s=>{seconds=s;api.update()},
 };
}
async function drain(){
 await new Promise(r=>setImmediate(r));
 await new Promise(r=>setImmediate(r));
}
test("all five games publish a keyboard/touch guide in the same screen",()=>{
 for(const [file,term] of [
  [gallery,"Mouse or touch"],[safe,"Keyboard:"],
  [snowman,"ghost outline"],[catchJs,"Home/End"],[trivia,"Backspace"],
 ])assert.match(file,new RegExp(term));
 assert.match(src,/arcade-scene-guide/);
 assert.match(src,/High contrast off/);
 assert.match(src,/Calm effects off/);
 assert.match(src,/aria-live='polite'/);
 assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
 assert.match(css,/arcade-high-contrast/);
 assert.match(html,/arcade-v299\.js\?v=299g/);
 assert.match(html,/arcade-gallery-v299a\.js\?v=299g/);
 assert.match(html,/arcade-safe-v299b\.js\?v=299g/);
 assert.match(html,/arcade-snowman-v299c\.js\?v=299g/);
 assert.match(html,/arcade-catch-v299d\.js\?v=299g/);
 assert.match(html,/arcade-trivia-v299e\.js\?v=299g/);
 assert.match(src,/server/);
});
test("shared guide is HTML escaped, with no executable injected markup",()=>{
 const view=makeScene({guide:["<img src=x onerror=alert(1)>","Tap & use keys"]});
 assert.match(view.root.innerHTML,/&lt;img src=x onerror=alert\(1\)&gt;/);
 assert.doesNotMatch(view.root.innerHTML,/<img src=x onerror=/);
 assert.match(view.root.innerHTML,/Tap &amp; use keys/);
 view.api.dispose();
});
test("calm effects and OS reduced motion both suppress decorative snowfall",async()=>{
 reduced=false;now=1000;
 const view=makeScene();
 view.button("start");await drain();
 view.frame(1400);
 assert.equal(view.renders.at(-1),false);
 assert.ok(view.ctxCalls.fillRect>0);
 const prior=view.ctxCalls.fillRect;
 view.button("effects");
 view.frame(1700);
 assert.equal(view.renders.at(-1),true);
 assert.equal(view.ctxCalls.fillRect,prior);
 reduced=true;
 view.button("effects"); // Turn full effects on but OS reduction overrides.
 view.frame(2100);
 assert.equal(view.renders.at(-1),true);
 assert.equal(view.ctxCalls.fillRect,prior);
 reduced=false;
 view.api.dispose();
});
test("contrast can be toggled without affecting game server state",async()=>{
 now=1000;
 const view=makeScene();
 const original=view.state();
 view.button("contrast");
 assert.ok(view.classes.has("arcade-high-contrast"));
 view.button("contrast");
 assert.ok(!view.classes.has("arcade-high-contrast"));
 assert.equal(view.state(),original);
 view.api.dispose();
});
test("End run now requires a second deliberate click, unlike Pause",async()=>{
 now=1000;
 const view=makeScene();
 view.button("start");await drain();
 assert.equal(view.state(),"active");
 view.button("finish");await drain();
 assert.equal(view.finishes(),0);
 assert.equal(view.state(),"active");
 assert.match(view.nodes.feedback.textContent,/End this run early/);
 view.button("finish");await drain();
 assert.equal(view.finishes(),1);
 assert.equal(view.state(),"finished");
 view.api.dispose();
});
test("Urgent last-ten-second status and paused/finished labels are server read only",async()=>{
 now=1000;
 const view=makeScene();
 view.button("start");await drain();
 view.setSeconds(9);
 assert.match(view.nodes.phase.textContent,/Ten seconds/);
 view.setSeconds(4);
 assert.match(view.nodes.phase.textContent,/Last five seconds/);
 view.button("pause");await drain();
 assert.match(view.nodes.phase.textContent,/Paused safely/);
 view.api.dispose();
});
test("touch-friendly Throw action submits a coordinate, never a local score",async()=>{
 now=1000;
 const view=makeScene({onShot:async()=>({outcome:"hit",feedback:"Practice hit!"})});
 view.button("start");await drain();
 view.button("throw");await drain();
 assert.equal(view.shots.length,1);
 assert.deepEqual(JSON.parse(JSON.stringify(view.shots)),[{x:320,y:182}]);
 assert.equal("score" in view.shots[0],false);
 assert.match(view.nodes.feedback.textContent,/Practice hit/);
 view.api.dispose();
});
test("Safecracker offers touch buttons for both turn directions",()=>{
 assert.match(safe,/key:"cw",label:"↻ Clockwise \+4"/);
 assert.match(safe,/key:"ccw",label:"↺ Anticlockwise −4"/);
 assert.match(safe,/action\("turn",4\)/);
 assert.match(safe,/action\("turn",-4\)/);
 assert.match(gallery,/key:"throw",label:"Throw snowball"/);
});
