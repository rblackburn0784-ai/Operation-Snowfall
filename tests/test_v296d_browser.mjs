import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";
const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const source=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const nodes=new Map();
function node(id){
 if(!nodes.has(id))nodes.set(id,{dataset:{},style:{},classList:{toggle(){}},textContent:"",innerHTML:""});
 return nodes.get(id);
}
const ctx=vm.createContext({document:{addEventListener(){},getElementById:node},URL});
vm.runInContext(source,ctx);
const run=s=>vm.runInContext(s,ctx);
test("countdowns respect live, paused, missing and expired times",()=>{
 assert.equal(run('hqTimer("2026-12-01T12:01:05Z","live",Date.parse("2026-12-01T12:00:00Z"))'),"01m 05s");
 assert.equal(run('hqTimer(null,"paused",0)'),"Paused");
 assert.equal(run('hqTimer(null,"live",0)'),"—");
 assert.equal(run('hqTimer("2026-12-01T12:00:00Z","live",Date.parse("2026-12-01T12:00:01Z"))'),"Refresh due");
 assert.equal(run("hqPercent(500,300)"),100);
});
test("medals use committed art, escape names and do not render untrusted keys",()=>{
 for(const key of run("MEDALS"))assert.ok(existsSync(path.join(root,"graphics/art/v290/trophies/medals",key+".png")),key);
 assert.equal(run('hqMedal({key:"../../private"})'),"");
 assert.match(run('hqMedal({key:"first_flurry",badge:"<script>",rarity:"Common",unlocked:false,description:"test",progress:0,target:1})'),/&lt;script&gt;/);
});
test("private HQ ranks, title and medals clear when signed out",()=>{
 run('S.session={player_id:"42"};S.me={registered:true,phase:"live",day:4,resources:{snowballs:6,warmth:80}}; S.hq={registered:true,phase:"live",rank:3,title:"Snowball Rookie",daily_points:8,rarity:"Rare",caps:{snowballs:12,warmth:100,pvp:300},today_pvp:60,quests:[],trophies:[{key:"first_flurry",badge:"First Flurry",title:"Snowball Rookie",rarity:"Common",unlocked:true,progress:1,target:1}],records:{accuracy:54.5}};showHq()');
 assert.equal(node("hqRank").textContent,"#3");
 assert.equal(node("hqAmmoMeter").style.width,"50%");
 assert.match(node("hqFeatured").innerHTML,/First Flurry/);
 assert.match(node("hqRecordGrid").innerHTML,/54.5%/);
 run("S.session=null;S.me=null;S.hq=null;showHq()");
 assert.equal(node("hqRank").textContent,"—");
 assert.equal(node("hqFeatured").innerHTML,"");
 assert.equal(node("hqTrophyGrid").innerHTML,"");
});
test("HQ layout retains cosmetic layers, includes actual original artwork and unique IDs",()=>{
 for(const asset of ["v290/cosmetics/backgrounds/headquarters.webp","v290/trophies/backgrounds/trophy_cabinet.png","v290/cities/crests/chicago_crest.png"])assert.ok(existsSync(path.join(root,"graphics/art",asset)));
 for(const id of ["hqPortrait","hqFrame","hqBanner","hqGear","hqTrail","hqCityCrest","hqTrophyGrid","hqQuestList","hqRank","hqRecordGrid","heroBossArt","bossPortrait"])assert.equal([...html.matchAll(new RegExp('id="'+id+'"',"g"))].length,1,id);
});
