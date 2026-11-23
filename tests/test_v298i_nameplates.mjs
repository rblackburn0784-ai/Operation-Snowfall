import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const css=readFileSync(path.join(root,"app.css"),"utf8");
const js=readFileSync(path.join(root,"app.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");

test("nameplate uses only the chosen banner artwork without a second box",()=>{
 const start=css.indexOf("/* v2.9.8i:");
 assert.ok(start>0);
 const portion=css.slice(start,css.indexOf("#hqPortraitWell",start));
 assert.match(portion,/background:transparent;border:0;border-radius:0;/);
 assert.match(portion,/box-shadow:none;overflow:visible/);
 assert.match(portion,/\.collector-banner-well::before,\.collector-banner-well::after\{content:none\}/);
 assert.match(portion,/object-fit:contain/);
 assert.match(portion,/filter:none/);
 for(const prefix of ["hq","fit","rival"]){
  assert.equal([...html.matchAll(new RegExp('id="'+prefix+'BannerWell"',"g"))].length,1);
  assert.ok(html.includes('id="'+prefix+'BannerText"'));
  assert.ok(html.includes('id="'+prefix+'Banner"'));
 }
});

test("names never wrap and resize is handled across all three previews",()=>{
 const start=css.indexOf("/* v2.9.8i:");
 const portion=css.slice(start,css.indexOf("#hqPortraitWell",start));
 assert.match(portion,/white-space:nowrap;overflow-wrap:normal;word-break:normal/);
 assert.match(js,/function fitVisibleBannerNames\(\)/);
 assert.match(js,/requestAnimationFrame\(fitVisibleBannerNames\)/);
 assert.match(js,/fitBannerName\(prefix\)/);
 assert.match(js,/fitVisibleBannerNames\(\);/);
});

test("long usernames shrink to their measured width and refit on resize",()=>{
 let available=130;
 const text={style:{fontSize:"",overflow:"",transform:""},textContent:"TheSnowman"};
 Object.defineProperty(text,"clientWidth",{get:()=>available});
 Object.defineProperty(text,"scrollWidth",{get:()=>{
   // Emulate real DOM glyph reflow using the currently applied font size.
   const font=parseFloat(text.style.fontSize)||20;
   return Math.ceil(190*font/20);
 }});
 const context=vm.createContext({
  document:{addEventListener(){},getElementById:id=>id==="rivalBannerText"?text:null},
  window:{getComputedStyle:()=>({fontSize:"20px"})},URL
 });
 vm.runInContext(js,context);
 const run=expression=>vm.runInContext(expression,context);
 run('fitBannerName("rival")');
 assert.ok(parseFloat(text.style.fontSize)<20);
 assert.ok(text.scrollWidth<=available+1);
 available=55;
 run('fitBannerName("rival")');
 assert.ok(parseFloat(text.style.fontSize)<=8);
 assert.match(text.style.transform,/^scaleX\(/);
 // CSS now uses intrinsic text width; no inline overflow clipping is needed.
 assert.equal(text.style.overflow,"");
 assert.match(css,/overflow:visible;text-overflow:initial/);
 available=190;
 run('fitBannerName("rival")');
 assert.equal(text.style.fontSize,"");
 assert.equal(text.style.transform,"");
});

test("the snapshot label renders text, never player-supplied HTML",()=>{
 assert.match(js,/txt\(prefix\+"BannerText",displayName\)/);
 assert.doesNotMatch(js,/innerHTML\s*=\s*displayName/);
 assert.match(html,/snowfall-web-release" content="2\.9\.8k"/);
 assert.match(html,/app\.css\?v=298k/);
 assert.match(html,/app\.js\?v=298k/);
});
