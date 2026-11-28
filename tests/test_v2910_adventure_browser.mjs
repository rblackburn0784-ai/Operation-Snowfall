import {readFileSync} from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";

const root="src/snowfall/platform/static/";
const app=readFileSync(root+"app.js","utf8");
const html=readFileSync(root+"index.html","utf8");
const css=readFileSync(root+"app.css","utf8");
const start=app.indexOf("function adventureButton(");
const end=app.indexOf("/* v2.9.8a",start);
function renderer(){
 const node={dataset:{},innerHTML:"",contains:()=>false,querySelectorAll:()=>[]};
 const context={el:id=>id==="adventureContent"?node:null,document:{activeElement:null},
   esc:v=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll("'","&#39;").replaceAll('"',"&quot;")};
 vm.createContext(context);
 vm.runInContext(app.slice(start,end),context);
 return {node,render:context.showAdventure};
}
const scene={key:"office",title:"Office",description:"Find the dispatch",
 hotspots:[{key:"drawer",label:"Desk drawer",x:43,y:75}]};
const state={title:"The dispatch",scene,phase:"live",message:"Search",complete:false,
 inventory:[],evidence:[],dialogue:null};
test("adventure panel and bundled artwork are present, touch and keyboard accessible",()=>{
 assert.match(html,/snowfall-adventure-release" content="2\.9\.10"/);
 assert.match(html,/id="adventureContent"/);
 for(const name of ["office","alley"])assert.match(readFileSync(root+"adventure-"+name+".svg","utf8"),/viewBox="0 0 960 540"/);
 assert.match(css,/\.adventure-hotspot\{[^}]*width:44px;height:44px/);
 assert.match(css,/\.adventure-dossier\{grid-template-columns:1fr\}/);
 assert.ok(app.includes('"/v1/game/adventure/action"'));
});
test("scene renders actual hotspots and accessible action buttons, escapes text",()=>{
 const {node,render}=renderer();
 render({...state,message:"<script>unsafe</script>"},false);
 assert.match(node.innerHTML,/class='adventure-hotspot'/);
 assert.match(node.innerHTML,/left:43%;top:75%/);
 assert.match(node.innerHTML,/aria-label='Inspect Desk drawer'/);
 assert.match(node.innerHTML,/1\. Desk drawer/);
 assert.match(node.innerHTML,/&lt;script&gt;/);
 assert.doesNotMatch(node.innerHTML,/<script>/);
 assert.match(node.innerHTML,/Nothing collected yet/);
});
test("dialogue gates scene actions, completed and offline views disable input",()=>{
 const {node,render}=renderer();
 render({...state,dialogue:{speaker:"Courier",text:"Hello",choices:[{key:"leave",label:"Leave"}]}},false);
 assert.match(node.innerHTML,/data-adventure='choose' data-target='leave'>Leave/);
 assert.match(node.innerHTML,/class='adventure-hotspot'[^>]* disabled>/);
 render({...state,phase:"closed"},false);
 assert.match(node.innerHTML,/data-target='drawer' disabled>/);
 render({...state,complete:true,souvenir:"Detective"},false);
 assert.match(node.innerHTML,/Case complete/);
 assert.match(node.innerHTML,/Collectible earned: Detective/);
 assert.doesNotMatch(node.innerHTML,/aria-label='Accessible scene objects'/);
 render(null,false);
 assert.doesNotMatch(node.innerHTML,/Detective/);
});