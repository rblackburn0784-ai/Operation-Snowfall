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
const ctx=vm.createContext({document:{addEventListener(){}},URL});
vm.runInContext(js,ctx);
const run=s=>vm.runInContext(s,ctx);
test("daily defeat never ends season; pause, closed and finalized are distinct",()=>{
 assert.equal(run('eventPresentation({phase:"live"},{state:"defeated"}).kind'),"raid");
 assert.equal(run('eventPresentation({phase:"live"},{state:"healthy"}).kind'),"normal");
 assert.equal(run('eventPresentation({phase:"live",current_day:2},{state:"defeated",day:1}).kind'),"normal");
 assert.equal(run('eventPresentation({phase:"live"},{state:"defeated"},true).kind'),"normal");
 assert.equal(run('eventPresentation({phase:"closed"},{state:"healthy"}).kind'),"closed");
 assert.equal(run('eventPresentation({phase:"finalized"},{state:"defeated"}).kind'),"finalized");
 assert.equal(run('eventPresentation({phase:"paused"},{state:"defeated"}).kind'),"paused");
});
test("newspaper headlines are escaped and original assets exist",()=>{
 assert.match(run('wireHeadlineMarkup({category:"Combat",title:"<script>",detail:"<img>"})'),/&lt;script&gt;/);
 for(const file of ["wire/backgrounds/final_day_edition.png","wire/backgrounds/front_page_template.png","wire/backgrounds/newsroom_editorial.png","wire/banners/snowfall_wire_masthead.png","wire/banners/breaking_news.png","boss/raid_celebration.webp","boss/victory_screen.webp"])assert.ok(existsSync(path.join(root,"graphics/art/v290",file)),file);
 for(const id of ["page-wire","wireDay","wirePaper","wireHeadlines","eventFinale","eventRetry","atmosphereToggle","raidCelebration","heroBossArt","cityMapOverlay","fitPortrait","hqPortrait"])assert.equal([...html.matchAll(new RegExp('id="'+id+'"',"g"))].length,1,id);
 assert.match(css,/prefers-reduced-motion:reduce/);
 assert.match(css,/data-atmosphere="off"/);
});

test("four newspaper boxes are stable even with missing or unordered data",()=>{
 assert.equal(run('JSON.stringify(wireSlots([{key:"community",title:"C"},{key:"streets",title:"S"},{key:"lead",title:"L"}]).map(h=>h.key))'),'["streets","boss","cities","community"]');
 assert.equal(run('wireSlots([]).length'),4);
 assert.equal(run('wireSlots([{key:"boss",title:"B"}])[1].title'),"B");
 assert.equal(run('wireSlots([])[0].title'),"Awaiting dispatch");
});
