"""Web-only visual layout checks for the requested Resource Card Layout Fixes."""
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const html=readFileSync(path.join(root,"index.html"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
const js=readFileSync(path.join(root,"app.js"),"utf8");
const hq=html.slice(html.indexOf('id="playerDashboard"'),html.indexOf('class="hq-next"'));

test("snowflakes show crystal art, points show gold tokens; values retain their IDs",()=>{
 const left=hq.indexOf('id="hqCurrencyArt"');
 const right=hq.indexOf('id="hqPointsArt"');
 assert.ok(left>0&&right>left);
 assert.match(hq,/id="hqCurrencyArt"[^>]+points_1\.webp/);
 assert.match(hq,/id="hqPointsArt"[^>]+currency_1\.webp/);
 assert.ok(hq.includes('id="flakeValue"'));
 assert.ok(hq.includes('id="scoreValue"'));
 assert.match(js,/\["hqCurrencyArt","points",r\.snowflakes,"currency"\]/);
 assert.match(js,/\["hqPointsArt","currency",score,"points"\]/);
 assert.match(js,/\["marketCurrencyArt","currency",r\.snowflakes\]/);
 assert.match(js,/\["playPointsArt","points",score\]/);
});

test("thermometer is at the bottom of warmth card, replacing the old visible bar",()=>{
 const start=hq.indexOf('class="stat resource-stat resource-warmth-stat"');
 const end=hq.indexOf('id="hqCurrencyArt"',start);
 const warm=hq.slice(start,end);
 const index=id=>warm.indexOf('id="'+id+'"');
 const order=["hqColdArt","warmthValue","hqColdLabel","hqWarmthSub","hqWarmthArt","hqWarmthMeter"].map(index);
 assert.ok(order.every(x=>x>=0),"warmth IDs must remain wired");
 assert.ok(order.every((x,i)=>i===0||x>order[i-1]),"thermometer sits after the text at bottom");
 assert.equal((warm.match(/id="hqWarmthArt"/g)||[]).length,1);
 assert.match(warm,/class="hq-meter warmth-meter"><img id="hqWarmthArt"/);
 assert.match(css,/\.resource-warmth-stat \.warmth-meter>span\{display:none\}/);
 assert.match(css,/\.resource-warmth-stat \.warmth-meter \.resource-warmth-bar/);
 assert.match(js,/el\("hqWarmthMeter"\)\.style\.width/);
});

test("snowball stockpile moves down without clipping or changing inventory",()=>{
 assert.match(hq,/class="stat resource-stat resource-ammo-stat"/);
 assert.match(css,/\.resource-ammo-stat \.resource-art-ammo\{[^}]*margin-top:clamp\(10px,1\.2vw,16px\)/);
 assert.match(css,/\.resource-ammo-stat \.resource-art-ammo\{[^}]*object-position:left bottom/);
 assert.match(css,/@media\(max-width:640px\)/);
 assert.match(css,/@media\(max-width:380px\)/);
 assert.match(hq,/id="hqAmmoArt"/);
 assert.match(hq,/id="ammoValue"/);
 assert.match(hq,/id="hqAmmoMeter"/);
 assert.match(js,/\["hqAmmoArt","snowballs",r\.snowballs\]/);
});

test("original styling changes are not applied to unrelated progress displays",()=>{
 assert.match(hq,/id="hqPvpMeter"/);
 assert.match(hq,/id="hqAmmoMeter"/);
 assert.match(css,/#playerDashboard \.resource-warmth-stat \.warmth-meter/);
 assert.doesNotMatch(css,/(^|\n)\.hq-meter\s*\{display:none/);
 assert.match(html,/app\.css\?v=298l-r2/);
 assert.match(html,/app\.js\?v=298l-r2/);
});
