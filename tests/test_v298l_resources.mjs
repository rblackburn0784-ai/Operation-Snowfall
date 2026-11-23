import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const css=readFileSync(path.join(root,"platform/static/app.css"),"utf8");
const js=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const nodes=new Map();
const node=id=>{
 if(!nodes.has(id)){
  const attrs=new Map(),states=new Set();
  nodes.set(id,{id,dataset:{},textContent:"",innerHTML:"",
   setAttribute:(k,v)=>attrs.set(k,String(v)),
   getAttribute:k=>attrs.get(k),removeAttribute:k=>attrs.delete(k),
   classList:{add:k=>states.add(k),remove:k=>states.delete(k),contains:k=>states.has(k)}});
 }
 return nodes.get(id);
};
const ctx=vm.createContext({document:{getElementById:node,addEventListener(){}},URL});
vm.runInContext(js,ctx);
const run=expr=>vm.runInContext(expr,ctx);
const stages=(key,values)=>values.map(value=>run("resourceStage("+JSON.stringify(key)+","+JSON.stringify(value)+")"));

test("stage thresholds respect the real game limits, including zero",()=>{
 assert.deepEqual(stages("snowballs",[0,2,3,5,6,9,10,12]),[1,1,2,2,3,3,4,4]);
 assert.deepEqual(stages("warmth",[100,75,74,50,49,25,24,0]),[1,1,2,2,3,3,4,4]);
 assert.deepEqual(stages("cold",[100,75,74,50,49,25,24,0]),[1,1,2,2,3,3,4,4]);
 assert.deepEqual(stages("currency",[0,24,25,74,75,149,150]),[1,1,2,2,3,3,4]);
 assert.deepEqual(stages("points",[0,99,100,299,300,599,600]),[1,1,2,2,3,3,4]);
 for(const v of ["",null,-1,"not-a-number",undefined])assert.equal(run("resourceStage('warmth',"+JSON.stringify(v??null)+")"),null);
 assert.equal(run("resourceStage('invented',55)"),null);
});
test("all 21 user-supplied artworks are genuine webp files under static /art",()=>{
 for(const kind of ["snowballs","warmth","cold","points","currency"]){
  for(let stage=1;stage<=4;stage++){
   const url=run("resourceArtUrl("+JSON.stringify(kind)+","+JSON.stringify(kind==="warmth"||kind==="cold"?[95,65,32,5][stage-1]:kind==="snowballs"?[1,4,7,12][stage-1]:kind==="currency"?[5,35,85,170][stage-1]:[12,175,320,800][stage-1])+")");
   const file=path.join(root,"graphics",url.slice(1));
   assert.ok(existsSync(file),file);
   const bytes=readFileSync(file);
   assert.equal(bytes.toString("ascii",0,4),"RIFF");
   assert.equal(bytes.toString("ascii",8,12),"WEBP");
   assert.ok(bytes.length>3000,file);
  }
 }
 const street=path.join(root,"graphics/art/v290/status/v298l/winter_street.webp");
 assert.ok(existsSync(street));
 assert.equal(readFileSync(street).toString("ascii",8,12),"WEBP");
});
test("resource data drives real images; unknown readings hide rather than invent",()=>{
 run("showResourceArtwork({snowballs:12,warmth:15,snowflakes:170},800)");
 assert.match(node("hqAmmoArt").getAttribute("src"),/snowballs_4\.webp$/);
 assert.match(node("hqWarmthArt").getAttribute("src"),/warmth_4\.webp$/);
 assert.match(node("hqColdArt").getAttribute("src"),/cold_4\.webp$/);
 assert.match(node("marketCurrencyArt").getAttribute("src"),/currency_4\.webp$/);
 // Headquarters uses the requested swapped art, not swapped resource values.
 assert.match(node("hqCurrencyArt").getAttribute("src"),/points_4\.webp$/);
 assert.match(node("hqPointsArt").getAttribute("src"),/currency_4\.webp$/);
 assert.match(node("playPointsArt").getAttribute("src"),/points_4\.webp$/);
 assert.match(node("alleyAmmoArt").getAttribute("src"),/snowballs_4\.webp$/);
 assert.match(node("hqColdLabel").textContent,/Freezing/);
 assert.equal(node("alleyAmmoCount").textContent,"12");
 assert.match(node("alleyWarmthCount").textContent,/15 \/ 100/);
 run("showResourceArtwork({snowballs:0,warmth:98,snowflakes:0},0)");
 assert.equal(node("hqAmmoArt").dataset.empty,"true");
 assert.match(node("hqColdLabel").textContent,/Comfortable/);
 assert.match(node("hqWarmthArt").getAttribute("src"),/warmth_1\.webp$/);
 run("showResourceArtwork({},null)");
 assert.equal(node("hqWarmthArt").classList.contains("hidden"),true);
 assert.equal(node("hqWarmthArt").getAttribute("src"),undefined);
 assert.equal(node("alleyAmmoCount").textContent,"—");
});
test("scoreboard shows stage imagery and exact shared points",()=>{
 run('S.board=[{mr_username:"TestRival",city:"New York",score:320}];showBoard()');
 const markup=node("leaderboard").innerHTML;
 assert.match(markup,/points_3\.webp/);
 assert.match(markup,/320 pts/);
 assert.match(markup,/TestRival/);
});
test("all resource cards retain numeric values and original required controls",()=>{
 for(const id of ["ammoValue","warmthValue","flakeValue","scoreValue","shopBalance",
    "hqAmmoMeter","hqWarmthMeter","throwButton","targetSelect","alleyLoadout",
    "hqAmmoArt","hqWarmthArt","hqColdArt","hqCurrencyArt","hqPointsArt",
    "marketCurrencyArt","alleyAmmoArt","alleyColdArt","playAmmoArt","playWarmthArt",
    "playFlakesArt","playPointsArt","alleyAmmoCount","alleyWarmthCount","hqColdLabel"]){
   assert.ok(html.includes('id="'+id+'"'),"missing "+id);
 }
 assert.match(html,/alley-winter-scene/);
 assert.match(css,/url\("\/art\/v290\/status\/v298l\/winter_street\.webp"\)/);
 assert.match(css,/@media\(max-width:380px\)/);
 assert.match(html,/snowfall-web-release" content="2\.9\.8l"/);
 assert.match(html,/app\.css\?v=298l/);
 assert.match(html,/app\.js\?v=298l/);
});
