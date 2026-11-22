import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const js=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const css=readFileSync(path.join(root,"platform/static/app.css"),"utf8");
const nodes=new Map();
const el=id=>{
 if(!nodes.has(id)){
  const classes=new Set(["hidden"]),attrs=new Map();
  nodes.set(id,{dataset:{},style:{},textContent:"",alt:"",
   classList:{toggle:(key,on)=>on===undefined
       ?(classes.has(key)?(classes.delete(key),false):(classes.add(key),true))
       :(on?classes.add(key):classes.delete(key),!!on),
      add:key=>classes.add(key),remove:key=>classes.delete(key),
      contains:key=>classes.has(key)},
   getAttribute:key=>attrs.get(key),
   setAttribute:(key,value)=>attrs.set(key,value),
   removeAttribute:key=>attrs.delete(key)});
 }
 return nodes.get(id);
};
const ctx=vm.createContext({document:{addEventListener(){},getElementById:el},URL});
vm.runInContext(js,ctx);
const run=expr=>vm.runInContext(expr,ctx);

test("selected target sees only their real, validated equipment",()=>{
 const look={portrait:"frost_spectre",frame:"gold_frame",banner:"midnight_banner",gear:"scarf",trail:"candy_trail"};
 const resolved=run("profileLayers(rivalWardrobe("+JSON.stringify(look)+"))");
 for(const [slot,key] of Object.entries(look)){
  assert.equal(resolved[slot].key,key);
  assert.ok(existsSync(path.join(root,"graphics",resolved[slot].src.slice(1))),resolved[slot].src);
 }
 const fake=run('rivalWardrobe({frame:"https://outside.test/evil.png",portrait:"unknown",banner:"goggles",gear:"<img>",trail:"candy_trail"})');
 assert.equal(fake.equipped.frame,undefined);
 assert.equal(fake.equipped.banner,undefined);
 assert.equal(fake.equipped.portrait,undefined);
 assert.equal(fake.equipped.gear,undefined);
 assert.equal(fake.equipped.trail,"candy_trail");
});

test("rival changes update actual portrait, frame, trail and banner name",()=>{
 run('showRivalAppearance({player_id:"102",mr_username:"ActualRival",appearance:{portrait:"frost_spectre",frame:"gold_frame",banner:"midnight_banner",gear:"scarf",trail:"candy_trail"}})');
 assert.equal(el("rivalAppearance").classList.contains("hidden"),false);
 assert.equal(el("rivalEmpty").classList.contains("hidden"),true);
 assert.equal(el("rivalPortraitWell").dataset.trail,"candy_trail");
 assert.equal(el("rivalPortraitWell").classList.contains("has-frame"),true);
 assert.match(el("rivalPortrait").getAttribute("src"),/frost_spectre_m.webp$/);
 assert.match(el("rivalFrame").getAttribute("src"),/gold_frame.png$/);
 assert.equal(el("rivalBannerText").textContent,"ActualRival");
 assert.match(el("rivalVisualStatus").textContent,/Candy Cane Trail/);
 run('showRivalAppearance({player_id:"103",mr_username:"<script>Rival</script>",appearance:{}})');
 assert.equal(el("rivalPortraitWell").dataset.trail,"none");
 assert.equal(el("rivalPortraitWell").classList.contains("has-frame"),false);
 assert.equal(el("rivalFrame").getAttribute("src"),undefined);
 assert.equal(el("rivalBannerText").textContent,"<script>Rival</script>");
 assert.equal(el("rivalBannerText").innerHTML,undefined);
 assert.match(el("rivalVisualStatus").textContent,/Default recruit outfit/);
 run("showRivalAppearance(null)");
 assert.equal(el("rivalAppearance").classList.contains("hidden"),true);
 assert.equal(el("rivalEmpty").classList.contains("hidden"),false);
});

test("market equipped trail and combat throwing style stay visually separate",()=>{
 run('S.session={player_id:"101"};S.me={registered:true};S.shop={unlocked:["snow_trail","candy_trail"],equipped:{trail:"candy_trail"}};S.progress={inventory:{golden:0}};showSnowballLoadout("standard")');
 assert.equal(el("alleyLoadoutIcon").dataset.trail,"candy_trail");
 assert.match(el("alleyLoadoutTrail").getAttribute("src"),/candy_trail\.png$/);
 assert.equal(el("alleyLoadoutTrail").classList.contains("hidden"),false);
 assert.equal(el("alleyLoadoutIcon").dataset.style,"standard");
 assert.match(el("alleyLoadoutName").textContent,/Standard Throw/);
 assert.match(el("alleyLoadoutDetail").textContent,/Candy Cane Trail equipped/);
 run('showSnowballLoadout("golden")');
 assert.equal(el("alleyLoadoutIcon").dataset.style,"golden");
 assert.match(el("alleyLoadoutDetail").textContent,/required in inventory/);
 run('S.shop={unlocked:["snow_trail"],equipped:{trail:"candy_trail"}};showSnowballLoadout("power")');
 assert.equal(el("alleyLoadoutIcon").dataset.trail,"none"); // unowned: no cosmetic
 assert.equal(el("alleyLoadoutTrail").classList.contains("hidden"),true);
 assert.equal(el("alleyLoadoutTrail").getAttribute("src"),undefined);
 run('S.shop={unlocked:["snow_trail"],equipped:{trail:"snow_trail"}};showSnowballLoadout("quick")');
 assert.equal(el("alleyLoadoutIcon").dataset.trail,"snow_trail");
 assert.match(el("alleyLoadoutTrail").getAttribute("src"),/snow_trail\.png$/);
});

test("HQ and Market name banners sit directly above correctly fitted portrait",()=>{
 for(const prefix of ["hq","fit","rival"]){
  const name=prefix+"BannerWell",portrait=prefix+"PortraitWell";
  assert.equal([...html.matchAll(new RegExp('id="'+name+'"',"g"))].length,1);
  assert.equal([...html.matchAll(new RegExp('id="'+portrait+'"',"g"))].length,1);
  const well=html.indexOf('id="'+name+'"'),frame=html.indexOf('id="'+portrait+'"');
  assert.ok(well>0&&frame>well&&frame-well<400,prefix);
  assert.ok(html.includes('id="'+prefix+'BannerText"'));
  assert.ok(html.includes('id="'+prefix+'Snowball"'));
 }
 assert.ok(css.includes("left:10%;top:10%;width:80%;height:80%"));
 assert.ok(css.includes(".snowball-foreground"));
 assert.ok(css.includes("z-index:7"));
 assert.ok(css.includes("@media(max-width:700px)"));
 assert.match(html,/id="alleyLoadoutIcon"/);
 assert.match(html,/id="rivalAppearance"/);
 assert.match(html,/id="targetSelect"/);
});
