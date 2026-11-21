/* Operation Snowfall v2.9.6d — illustrated headquarters and shared boss state. */
"use strict";
const S={session:null,me:null,world:null,raid:null,bossRequest:0,bossPending:false,bossStale:false,hq:null,hqClock:0,shop:null,items:[],board:[],cities:[],targets:[],config:null,progress:null,discard:null,verification:null,busy:false,pendingActions:new Map()};
const el=id=>document.getElementById(id);
const txt=(id,v)=>{if(el(id))el(id).textContent=v==null?"—":String(v)};
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=v=>Number(v??0).toLocaleString("en-GB");
const CITY_SLUG=Object.freeze({
 "Chicago":"chicago","Detroit":"detroit","Las Vegas":"las_vegas",
 "Los Angeles":"los_angeles","New York":"new_york","Philadelphia":"philadelphia"
});
const COSMETIC_ART=Object.freeze({
 "ice_frame":"/art/v290/cosmetics/frames/ice_frame.png",
 "gold_frame":"/art/v290/cosmetics/frames/gold_frame.png",
 "holly_frame":"/art/v290/cosmetics/frames/holly_frame.png",
 "snow_trail":"/art/v290/cosmetics/trails/snow_trail.png",
 "candy_trail":"/art/v290/cosmetics/trails/candy_trail.png",
 "goggles":"/art/v290/cosmetics/gear/goggles.png",
 "boots":"/art/v290/cosmetics/gear/boots.png",
 "scarf":"/art/v290/cosmetics/gear/scarf.png",
 "midnight_banner":"/art/v290/cosmetics/banners/midnight_banner.png",
 "aurora_banner":"/art/v290/cosmetics/banners/aurora_banner.png",
 "gilded_banner":"/art/v290/cosmetics/banners/gilded_banner.png",
 "noir_detective":"/art/v290/portraits/noir_detective_m.webp",
 "winter_enforcer":"/art/v290/portraits/winter_enforcer_m.webp",
 "frost_spectre":"/art/v290/portraits/frost_spectre_m.webp",
 "recruit_f":"/art/v290/portraits/recruit_f.webp",
 "noir_detective_f":"/art/v290/portraits/noir_detective_f.webp",
 "winter_enforcer_f":"/art/v290/portraits/winter_enforcer_f.webp",
 "frost_spectre_f":"/art/v290/portraits/frost_spectre_f.webp"
});
const HQ_SLOTS=Object.freeze({
 portrait:["noir_detective","winter_enforcer","frost_spectre","recruit_f","noir_detective_f","winter_enforcer_f","frost_spectre_f"],
 frame:["ice_frame","gold_frame","holly_frame"],
 banner:["midnight_banner","aurora_banner","gilded_banner"],
 gear:["goggles","boots","scarf"],
 trail:["snow_trail","candy_trail"]
});
function ownedEquipped(wardrobe,slot){
 const key=wardrobe?.equipped?.[slot];
 return Array.isArray(wardrobe?.unlocked)&&wardrobe.unlocked.includes(key)&&
     HQ_SLOTS[slot]?.includes(key)?key:null;
}
function profileLayers(wardrobe){
 const layers={};
 for(const slot of Object.keys(HQ_SLOTS)){
  const key=ownedEquipped(wardrobe,slot);
  layers[slot]={key,src:key?COSMETIC_ART[key]:slot==="portrait"?"/art/v290/portraits/recruit_m.webp":null};
 }
 return layers;
}
function cosmeticName(key){return S.items.find(item=>item.key===key)?.name||
    (key?key.split("_").map(word=>word[0].toUpperCase()+word.slice(1)).join(" "):"None");}
