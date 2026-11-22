/* v2.9.6 visual helpers and browser asset contract. */
import assert from "node:assert/strict";
import {existsSync,readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const js=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const ctx=vm.createContext({document:{addEventListener:()=>{}},URL});
vm.runInContext(js,ctx);
const run=expr=>vm.runInContext(expr,ctx);

test("Snow Don portrait thresholds cover 100 to 0 without inventing health",()=>{
 assert.equal(run("bossArtTier(150,150)"),100);
 assert.equal(run("bossArtTier(76,150)"),60);
 assert.equal(run("bossArtTier(60,150)"),40);
 assert.equal(run("bossArtTier(1,150)"),10);
 assert.equal(run("bossArtTier(0,150)"),0);
 assert.equal(run("bossArtTier(0,0)"),100);
});
test("The Streets chat stays in-site and embeds only the configured genuine Discord channel",()=>{
 const ok="https://discord.com/channels/123456789012345678/234567890123456789";
 assert.equal(run("safeStreetsUrl("+JSON.stringify(ok)+")"),ok);
 for(const bad of ["javascript:alert(1)","https://evil.test/","https://discord.com.evil.test/channels/123456789012345678/234567890123456789"]){
  assert.equal(run("safeStreetsUrl("+JSON.stringify(bad)+")"),"");
 }
 assert.equal(run("streetsEmbedUrl("+JSON.stringify(ok)+")"),"https://e.widgetbot.io/channels/123456789012345678/234567890123456789");
 assert.equal(run('streetsEmbedUrl("https://evil.test/")'),"");
 assert.match(html,/id="streetsLink"[^>]*data-chat-open/);
 assert.match(html,/id="streetsTopLink"[^>]*data-chat-open/);
 assert.match(html,/id="streetsChatLauncher"/);
 assert.equal((html.match(/id="streetsChatFrame"/g)||[]).length,1);
 assert.match(html,/id="streetsChatFrame"[^>]*referrerpolicy="no-referrer"/);
 assert.doesNotMatch(html,/id="streetsLink"[^>]*target="_blank"/);
});
test("all static artwork used directly in page markup is committed",()=>{
 const refs=[...html.matchAll(/(?:src|href)="\/art\/([^"]+)"/g)].map(m=>m[1]);
 assert.ok(refs.length>=4);
 for(const asset of refs){
  assert.equal(existsSync(path.join(root,"graphics/art",asset)),true,asset);
 }
});
test("every cosmetic preview maps to an existing public asset",()=>{
 const map=run("COSMETIC_ART");
 for(const asset of Object.values(map)){
  assert.ok(asset.startsWith("/art/"),asset);
  assert.ok(existsSync(path.join(root,"graphics/art",asset.slice(5))),asset);
 }
});
