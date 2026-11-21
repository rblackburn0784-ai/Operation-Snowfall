import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";
import path from "node:path";
import {fileURLToPath} from "node:url";
const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const js=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const ctx=vm.createContext({document:{addEventListener:()=>{}},URL});
vm.runInContext(js,ctx);
const layers=wardrobe=>vm.runInContext("profileLayers("+JSON.stringify(wardrobe)+")",ctx);
test("only owned, equipped, correct-slot cosmetics appear in player HQ",()=>{
 const q=layers({unlocked:["gold_frame","frost_spectre_f","scarf","aurora_banner","candy_trail"],
 equipped:{frame:"gold_frame",portrait:"frost_spectre_f",gear:"scarf",banner:"aurora_banner",trail:"candy_trail"}});
 for(const [slot,entry] of Object.entries(q)){
  assert.ok(entry.key,slot);assert.ok(existsSync(path.join(root,"graphics/art",entry.src.slice(5))),entry.src);
 }
 assert.match(q.portrait.src,/frost_spectre_f\.webp$/);
});
test("purchased only, unknown, mismatched, unowned, and logged-out cosmetics never appear",()=>{
 const q=layers({unlocked:["gold_frame","scarf","winter_enforcer"],equipped:{frame:"holly_frame",banner:"gold_frame",gear:"https://evil.test/x",portrait:"recruit_f"}});
 assert.equal(q.frame.src,null);assert.equal(q.banner.src,null);assert.equal(q.gear.src,null);
 assert.equal(q.portrait.src,"/art/v290/portraits/recruit_m.webp");
 assert.equal(layers(null).frame.src,null);
});
test("equipping a different owned frame changes the image without purchasing again",()=>{
 const unlocked=["gold_frame","ice_frame"];
 assert.match(layers({unlocked,equipped:{frame:"gold_frame"}}).frame.src,/gold_frame\.png$/);
 assert.match(layers({unlocked,equipped:{frame:"ice_frame"}}).frame.src,/ice_frame\.png$/);
});
test("branding and collector controls are present and account tools remain accessible",()=>{
 for(const id of ["brandIcon","siteBanner","hqPortrait","hqFrame","hqBanner","hqGear","hqTrail","accountTools","crossPlatformPanel","linkDiscord","refreshShared"])assert.ok(html.includes('id="'+id+'"'),id);
 assert.ok(html.includes('width="2048" height="682"'));
 assert.ok(html.includes('data-nav="shop">Edit appearance'));
});

test("v2.9.6b header branding does not displace the original Snow Don splash",()=>{
 const header=html.split("</header>")[0],main=html.split("</header>")[1];
 assert.ok(header.includes('id="siteBanner"'));
 assert.ok(header.includes('id="brandIcon"'));
 assert.ok(!main.includes('id="siteBanner"'));
 assert.ok(main.includes('src="/art/v290/boss/phase_ice.webp"'));
 assert.ok(main.includes('THE COLD<br><em>NEVER</em>'));
 assert.ok(main.includes('id="hqPortraitWell"'));
 const css=readFileSync(path.join(root,"platform/static/app.css"),"utf8");
 assert.match(css,/\.portrait-well\{aspect-ratio:1;overflow:hidden/);
 assert.match(css,/\.collector-profile\{width:100%;max-width:340px/);
});