function showWardrobe(){
 const wardrobe=S.session&&S.me?.registered?S.shop:null;
 const layers=profileLayers(wardrobe);
 el("hqPortraitWell").classList.toggle("has-frame",!!layers.frame.key);
 el("hqBannerWell").classList.toggle("hidden",!layers.banner.key);
 for(const slot of Object.keys(layers)){
  const id=slot[0].toUpperCase()+slot.slice(1),node=el("hq"+id),layer=layers[slot];
  if(layer.src){
   if(node.getAttribute("src")!==layer.src)node.setAttribute("src",layer.src);
   node.classList.remove("hidden");
  }else{
   node.classList.add("hidden");
   node.removeAttribute("src");
  }
  node.dataset.cosmetic=layer.key||"";
  const name=layer.key?cosmeticName(layer.key):slot==="portrait"?"Recruit":"None";
  if(slot==="portrait")node.alt=name+" profile";
  txt("hq"+id+"Name",name);
 }
 txt("hqWardrobeStatus",wardrobe?
     fmt(wardrobe.unlocked?.length||0)+" cosmetics owned · shared with Discord":
     "Wardrobe not loaded — refresh to check equipped cosmetics.");
}
const MEDALS=Object.freeze(["first_flurry","deadeye","rival_hunter","critical_ace","knockout_artist","don_destroyer","boss_regular","fort_breaker","quest_master","gift_collector","golden_legend","seven_days","cocoa_club","first_style","collector","full_outfit"]);
const RARITIES=["Common","Rare","Epic","Legendary"];
function hqPercent(value,cap){
 if(value==null||!(Number(cap)>0)||!Number.isFinite(Number(value)))return 0;
 return Math.min(100,Math.max(0,Number(value)*100/Number(cap)));
}
function hqTimer(value,phase,now){
 if(phase==="paused")return "Paused";
 if(phase!=="live"||!value)return "—";
 const until=Date.parse(value);
 if(!Number.isFinite(until))return "—";
 const seconds=Math.ceil((until-now)/1000);
 if(seconds<=0)return "Refresh due";
 const d=Math.floor(seconds/86400),h=Math.floor(seconds/3600)%24,m=Math.floor(seconds/60)%60,s=seconds%60;
 return (d?d+"d ":"")+(d||h?h+"h ":"")+String(m).padStart(2,"0")+"m "+String(s).padStart(2,"0")+"s";
}
function updateHqTimers(){
 if(!S.session||!S.hq?.registered)return;
 const now=Date.now()+S.hqClock;
 for(const key of ["snowball","warmth","throw","reset","knockout","shield"])
  txt("hqTimer"+key[0].toUpperCase()+key.slice(1),hqTimer(S.hq.timers?.[key],S.hq.phase,now));
 if(S.hq.timers?.arena&&S.hq.phase==="live")
  txt("hqArenaState",Date.parse(S.hq.timers.arena)>now?"Arena active · "+hqTimer(S.hq.timers.arena,S.hq.phase,now):"Arena status expired · refresh");
}
function hqMedal(t,featured=false){
 if(!MEDALS.includes(t.key))return "";
 const rarity=RARITIES.includes(t.rarity)?t.rarity:"Common",earned=t.unlocked===true;
 return "<article class='hq-medal "+(earned?"earned":"locked")+"' data-rarity='"+rarity+"'>"+
 "<img loading='lazy' src='/art/v290/trophies/medals/"+t.key+".png' alt=''>"+
 "<div><strong>"+esc(t.badge)+"</strong><small>"+esc(rarity)+" · "+(earned?"Earned":"Locked")+"</small>"+
 (featured?"":"<p>"+esc(t.description)+"</p><div class='hq-meter'><span style='width:"+hqPercent(t.progress,t.target)+"%'></span></div><small>"+fmt(t.progress)+" / "+fmt(t.target)+"</small>")+"</div></article>";
}
function showHq(){
 const h=S.session&&S.me?.registered&&S.hq?.registered?S.hq:null;
 const quests=h&&Array.isArray(h.quests)?h.quests:[],trophies=h&&Array.isArray(h.trophies)?h.trophies.filter(t=>MEDALS.includes(t.key)):[];
 const earned=trophies.filter(t=>t.unlocked===true);
 const rarity=h&&RARITIES.includes(h.rarity)?h.rarity:"Common";
 el("hqCollector").dataset.rarity=rarity;
 txt("hqPlayerTitle",h?.title||"Title unavailable");
 txt("hqRarity",h?rarity+" style":"Style unavailable");
 txt("hqRank",h?.rank!=null?"#"+fmt(h.rank):"—");
 txt("hqDailyPoints",h?.daily_points==null?"—":fmt(h.daily_points));
 txt("hqPhase",S.me?.phase?String(S.me.phase).toUpperCase()+" · "+(S.me.day?"Day "+S.me.day+" of 7":"Awaiting event"):"Awaiting event");
 const cap=h?.caps||{};
 el("hqAmmoMeter").style.width=hqPercent(S.me?.resources?.snowballs,cap.snowballs)+"%";
 el("hqWarmthMeter").style.width=hqPercent(S.me?.resources?.warmth,cap.warmth)+"%";
 el("hqPvpMeter").style.width=hqPercent(h?.today_pvp,cap.pvp)+"%";
 txt("hqPvpValue",h?.today_pvp!=null?fmt(h.today_pvp)+" / "+fmt(cap.pvp)+" pts":"—");
 txt("hqArenaState",!h?"Arena status unavailable":h.phase==="paused"?"Event paused":h.phase!=="live"?"Arena not open":h.timers?.arena?"Checking arena timer…":"Arena inactive — enter Snowball Alley");
 for(const key of ["snowball","warmth","throw","reset","knockout","shield"])
  txt("hqTimer"+key[0].toUpperCase()+key.slice(1),"—");
 if(h)updateHqTimers();
 const recommendation=el("hqRecommended");
 const routes={world:["boss","Open raid"],fight:["combat","Find rivals"],player:["combat","Enter arena"],rankings:["cities","View standings"],quests:["missions","View assignments"]};
 const next=h?routes[h.next_action_route]:null;
 recommendation.classList.toggle("hidden",!next);
 recommendation.dataset.destination=next?.[0]||"";
 recommendation.textContent=next?.[1]||"Open";
 if(h)txt("hqNextMove",h.next_action+(["arcade","guide"].includes(h.next_action_route)?" See Discord for this feature.":""));
 txt("hqQuestCount",h?quests.filter(q=>q.claimed).length+" / "+quests.length+" claimed":"Unavailable");
 el("hqQuestList").innerHTML=quests.length?quests.map(q=>"<article class='hq-quest'><strong>"+esc(q.name)+"</strong><span>"+(q.claimed?"Claimed":Number(q.progress)>=Number(q.target)?"Ready to claim in Discord":"In progress")+"</span><div class='hq-meter'><span style='width:"+hqPercent(q.progress,q.target)+"%'></span></div><small>"+fmt(q.progress)+" / "+fmt(q.target)+"</small></article>").join(""):"<p class='subtle'>"+(h?"No daily assignments are available.":"Refresh to load your assignments.")+"</p>";
 txt("hqGiftStatus",h?"Daily gift: "+h.daily_gift+" · Bonus: "+h.bonus_gift+" · Open gifts in Discord.":"Gift status unavailable.");
 txt("hqTrophyCount",h?earned.length+" / "+trophies.length+" collected":"Achievements unavailable — refresh to retry.");
 el("hqTrophyGrid").innerHTML=trophies.map(t=>hqMedal(t)).join("");
 el("hqFeatured").innerHTML=earned.slice().sort((a,b)=>(Number(b.title===h.title)-Number(a.title===h.title))||RARITIES.indexOf(b.rarity)-RARITIES.indexOf(a.rarity)||String(a.badge).localeCompare(String(b.badge))).slice(0,3).map(t=>hqMedal(t,true)).join("");
 const records=[["PvP throws","pvp_throws"],["PvP accuracy","accuracy"],["Critical hits","critical_hits"],["Knockouts","knockouts"],["Best hit","best_hit"],["Boss damage","boss_damage"],["Siege damage","siege_damage"],["Active days","active_days"]];
 el("hqRecordGrid").innerHTML=records.map(([label,key])=>"<div><small>"+label+"</small><strong>"+(h?.records?.[key]==null?"—":fmt(h.records[key])+(key==="accuracy"?"%":""))+"</strong></div>").join("");
}
function configureBranding(branding){
 const banner=el("siteBanner"),icon=el("brandIcon");
 if(branding?.banner){
  banner.onerror=()=>{banner.classList.add("hidden");el("bannerFallback").classList.remove("hidden")};
  banner.src="/static/snowfall-site-banner.webp";
  banner.classList.remove("hidden");el("bannerFallback").classList.add("hidden");
 }
 if(branding?.icon){
  icon.onerror=()=>{icon.classList.add("hidden");el("brandFallback").classList.remove("hidden")};
  icon.src="/static/snowfall-site-icon.webp";
  icon.classList.remove("hidden");el("brandFallback").classList.add("hidden");
 }
}
function bossArtTier(hp,max){
 if(!(Number(max)>0))return 100;
 if(Number(hp)<=0)return 0;
 const maximum=Math.trunc(Number(max)),remaining=Math.max(0,Math.min(Math.trunc(Number(hp)),maximum));
 return Math.max(10,Math.floor((remaining*10+maximum-1)/maximum)*10);
}
function safeStreetsUrl(value){
 if(typeof value!=="string")return "";
 try{
  const url=new URL(value);
  if(url.protocol==="https:" && url.host==="discord.com" && !url.search && !url.hash &&
      /^\/channels\/\d{15,25}\/\d{15,25}$/.test(url.pathname))return url.href;
 }catch{}
 return "";
}
function configureStreets(value){
 const url=safeStreetsUrl(value);
 for(const id of ["streetsLink","streetsTopLink"]){
  const link=el(id);if(!link)continue;
  link.classList.toggle("hidden",!url);
  if(url)link.href=url;else link.removeAttribute("href");
 }
 el("streetsUnavailable").classList.toggle("hidden",!!url);
}

