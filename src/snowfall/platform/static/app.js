/* Operation Snowfall v2.9.4d — verified Discord character replacement. */
"use strict";
const S={session:null,me:null,world:null,raid:null,shop:null,items:[],board:[],cities:[],targets:[],config:null,progress:null,discard:null,busy:false};
const el=id=>document.getElementById(id);
const txt=(id,v)=>{if(el(id))el(id).textContent=v==null?"—":String(v)};
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=v=>Number(v??0).toLocaleString("en-GB");
let timer;
function notice(message,kind){
 const node=el("toast");node.textContent=String(message);node.className="toast "+(kind||"");
 clearTimeout(timer);timer=setTimeout(()=>node.classList.add("hidden"),5500);
}
async function request(path,method,body,mutation,unique){
 const headers={"Accept":"application/json"};
 if(body!==undefined)headers["Content-Type"]="application/json";
 if(mutation)headers["X-Snowfall-CSRF"]=S.session?.csrf||"";
 if(unique)headers["Idempotency-Key"]="web-ui-"+(crypto.randomUUID?crypto.randomUUID():String(Date.now())+"-"+Math.random()).replace(/[^A-Za-z0-9_-]/g,"");
 let response;
 try{response=await fetch(path,{method:method||"GET",headers,credentials:"same-origin",cache:"no-store",body:body===undefined?undefined:JSON.stringify(body)})}
 catch{throw Error("Cannot reach the staging server.")}
 let data={};try{data=await response.json()}catch{}
 if(!response.ok){let e=Error(typeof data.detail==="string"?data.detail:"Request failed ("+response.status+")");e.status=response.status;throw e}
 return data;
}
const get=path=>request(path);
const post=(path,body,mutate,unique)=>request(path,"POST",body,mutate,unique);
function section(name){
 if(!["home","combat","boss","shop","cities"].includes(name))name="home";
 document.querySelectorAll(".panel").forEach(n=>n.classList.toggle("active",n.id==="page-"+name));
 document.querySelectorAll(".nav-item").forEach(n=>n.classList.toggle("active",n.dataset.nav===name));
 if(name==="shop")showShop();
 if(name==="cities"){showCities();showBoard()}
 if(name==="boss")showBoss();
 window.scrollTo({top:document.querySelector(".page-grid").offsetTop,behavior:"smooth"});
}
function authModal(){if(S.session)return notice("Already signed in.","success");el("authDialog").classList.remove("hidden")}
function closeAuth(){el("authDialog").classList.add("hidden")}
function showMe(){
 const signed=!!S.session;
 el("authToggle").textContent=signed?"Sign out":"Sign in";
 txt("identityStatus",signed?"Signed in":"Guest");
 el("loggedOutNotice").classList.toggle("hidden",signed);
 el("registration").classList.toggle("hidden",!signed||!!S.me?.registered);
 el("playerDashboard").classList.toggle("hidden",!signed||!S.me?.registered);
 el("linkedIdentity").classList.toggle("hidden",!signed);
 if(!signed||S.session?.links?.some(x=>x.provider==="discord")){
   el("discordDiscardPanel").classList.add("hidden");S.discard=null;
 }
 const links=S.session?.links||[];
 const hasDiscord=links.some(x=>x.provider==="discord");
 const hasUnderworld=links.some(x=>x.provider==="underworld");
 txt("canonicalPlayerId",S.session?.player_id);
 txt("providerStatus",(hasUnderworld?"Underworld connected":"Underworld not linked")+
     " · "+(hasDiscord?"Discord connected":"Discord not linked"));
 el("linkDiscord").disabled=hasDiscord||!S.config?.discord_oauth;
 el("linkDiscord").textContent=hasDiscord?"✓ Discord linked":S.config?.discord_oauth?
      "Link Discord account":"Discord linking not configured";
 if(!S.me?.registered){
   txt("progressSummary","Register this character to compare your official game progress.");
   return;
 }
 renderProgress();
 txt("welcomeName",S.me.mr_username);txt("welcomeCity",S.me.city+" · Day "+(S.me.day||"—"));
 txt("ammoValue",S.me.resources?.snowballs);txt("warmthValue",S.me.resources?.warmth);
 txt("flakeValue",S.me.resources?.snowflakes);txt("scoreValue",fmt(S.me.score));
 txt("shopBalance",fmt(S.me.resources?.snowflakes));
 txt("ammoSub",S.me.resources?.next_snowball_at?"Regenerating snowballs":"Ready for action");
 txt("phaseValue",S.me.phase.toUpperCase());txt("sideStatus",S.me.phase.toUpperCase());
 txt("sideStatusDetail","Day "+(S.me.day||"—")+" of 7 · "+S.me.city);
}
function renderProgress(){
 const p=S.progress;
 if(!p?.registered){txt("progressSummary","Loading official shared progress…");return}
 txt("progressSummary","Official score: "+fmt(p.score)+" · "+fmt(p.snowballs)+
     " snowballs · "+fmt(p.snowflakes)+" snowflakes · Snow Don "+
     fmt(p.boss_hp)+"/"+fmt(p.boss_max_hp)+" HP.");
}
function showBoss(){
 let max=Number(S.world?.boss_max_hp??S.raid?.max_hp??0), hp=Number(S.world?.boss_hp??S.raid?.remaining_hp??0);
 txt("bossHeadline",max&&hp===0?"The Snow Don has fallen!":"The Snow Don lives.");
 txt("bossHpText",fmt(hp)+" / "+fmt(max)+" HP");
 txt("bossPhase",max?Math.round((1-hp/max)*100)+"% damage taken":"Raid not started");
 el("bossHpBar").style.width=max?Math.max(0,Math.min(100,100*hp/max))+"%":"0%";
 txt("raidSummary",S.raid?fmt(S.raid.shared_hits)+" hits · "+fmt(S.raid.contributors)+" contributors · "+fmt(S.raid.misses)+" misses":"Raid status will appear here.");
}
function showTargets(){
 let node=el("targetSelect"),current=node.value;
 node.innerHTML="<option value=''>Select a rival</option>"+S.targets.map(t=>"<option value='"+esc(t.player_id)+"'>"+esc(t.mr_username)+" — "+esc(t.city)+" · "+fmt(t.warmth)+" warmth</option>").join("");
 if(S.targets.some(t=>t.player_id===current))node.value=current;
}
function showBoard(){
 el("leaderboard").innerHTML=S.board.length?S.board.map((r,i)=>"<div class='score-row'><span class='rank'>"+(i+1)+"</span><div><strong>"+esc(r.mr_username)+"</strong><small>"+esc(r.city)+"</small></div><strong>"+fmt(r.score)+" pts</strong></div>").join(""):"<div class='empty'>The scoreboard is waiting for its first winner.</div>";
}
function showCities(){
 el("cityStandings").innerHTML=S.cities.length?S.cities.map(r=>"<div class='city-row'><span class='rank'>✦</span><div><strong>"+esc(r.city)+"</strong><small>"+fmt(r.active_players)+" active · "+fmt(r.daily_wins)+" daily wins</small></div><strong>"+fmt(Math.round(r.score_x100/100))+" pts</strong></div>").join(""):"<div class='empty'>City standings are not available yet.</div>";
}
function showShop(){
 txt("shopBalance",S.shop?.balance??S.me?.resources?.snowflakes);
 const owned=new Set(S.shop?.unlocked||[]),wearing=S.shop?.equipped||{};
 el("catalog").innerHTML=S.items.length?S.items.map(i=>{
  let has=owned.has(i.key),on=wearing[i.category]===i.key;
  let button=has?"<button class='button button-outline' data-equip='"+esc(i.key)+"' "+(on?"disabled":"")+">"+(on?"Equipped":"Equip")+"</button>":"<button class='button button-gold' data-buy='"+esc(i.key)+"' "+(!S.me?.registered?"disabled":"")+">Purchase</button>";
  return "<article class='catalog-card'><span class='tag'>"+esc(i.rarity)+" · "+esc(i.category)+"</span><h3>"+esc(i.name)+"</h3><p>"+esc(i.detail)+"</p><div class='catalog-row'><strong>✦ "+fmt(i.cost)+"</strong>"+button+"</div></article>";
 }).join(""):"<p class='empty'>The market is currently unavailable.</p>";
}
async function loadPublic(){
 const results=await Promise.allSettled([get("/v1/game/leaderboard?limit=20"),get("/v1/game/cities"),get("/v1/game/raid?day=1"),get("/v1/game/catalog")]);
 if(results[0].status==="fulfilled")S.board=results[0].value.players||[];
 if(results[1].status==="fulfilled")S.cities=results[1].value.cities||[];
 if(results[2].status==="fulfilled")S.raid=results[2].value;
 if(results[3].status==="fulfilled")S.items=results[3].value.items||[];
 showBoard();showCities();showBoss();showShop();
}
async function loadPrivate(){
 if(!S.session){S.me=null;S.world=null;S.shop=null;S.targets=[];S.progress=null;showMe();return}
 try{S.me=await get("/v1/game/me")}
 catch(e){if(e.status===401){S.session=null;S.me=null;S.progress=null;showMe();return}throw e}
 if(S.me.registered){
  const results=await Promise.allSettled([get("/v1/game/world"),get("/v1/game/wardrobe"),get("/v1/game/targets"),get("/v1/game/progress")]);
  if(results[0].status==="fulfilled")S.world=results[0].value;
  if(results[1].status==="fulfilled")S.shop=results[1].value;
  if(results[2].status==="fulfilled")S.targets=results[2].value.targets||[];
  if(results[3].status==="fulfilled")S.progress=results[3].value;
 }
 showMe();showTargets();showBoss();showShop();
}
function updateDiscardSubmit(){
 el("discardConfirm").disabled=!S.discard||!el("discardAcknowledge").checked||
     el("discardPhrase").value!=="DISCARD DISCORD CHARACTER"||S.busy;
}
function hideDiscardOffer(){
 el("discordDiscardPanel").classList.add("hidden");S.discard=null;
 el("discardPhrase").value="";el("discardAcknowledge").checked=false;
 updateDiscardSubmit();
}
async function loadDiscardOffer(){
 const offer=await get("/v1/auth/discord/discard/preview");
 if(!S.session?.links?.some(x=>x.provider==="underworld"))throw Error("Sign in with Underworld to keep the correct character.");
 S.discard=offer;
 txt("discardKeepName",offer.keep.name);
 txt("discardKeepDetails",(offer.keep.city?offer.keep.city+" · ":"")+
    "Your Underworld player and all its progress are retained. Player ID: "+offer.keep.player_id);
 txt("discardOldName",offer.discard.name);
 txt("discardOldDetails",offer.discard.city+" · "+fmt(offer.discard.score)+" points · "+
    fmt(offer.discard.snowflakes)+" Snowflakes · "+
    fmt(offer.discard.snowballs)+" snowballs · "+fmt(offer.discard.warmth)+" warmth · "+
    fmt(offer.discard.cosmetic_unlocks)+" cosmetics unlocked · "+
    fmt(offer.discard.pvp_attacks)+" PvP attacks · "+fmt(offer.discard.boss_attacks)+" NPC attacks.");
 const owned=Object.entries(offer.discard.inventory||{}).filter(([,qty])=>qty>0)
     .map(([name,qty])=>name+" ×"+qty);
 txt("discardInventory","Inventory that will not transfer: "+(owned.length?owned.join(", "):"no stored items"));
 txt("discardWarning",offer.warning);
 el("discardPhrase").value="";el("discardAcknowledge").checked=false;
 el("discordDiscardPanel").classList.remove("hidden");
 updateDiscardSubmit();
 notice("Choose carefully: your separate Discord character will be retired only if you confirm.","error");
}
async function refresh(){await Promise.all([loadPublic(),loadPrivate()])}
async function resume(){try{S.session=await get("/v1/auth/session")}catch{S.session=null}await refresh()}
async function act(fn){
 if(S.busy)return;
 if(!S.session)return authModal();
 S.busy=true;document.querySelectorAll(".actions-inline button,.craft-card button").forEach(b=>b.disabled=true);
 try{await fn();await refresh()}catch(e){notice(e.message,"error")}
 finally{S.busy=false;document.querySelectorAll(".actions-inline button,.craft-card button").forEach(b=>b.disabled=false)}
}
function registered(){if(S.me?.registered)return true;section("home");notice("Register your player at Headquarters first.","error");return false}
function bind(){
 document.querySelectorAll("[data-nav]").forEach(b=>b.addEventListener("click",()=>section(b.dataset.nav)));
 el("heroPlay").onclick=()=>S.session?section("home"):authModal();
 el("loginCTA").onclick=authModal;el("closeAuth").onclick=closeAuth;
 el("authDialog").onclick=e=>{if(e.target===el("authDialog"))closeAuth()};
 document.addEventListener("keydown",e=>{if(e.key==="Escape")closeAuth()});
 el("authToggle").onclick=()=>{if(!S.session)return authModal();act(async()=>{await post("/v1/auth/logout",{},true);S.session=null;S.me=null;notice("Signed out.","success")})};
 el("demoForm").onsubmit=async e=>{
  e.preventDefault();let b=e.target.querySelector("button");b.disabled=true;
  try{
   S.session=await post("/v1/auth/demo",{code:el("demoCode").value,slot:Number(el("demoSlot").value)},false);
   el("demoCode").value="";closeAuth();await refresh();notice("Signed in to isolated staging.","success");
  }catch(x){notice(x.message,"error")}finally{b.disabled=false}
 };
 el("underworldForm").onsubmit=async e=>{
  e.preventDefault();
  try{S.session=await post("/v1/auth/underworld",{assertion:el("underworldAssertion").value},false);el("underworldAssertion").value="";closeAuth();await refresh();notice("Underworld assertion verified.","success")}
  catch(x){notice(x.message,"error")}
 };
 el("refreshShared").onclick=async()=>{
  if(!S.session)return authModal();
  try{
   S.session=await get("/v1/auth/session");
   S.progress=await get("/v1/game/progress");
   showMe();
   notice("Progress verified against the authoritative PostgreSQL game.","success");
  }catch(e){notice(e.message,"error")}
 };
 el("discardAcknowledge").onchange=updateDiscardSubmit;
 el("discardPhrase").oninput=updateDiscardSubmit;
 el("discardForm").onsubmit=e=>{
  e.preventDefault();
  if(el("discardConfirm").disabled||!S.discard)return;
  act(async()=>{
   const result=await post("/v1/auth/discord/discard/confirm",{
     acknowledged_loss:el("discardAcknowledge").checked,
     confirmation:el("discardPhrase").value
   },true);
   hideDiscardOffer();
   S.session=await get("/v1/auth/session");
   notice("Discord login now opens your Underworld character. "+
     "The separate Discord character was retired without transferring its progress.","success");
   if(!result.linked)throw Error("Replacement was not verified");
  });
 };
 el("discardCancel").onclick=()=>{
  if(!S.session)return hideDiscardOffer();
  act(async()=>{
   await post("/v1/auth/discord/discard/cancel",{},true);
   hideDiscardOffer();
   notice("Cancelled. Both characters are unchanged.");
  });
 };
 el("linkDiscord").onclick=async()=>{
  if(!S.session)return authModal();
  try{
   const r=await post("/v1/auth/discord/start",{mode:"link"},true);
   if(!r.authorize_url?.startsWith("https://discord.com/"))throw Error("Unexpected OAuth destination");
   location.assign(r.authorize_url);
  }catch(e){notice(e.message,"error")}
 };
 el("discordLogin").onclick=async()=>{
  try{const r=await post("/v1/auth/discord/start",{mode:"login"},false);if(!r.authorize_url?.startsWith("https://discord.com/"))throw Error("Unexpected OAuth destination");location.assign(r.authorize_url)}
  catch(x){notice(x.message,"error")}
 };
 el("registerForm").onsubmit=e=>{
  e.preventDefault();act(async()=>{
   const r=await post("/v1/game/register",{mr_username:el("characterName").value.trim(),city:el("cityChoice").value},true);
   notice("Welcome to "+r.city+", "+r.mr_username+"!","success");
  });
 };
 el("readyButton").onclick=()=>{if(registered())act(async()=>{await post("/v1/game/ready",{},true);notice("You are ready to be targeted.","success")})};
 el("findTargets").onclick=()=>{if(registered())act(async()=>{S.targets=(await get("/v1/game/targets")).targets||[];showTargets();notice("Rival list refreshed.")})};
 el("throwButton").onclick=()=>{
  if(!registered())return;
  let target=el("targetSelect").value;
  if(!target)return notice("Select a rival first.","error");
  act(async()=>{const r=await post("/v1/game/throw",{target_player_id:target,style:el("throwStyle").value},true,true);notice(r.hit?"Direct hit! +"+r.points_awarded+" points.":"Snowball missed.",r.hit?"success":"")});
 };
 for(const kind of ["boss","siege"]){
  el(kind==="boss"?"bossButton":"siegeButton").onclick=()=>{
   if(!registered())return;
   act(async()=>{let r=await post("/v1/game/"+kind,{},true,true);notice(r.hit?"Hit! "+r.damage+" damage and "+r.points+" points.":"Shot missed.",r.hit?"success":"")});
  };
 }
 el("craftButton").onclick=()=>{if(registered())act(async()=>{let r=await post("/v1/game/craft",{item:el("craftChoice").value},true,true);notice(r.text||"Crafted.","success")})};
 el("catalog").onclick=e=>{
  const b=e.target.closest("button");if(!b||!registered())return;
  if(b.dataset.buy)act(async()=>{let r=await post("/v1/game/wardrobe/purchase",{item:b.dataset.buy},true,true);notice(r.message,"success")});
  if(b.dataset.equip)act(async()=>{let r=await post("/v1/game/wardrobe/equip",{item:b.dataset.equip},true);notice(r.message,"success")});
 };
 for(const id of ["refreshHome","refreshBoss","refreshShop"]){el(id).onclick=()=>refresh().then(()=>notice("Game state refreshed.")).catch(e=>notice(e.message,"error"))}
}
async function init(){
 bind();
 try{
  let [cfg,health]=await Promise.all([get("/v1/web/config"),get("/v1/health")]);
  S.config=cfg;el("discordLogin").disabled=!cfg.discord_oauth;
  if(!cfg.discord_oauth)el("discordLogin").textContent="Discord login (not configured)";
  if(!cfg.underworld_assertions)el("underworldForm").querySelector("button").disabled=true;
  txt("sideStatus",(health.status||"unknown").toUpperCase());txt("sideStatusDetail","Isolated staging · "+cfg.season);
  await resume();
  if(location.search.includes("login=ok"))notice("Discord login successful.","success");
  if(location.search.includes("linked=discord"))notice("Discord account linked to this character.","success");
  if(location.search.includes("discord=discard-offer")){
    try{await loadDiscardOffer()}
    catch(e){notice("Cannot load Discord character confirmation: "+e.message,"error")}
  }
  if(location.search.includes("discord=conflict")){
    const reason=new URLSearchParams(location.search).get("reason")||"manual-review";
    const explanations={
      "gameplay":"That Discord login already has its own registered Snowfall player. For safety, its game progress cannot be automatically merged with your Underworld character.",
      "activity":"That Discord login already has recorded Snowfall activity, such as rewards or event history. A manual review is required before linking.",
      "linked-elsewhere":"That Discord account is already connected to a different Underworld character. Snowfall will not transfer it automatically.",
      "character-occupied":"This Underworld character already has a different Discord account connected.",
      "reserved":"That Discord account has a previously reserved identity requiring manual review.",
      "underworld-required":"Sign into Snowfall through Underworld first, then use Link Discord account.",
      "manual-review":"The link could not be completed safely. No accounts or progress were changed."
    };
    const explanation=explanations[reason]||explanations["manual-review"];
    const details=el("linkConflictDetail");
    if(details){details.textContent=explanation;details.classList.remove("hidden")}
    notice(explanation,"error");
  }
  if(location.search.includes("linked=discord")||location.search.includes("discord=conflict")||location.search.includes("discord=discard-offer"))
    history.replaceState(null,"",location.pathname);
 }catch(e){txt("sideStatus","OFFLINE");txt("sideStatusDetail",e.message);notice("Staging service unavailable: "+e.message,"error")}
}
document.addEventListener("DOMContentLoaded",init);