let timer;
function notice(message,kind){
 const node=el("toast");node.textContent=String(message);node.className="toast "+(kind||"");
 clearTimeout(timer);timer=setTimeout(()=>node.classList.add("hidden"),5500);
}
function requestKey(path,body){
 // Stable within the current authenticated character for identical inputs.
 return String(S.session?.player_id||"guest")+"|"+path+"|"+JSON.stringify(body??{});
}
function nextActionId(){
 return "web-ui-"+(crypto.randomUUID?crypto.randomUUID():
        String(Date.now())+"-"+Math.random()).replace(/[^A-Za-z0-9_-]/g,"");
}
async function request(path,method,body,mutation,unique){
 const headers={"Accept":"application/json"};
 if(body!==undefined)headers["Content-Type"]="application/json";
 if(mutation)headers["X-Snowfall-CSRF"]=S.session?.csrf||"";
 const key=unique?requestKey(path,body):null;
 if(key){
  if(!S.pendingActions.has(key))S.pendingActions.set(key,nextActionId());
  headers["Idempotency-Key"]=S.pendingActions.get(key);
 }
 const abort=new AbortController();
 const clock=setTimeout(()=>abort.abort(),15000);
 let response;
 try{
  response=await fetch(path,{
   method:method||"GET",headers,credentials:"same-origin",cache:"no-store",
   body:body===undefined?undefined:JSON.stringify(body),signal:abort.signal
  });
 }catch{
  // The server may have committed an action before the response was lost.
  // KEEP the key for the player's next attempt rather than spending twice.
  let err=Error("Connection interrupted. Your action may have succeeded. "+
      "Check shared progress, then retry the same action safely.");
  err.status=0;throw err;
 }finally{clearTimeout(clock)}
 let data={};try{data=await response.json()}catch{}
 if(!response.ok){
  if(key&&response.status<500)S.pendingActions.delete(key);
  let err=Error(typeof data.detail==="string"?data.detail:
      "Request failed ("+response.status+")");
  err.status=response.status;
  if(response.status>=500)err.message+=". Status uncertain — check progress before retrying.";
  throw err;
 }
 if(key)S.pendingActions.delete(key);
 return data;
}
const get=path=>request(path);
const post=(path,body,mutate,unique)=>request(path,"POST",body,mutate,unique);
function section(name){
 if(!["home","combat","boss","shop","cities"].includes(name))name="home";
 document.querySelectorAll(".panel").forEach(n=>n.classList.toggle("active",n.id==="page-"+name));
 document.querySelectorAll(".nav-item").forEach(n=>{
  const active=n.dataset.nav===name;
  n.classList.toggle("active",active);
  n.setAttribute("aria-pressed",String(active));
 });
 el("primaryNav").classList.remove("open");
 el("menuToggle").setAttribute("aria-expanded","false");
 if(name==="shop")showShop();
 if(name==="cities"){showCities();showBoard()}
 if(name==="boss"){showBoss();if(!S.bossPending&&!S.busy)void refreshBossVisual()}
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
 el("accountTools").classList.toggle("hidden",!signed);
 if(signed&&!S.session?.links?.some(x=>x.provider==="discord"))el("accountTools").open=true;
 showWardrobe();
 if(!signed){el("bossRecap").classList.add("hidden");showHq();}
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
   showVerification();
   return;
 }
 renderProgress();
 showVerification();
 txt("welcomeName",S.me.mr_username);txt("welcomeCity",S.me.city+" · Day "+(S.me.day||"—"));
  txt("hqCityName",S.me.city+" winter headquarters");
  const citySlug=CITY_SLUG[S.me.city];
  const cityImage=el("hqCityArt");
  if(citySlug){cityImage.src="/art/cities/"+citySlug+".webp";el("hqCityCrest").src="/art/v290/cities/crests/"+citySlug+"_crest.png";}
  else {cityImage.removeAttribute("src");el("hqCityCrest").removeAttribute("src");}
  cityImage.alt="";
  const ammo=Number(S.me.resources?.snowballs||0);
  txt("hqNextMove",ammo>0?
      "You've got "+fmt(ammo)+" snowballs ready. Pick a rival or confront the Snow Don.":
      "Ammunition is low. Explore the Winter Market or check back for regeneration.");
 txt("ammoValue",S.me.resources?.snowballs);txt("warmthValue",S.me.resources?.warmth);
 txt("flakeValue",S.me.resources?.snowflakes);txt("scoreValue",fmt(S.me.score));
 txt("shopBalance",fmt(S.me.resources?.snowflakes));
 txt("ammoSub",S.me.resources?.next_snowball_at?"Regenerating snowballs":"Ready for action");
 txt("phaseValue",S.me.phase.toUpperCase());txt("sideStatus",S.me.phase.toUpperCase());
 txt("sideStatusDetail","Day "+(S.me.day||"—")+" of 7 · "+S.me.city);
 showHq();
}
function showVerification(){
 const links=S.session?.links||[];
 const linked=!!S.session&&!!S.me?.registered&&
    links.some(x=>x.provider==="discord")&&links.some(x=>x.provider==="underworld");
 el("crossPlatformPanel").classList.toggle("hidden",!linked);
 if(!linked)return;
 const v=S.verification;
 txt("verificationIdentity","✓ Underworld and Discord linked to player "+S.session.player_id+".");
 if(!v||v.state==="not_started"){
   txt("verificationState","Not started. Save a baseline before your Discord move.");
   txt("verificationDiscord","Discord confirmation: waiting for verification.");
   txt("verificationGameplay","Discord gameplay: waiting for an actual game action.");
   txt("verificationReverse","Website → Discord reverse check: optional.");
   txt("verificationCounts","No activity in the current check.");
   txt("verificationDelta","Official progress will be compared after verification starts.");
   return;
 }
 if(v.state==="expired"){
   txt("verificationState","Verification expired after 15 minutes. Start a fresh test.");
   txt("verificationDiscord","No current Discord proof.");
   txt("verificationGameplay","No current gameplay proof.");
   txt("verificationReverse","Reverse check: not completed.");
   txt("verificationCounts","The previous test has expired.");
   txt("verificationDelta","Start a new check to record a fresh baseline.");
   return;
 }
 txt("verificationState",v.discord_gameplay_verified?
     "✓ Discord action recorded in the same official game database.":
     v.discord_confirmed?"✓ Same player verified on Discord. Now perform a game action.":
     "Awaiting the /snowbridge verify Discord command.");
 txt("verificationDiscord",v.discord_confirmed?
     "✓ Discord interaction authenticated as this canonical player.":
     "○ Discord confirmation pending. Run /snowbridge verify.");
 txt("verificationGameplay",v.discord_gameplay_verified?
     "✓ A real Discord crafting, PvP or boss action was recorded after this test started.":
     "○ No verified Discord gameplay yet. Use /snowbridge craft or /snowbridge boss.");
 txt("verificationReverse",v.web_gameplay_seen_by_discord?
     "✓ Discord re-read progress after a website action.":
     "○ Optional: act on this website, then run /snowbridge verify again.");
 txt("verificationCounts","Official events since baseline: Discord "+fmt(v.discord_action_count)+
     " · Website "+fmt(v.web_action_count));
 const d=v.delta||{},pieces=[];
 for(const [key,name] of [["score","points"],["snowballs","snowballs"],["snowflakes","Snowflakes"],
                           ["warmth","warmth"],["boss_hp","Snow Don HP"]]){
   const value=Number(d[key]||0);
   if(value)pieces.push((value>0?"+":"")+fmt(value)+" "+name);
 }
 for(const [item,count] of Object.entries(d.inventory||{})){
   if(count)pieces.push((count>0?"+":"")+fmt(count)+" "+item);
 }
 txt("verificationDelta","Changes from website baseline: "+(
     pieces.length?pieces.join(" · "):"No stable game values changed yet."));
}
function renderProgress(){
 const p=S.progress;
 if(!p?.registered){txt("progressSummary","Loading official shared progress…");return}
 txt("progressSummary","Official score: "+fmt(p.score)+" · "+fmt(p.snowballs)+
     " snowballs · "+fmt(p.snowflakes)+" snowflakes · Snow Don "+
     fmt(p.boss_hp)+"/"+fmt(p.boss_max_hp)+" HP.");
}
function showBoss(){
 const raid=S.raid,known=raid?.hp!=null&&Number(raid.max_hp)>0;
 const hp=known?Number(raid.hp):0,max=known?Number(raid.max_hp):0;
 const state=raid?.state||"waiting",defeated=state==="defeated",disabled=state==="disabled";
 const visibleHealth=known&&!disabled,percent=visibleHealth?Math.max(0,Math.min(100,100*hp/max)):0;
 const tier=visibleHealth?raid.tier:null;
 for(const id of ["snowDonHero","bossScene"])el(id).dataset.bossState=state;
 const art=el("heroBossArt"),portrait=el("bossPortrait");
 const splash=raid?.splash||"/art/v290/boss/phase_ice.webp";
 const portraitPath=raid?.portrait||"/art/boss/snow_don_100.png";
 if(art.getAttribute("src")!==splash)art.src=splash;
 if(portrait.getAttribute("src")!==portraitPath)portrait.src=portraitPath;
 art.dataset.tier=tier==null?"":String(tier);portrait.dataset.tier=art.dataset.tier;
 art.alt=defeated?"Original Discord Snow Don final defeat scene":"Original Discord Snow Don cinematic: "+(raid?.title||"awaiting the raid");
 portrait.alt=defeated?"Original Discord defeated Snow Don portrait":tier==null?"Original Snow Don portrait":"Discord Snow Don damage portrait — "+tier+"% health tier";
 txt("bossTierLabel",tier==null?"Awaiting status":tier===0?"Defeated":tier+"% artwork tier");
 el("heroLiveTitle").classList.toggle("hidden",defeated);el("heroDefeatTitle").classList.toggle("hidden",!defeated);
 txt("heroLede",defeated?"The shared Snow Don has fallen. The city celebrates. Visit the raid aftermath or continue your permitted daily activities.":"Six cities. Seven days. One very angry Snow Don. Grab your ammunition, pick your city and make a name for yourself.");
 const status=visibleHealth?fmt(hp)+" / "+fmt(max)+" HP · "+(raid?.title||""):(raid?.title||"Awaiting the Snow Don");
 txt("heroBossStatus",status+(S.bossStale?" · Refresh pending":""));
 txt("heroArtCaption",defeated?"THE FINAL SNOWFALL":(raid?.title||"ART FROM THE ORIGINAL DISCORD EVENT"));
 txt("heroBossLink",defeated?"View the aftermath":"Meet the Snow Don");
 txt("hqBossLink",defeated?"View boss aftermath":"🎯 Attack Snow Don");
 txt("bossHeadline",defeated?"The Snow Don has fallen!":disabled?"The boss is disabled":visibleHealth?"The Snow Don lives.":"The boss awaits.");
 txt("bossPhase",raid?.title||"The city is waiting");
 txt("raidDay",raid?.day?"SNOW DON / DAY "+raid.day+" OF 7":"SNOW DON / CURRENT STATUS");
 txt("bossHpText",visibleHealth?fmt(hp)+" / "+fmt(max)+" HP":"— / — HP");
 txt("bossDamage",visibleHealth?Math.round(100-percent)+"% damage taken":"—");
 const bar=el("bossHpBar");bar.style.width=percent+"%";
 if(visibleHealth)bar.parentElement.setAttribute("aria-valuenow",String(Math.round(percent)));
 else bar.parentElement.removeAttribute("aria-valuenow");
 for(const [id,key] of [["raidHits","hit_count"],["raidContributors","contributors"],["raidMisses","misses"]])
  txt(id,raid?.[key]==null?"—":fmt(raid[key]));
 txt("raidSummary",raid?.echo_attacks==null?"Raid statistics will appear once the boss spawns.":fmt(raid.echo_attacks)+" frozen-echo attempts · shared raid totals exclude echo damage.");
 txt("bossFreshness",S.bossStale?(raid?"Last known raid status — refresh pending.":"Raid unavailable — refresh pending."):raid?"Synced with the shared raid · refreshes every 30 seconds while this page is visible.":"Waiting for the shared raid.");
 txt("bossActionTitle",defeated?"The Don is down.": "Put the heat on him.");
 txt("bossActionText",defeated?"The real Don is defeated. The existing frozen-echo action remains available under the normal game rules; it cannot defeat him again.":"Attack the shared boss or defend your city’s siege. Daily limits, ammo costs and rewards are enforced in PostgreSQL.");
 txt("bossButton",defeated?"Attack frozen echo":"Attack the Snow Don");
 if(!S.busy)el("bossButton").disabled=disabled||raid?.season_phase==="closed"||raid?.season_phase==="finalized";
}
async function refreshBossVisual(){
 const sequence=++S.bossRequest;S.bossPending=true;
 try{
  const raid=await get("/v1/web/boss");
  if(sequence!==S.bossRequest)return;
  if(!["waiting","disabled","healthy","cracked","wounded","critical","defeated"].includes(raid.state))throw Error("Missing raid status");
  S.raid=raid;S.bossStale=false;
 }catch{
  if(sequence!==S.bossRequest)return;
  S.bossStale=true;
 }finally{
  if(sequence===S.bossRequest){S.bossPending=false;showBoss()}
 }
}
function showBossRecap(r){
 const echo=!!r.echo,final=!!r.final_blow&&!echo;
 txt("bossRecapTitle",final?"The final blow!":echo?"Frozen echo encounter":r.hit?"Direct hit!":"The Don dodged the shot.");
 txt("bossRecapText",(r.hit?(echo?"Echo damage: ":"Damage: ")+fmt(r.damage)+" · "+fmt(r.points)+" points.":"No hit this attempt.")+
    (r.repeated?" Previously recorded action.":""));
 const image=el("bossRecapArt"),tier=bossArtTier(r.hp_after,r.max_hp);
 image.src=tier===0?"/art/v290/boss/snow_don_0.webp":"/art/boss/snow_don_"+tier+".png";
 image.alt="Snow Don artwork at the recorded encounter's remaining health";
 el("bossRecap").classList.remove("hidden");
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
 el("cityStandings").innerHTML=S.cities.length?S.cities.map(r=>{
  const city=CITY_SLUG[r.city];
  const crest=city?"<img class='city-crest' src='/art/v290/cities/crests/"+city+"_crest.png' alt='' loading='lazy'>":"<span class='rank'>✦</span>";
  return "<div class='city-row'>"+crest+"<div><strong>"+esc(r.city)+"</strong><small>"+fmt(r.active_players)+" active · "+fmt(r.daily_wins)+" daily wins</small></div><strong>"+fmt(Math.round(r.score_x100/100))+" pts</strong></div>";
 }).join(""):"<div class='empty'>City standings are not available yet.</div>";
}
function showShop(){
 txt("shopBalance",S.shop?.balance??S.me?.resources?.snowflakes);
 const owned=new Set(S.shop?.unlocked||[]),wearing=S.shop?.equipped||{};
 el("catalog").innerHTML=S.items.length?S.items.map(i=>{
  let has=owned.has(i.key),on=has&&wearing[i.category]===i.key;
  let button=has?"<button class='button button-outline' data-equip='"+esc(i.key)+"' "+(on?"disabled":"")+">"+(on?"Equipped":"Equip")+"</button>":"<button class='button button-gold' data-buy='"+esc(i.key)+"' "+(!S.me?.registered?"disabled":"")+">Purchase</button>";
  const art=COSMETIC_ART[i.key];
   const preview=art?"<img class='catalog-thumb' src='"+art+"' loading='lazy' alt='"+esc(i.name)+" artwork preview'>":"";
   return "<article class='catalog-card'>"+preview+"<span class='tag'>"+esc(i.rarity)+" · "+esc(i.category)+"</span><h3>"+esc(i.name)+"</h3><p>"+esc(i.detail)+"</p><div class='catalog-row'><strong>✦ "+fmt(i.cost)+"</strong>"+button+"</div></article>";
 }).join(""):"<p class='empty'>The market is currently unavailable.</p>";
}
async function loadPublic(){
 const results=await Promise.allSettled([get("/v1/game/leaderboard?limit=20"),get("/v1/game/cities"),get("/v1/game/catalog")]);
 if(results[0].status==="fulfilled")S.board=results[0].value.players||[];
 if(results[1].status==="fulfilled")S.cities=results[1].value.cities||[];
 if(results[2].status==="fulfilled")S.items=results[2].value.items||[];
 showBoard();showCities();showBoss();showShop();
}
async function loadPrivate(){
 if(!S.session){S.me=null;S.world=null;S.hq=null;S.shop=null;S.targets=[];S.progress=null;S.verification=null;S.pendingActions.clear();showMe();showShop();return}
 try{S.me=await get("/v1/game/me")}
 catch(e){if(e.status===401){S.session=null;S.me=null;S.world=null;S.hq=null;S.shop=null;S.progress=null;S.targets=[];S.verification=null;showMe();showShop();return}throw e}
 if(S.me.registered){
  const results=await Promise.allSettled([get("/v1/game/world"),get("/v1/game/wardrobe"),get("/v1/game/targets"),get("/v1/game/progress"),get("/v1/game/headquarters")]);
  S.world=results[0].status==="fulfilled"?results[0].value:null;
  S.shop=results[1].status==="fulfilled"?results[1].value:null;
  S.targets=results[2].status==="fulfilled"?results[2].value.targets||[]:[];
  S.progress=results[3].status==="fulfilled"?results[3].value:null;
  S.hq=results[4].status==="fulfilled"?results[4].value:null;
  S.hqClock=Number.isFinite(Date.parse(S.hq?.server_time))?Date.parse(S.hq.server_time)-Date.now():0;
  const linked=(S.session.links||[]).some(x=>x.provider==="discord")&&
               (S.session.links||[]).some(x=>x.provider==="underworld");
  if(linked){
    try{S.verification=await get("/v1/verification/status")}
    catch{S.verification=null}
  }else S.verification=null;
 }else{S.shop=null;S.world=null;S.hq=null;S.progress=null;S.targets=[];S.verification=null;}
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
async function refresh(){await Promise.all([loadPublic(),loadPrivate()]);await refreshBossVisual()}
async function resume(){try{S.session=await get("/v1/auth/session")}catch{S.session=null}await refresh()}
async function act(fn){
 if(S.busy)return;
 if(!S.session)return authModal();
 S.busy=true;document.querySelectorAll(".actions-inline button,.craft-card button").forEach(b=>b.disabled=true);
 try{await fn();await refresh()}catch(e){notice(e.message,"error")}
 finally{S.busy=false;document.querySelectorAll(".actions-inline button,.craft-card button").forEach(b=>b.disabled=false);showBoss()}
}
function registered(){if(S.me?.registered)return true;section("home");notice("Register your player at Headquarters first.","error");return false}
function bind(){
 document.querySelectorAll("[data-nav]").forEach(b=>b.addEventListener("click",()=>section(b.dataset.nav)));
 el("menuToggle").onclick=()=>{
  const open=el("primaryNav").classList.toggle("open");
  el("menuToggle").setAttribute("aria-expanded",String(open));
 };
 document.querySelectorAll(".nav-item").forEach(b=>b.setAttribute("aria-pressed",String(b.classList.contains("active"))));
 el("heroPlay").onclick=()=>S.session?section("home"):authModal();
 el("hqRecommended").onclick=()=>{const dest=el("hqRecommended").dataset.destination;if(dest==="missions")el("hqMissions").scrollIntoView({block:"start"});else if(dest)section(dest)};
 el("loginCTA").onclick=authModal;el("closeAuth").onclick=closeAuth;
 el("authDialog").onclick=e=>{if(e.target===el("authDialog"))closeAuth()};
 document.addEventListener("keydown",e=>{if(e.key==="Escape")closeAuth()});
 el("authToggle").onclick=()=>{if(!S.session)return authModal();act(async()=>{await post("/v1/auth/logout",{},true);S.session=null;S.me=null;S.pendingActions.clear();notice("Signed out.","success")})};
 el("demoForm").onsubmit=async e=>{
  e.preventDefault();let b=e.target.querySelector("button");b.disabled=true;
  try{
   S.pendingActions.clear();S.session=await post("/v1/auth/demo",{code:el("demoCode").value,slot:Number(el("demoSlot").value)},false);
   el("demoCode").value="";closeAuth();await refresh();notice("Signed in to isolated staging.","success");
  }catch(x){notice(x.message,"error")}finally{b.disabled=false}
 };
 el("underworldForm").onsubmit=async e=>{
  e.preventDefault();
  try{S.pendingActions.clear();S.session=await post("/v1/auth/underworld",{assertion:el("underworldAssertion").value},false);el("underworldAssertion").value="";closeAuth();await refresh();notice("Underworld assertion verified.","success")}
  catch(x){notice(x.message,"error")}
 };
 el("refreshShared").onclick=async()=>{
  if(!S.session)return authModal();
  try{
   S.session=await get("/v1/auth/session");
   await loadPrivate();
   if(!S.progress?.registered)throw Error("Shared progress could not be verified. Refresh and try again.");
   notice("Progress verified against the authoritative PostgreSQL game.","success");
  }catch(e){notice(e.message,"error")}
 };
 el("verificationStart").onclick=()=>{
   if(!registered())return;
   act(async()=>{
     S.verification=await post("/v1/verification/start",{},true);
     showVerification();
     notice("Baseline saved. Now run /snowbridge verify in Discord.","success");
   });
 };
 el("verificationCheck").onclick=async()=>{
   try{await refresh();notice("Checked canonical progress and Discord receipts.","success")}
   catch(e){notice(e.message,"error")}
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
   act(async()=>{let r=await post("/v1/game/"+kind,{},true,true);if(kind==="boss")showBossRecap(r);notice(r.hit?"Hit! "+r.damage+" damage and "+r.points+" points.":"Shot missed.",r.hit?"success":"")});
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
  S.config=cfg;configureBranding(cfg.branding);configureStreets(cfg.streets_url);el("discordLogin").disabled=!cfg.discord_oauth;
  if(!cfg.discord_oauth)el("discordLogin").textContent="Discord login (not configured)";
  if(!cfg.underworld_assertions)el("underworldForm").querySelector("button").disabled=true;
  txt("sideStatus",(health.status||"unknown").toUpperCase());txt("sideStatusDetail","Isolated staging · "+cfg.season);
  await resume();
  const poll=()=>{if(!document.hidden&&!S.busy&&!S.bossPending)void refreshBossVisual()};
  setInterval(poll,30000);document.addEventListener("visibilitychange",poll);
  setInterval(()=>{if(!document.hidden)updateHqTimers()},1000);
  if(location.search.includes("login=ok"))notice("Discord login successful.","success");
  if(location.search.includes("linked=discord"))notice("Discord account linked to this character.","success");
  if(location.search.includes("discord=discard-offer")){
    el("accountTools").open=true;
    try{await loadDiscardOffer()}
    catch(e){notice("Cannot load Discord character confirmation: "+e.message,"error")}
  }
  if(location.search.includes("discord=conflict")){
    el("accountTools").open=true;
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
