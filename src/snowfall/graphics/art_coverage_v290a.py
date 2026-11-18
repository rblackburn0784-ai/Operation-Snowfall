#!/usr/bin/env python3
"""Executable per-image render-path coverage check for Snowverhaul v2.9.0a.

Rather than searching filenames in source comments, drive the actual render functions
through the expected user-visible states and intercept every artwork request.
Production artwork is separately verified by verify_v290.py; this audit uses
lightweight placeholder images to avoid building dozens of full-size PNGs.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from io import BytesIO
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

from PIL import Image, ImageDraw

PACKAGE = Path(__file__).resolve().parent
MANIFEST = (PACKAGE/'art/v290/_manifest.json'
            if (PACKAGE/'art/v290/_manifest.json').is_file()
            else PACKAGE/'payload/asset_manifest.json')
SIX_CITIES=('Chicago','New York','Detroit','Philadelphia','Las Vegas','Los Angeles')
EIGHT_ITEMS=('snowball','golden','bomb','cocoa','mittens','fort','siege','boss')
MODES=('gallery','safe','snowman','catch','trivia')


def audit(project: Path, *, report_path: Path | None = None):
    project=project.resolve()
    art=project/'src/snowfall/graphics/art/v290'
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    expected={entry['asset'] for entry in manifest['assets']}
    if len(expected)!=len(manifest['assets']):
        raise AssertionError('Duplicate art asset names in manifest')
    if not art.is_dir():
        raise AssertionError('Missing v2.9.0a artwork: run the installer first')
    sys.path.insert(0,str(project/'src'))
    from snowfall.graphics import snowverhaul as sv
    from snowfall.graphics import cards
    from snowfall.services.achievements import TROPHIES, BADGE_RARITIES
    if not sv._APPLIED:
        raise AssertionError('Snowverhaul activation hook is not active')

    # Confirm the exact installed bytes, not just existing filenames.
    for entry in manifest['assets']:
        file=art/entry['asset']
        if not file.is_file():raise AssertionError(f'Missing art asset {entry["asset"]}')
        raw=file.read_bytes()
        if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:
            raise AssertionError(f'Asset integrity error {entry["asset"]}')
    observed=defaultdict(set)
    current=['unknown']
    small=Image.new('RGBA',(960,540),(18,34,51,255))
    buf=BytesIO();small.convert('RGB').save(buf,'PNG');stub_bytes=buf.getvalue()
    saved_source, saved_paste, saved_image, saved_finish=(sv._source,sv._paste,sv._image,sv._finish)
    saved_orig=dict(sv._ORIG)
    saved_canvas=cards._canvas

    def record(path):
        observed[str(path)].add(current[0])

    def pseudo_source(path):
        record(path)
        return Image.new('RGBA',(8,8),(255,255,255,255))

    def pseudo_paste(canvas,path,box,*,fit=False,opacity=255):
        record(path)
        return True

    def pseudo_image(path,size=None,*,fit=False):
        record(path)
        return Image.new('RGBA', size or (960,540), (20,36,54,255))

    def pseudo_canvas(city,title,subtitle):
        im=Image.new('RGBA',(960,540),(18,34,51,255))
        return im, ImageDraw.Draw(im,'RGBA')

    @contextmanager
    def calling(name):
        prior=current[0];current[0]=name
        try:yield
        finally:current[0]=prior

    def call(name,fn,*args,**kw):
        with calling(name):
            return fn(*args,**kw)

    # Mask only the old card renderers, not the new drawing functions under audit.
    # This keeps the test independent of arbitrary real scoreboard statistics.
    for k in list(sv._ORIG):
        sv._ORIG[k]=lambda *args,**kwargs:stub_bytes
    # The old raid-board and arcade-lobby functions are installed in v2.9.0a.
    assert 'raid.raid_board_card' in sv._ORIG
    assert 'arcade.lobby_card' in sv._ORIG
    sv._source=pseudo_source
    sv._paste=pseudo_paste
    sv._image=pseudo_image
    sv._finish=lambda image:stub_bytes
    cards._canvas=pseudo_canvas
    try:
        for n,style in enumerate(('recruit','noir_detective','winter_enforcer','frost_spectre',
                                  'recruit_f','noir_detective_f','winter_enforcer_f','frost_spectre_f')):
            frames=('ice_frame','gold_frame','holly_frame')
            banners=('midnight_banner','aurora_banner','gilded_banner')
            gear=('goggles','scarf','boots')
            eq={'portrait':style,'frame':frames[n%3],'banner':banners[n%3],
                'gear':gear[n%3],'trail':('snow_trail' if n%2 else 'candy_trail')}
            showcase=NS(player=NS(city='Chicago',mr_username='Example'),title='Snowball Recruit',
                best_rarity='Epic',resources=NS(warmth=95,snowballs=9,today_pvp=5,snowflakes=20),
                points=20,equipped=eq,featured_badges=(),badge_count=0,badge_total=16,
                owned_count=8,cosmetic_total=22,arcade_stamps=())
            call('Player profile ('+style+')',sv._showcase,showcase)

        trophies=tuple(NS(key=t.key,badge=t.badge,rarity=BADGE_RARITIES[t.key],
                          progress=t.required,target=t.required,unlocked=True) for t in TROPHIES)
        call('Trophy Cabinet (all unlocked)',sv._trophy_cabinet,
             NS(city='Chicago',player_name='Example',equipped_title='Snowball Rookie',trophies=trophies))
        call('Shop',sv.shop_card,NS(balance=99))
        call('Champions',sv._champions,[],[])

        for category in ('miss','snowball_impact','critical_hit','knockout'):
            hit=category!='miss';critical=category=='critical_hit';knockout=category=='knockout'
            result=NS(hit=hit,critical=critical,knocked_out=knockout,
                      armour_damage=8 if hit else 0,style='regular')
            beat=NS(streak=4) if category=='snowball_impact' else None
            call('PvP '+category,sv._battle,result,'Opponent',beat=beat)
        for hp in (82,19,0):
            call('Fortress HP '+str(hp),sv._world_result,
                 NS(kind='siege',hp_after=hp,max_hp=100))
        call('Defeated Snow Don',sv._world_result,
             NS(kind='boss',hp_after=0,max_hp=100))
        call('Cooperative raid',sv._raid_board,
             NS(enabled=True,contributors=3),viewer_id=123,city='Chicago')

        colours=('#ec6f70','#74aee6','#bd9ee7','#ffd084','#ec99d9','#91dcba')
        banners=tuple(NS(city=c,colour=col,motto='Test',home_district='Home',
                         active=1,registered=2,rally_marks=1) for c,col in zip(SIX_CITIES,colours))
        by_city={b.city:b for b in banners}
        board=NS(viewer_city='Chicago',day=1,banners=banners,matches=(),districts=(),
                 banner=lambda city:by_city[city])
        call('City map',sv._territory_map,board)
        call('Six city crests',sv._banners,board)
        for city in SIX_CITIES:
            won=NS(city_a=city,city_b='Detroit' if city!='Detroit' else 'Chicago',
                   rally_owner=city,duel_owner=None)
            board_won=NS(matches=(won,))
            call('City '+city+' victory',sv._city_territory,board_won,city)
        lost=NS(city_a='Chicago',city_b='Detroit',rally_owner='Detroit',duel_owner=None)
        call('City Chicago defeat',sv._city_territory,NS(matches=(lost,)),'Chicago')

        for day in range(1,8):
            clue=NS(label='Footprints',found=(day%2==0))
            snap=NS(case=NS(day=day,title='Mystery '+str(day)),clues=[clue,clue,clue],
                    guesses=1,solved=False,secret=None,secret_ready=False)
            call('Mystery day '+str(day),sv._case_file,snap)
        history=tuple(NS(day=d,title='Case '+str(d),clues=1,solved=False,secret=False)
                      for d in range(1,8))
        call('Seven-day casebook',sv._casebook,
             NS(history=history,solved_count=0,souvenirs_count=0))
        call('Secret encounter',sv._secret,NS(day=1,secret=None))

        for mode in MODES:
            call('Arcade '+mode,sv._arcade,
                 NS(current=True,mode=mode,title=mode,score=10,step=1,total_rounds=5))
        records=tuple(NS(name=mode.title(),mode=mode,personal_best=30,attempts_today=1)
                      for mode in MODES)
        call('Illustrated arcade lobby',sv._arcade_lobby,
             NS(day=1,records=records,completed=3,stamps=('gallery',)))

        call('Wire daily front',sv._wire_front,None,NS(day=1,recent=()),'Chicago')
        article=NS(category='City Rivalry',title='Cities Rally',detail='Honorary city contest')
        call('Wire city report',sv._wire_front,NS(day=3,headline='City Rivals',verified=[article]))
        call('Wire final edition',sv._wire_front,NS(day=7,headline='Winter Finale',verified=[]))
        stories=[NS(day=2,title='A Letter from the Alley',author='Player',city='Chicago')]
        call('Wire player letters',sv._wire_stories,stories)
        call('Wire dispatch',sv._wire_report,NS(leading_city='Chicago'))

        boss_assets=[p.rsplit('/',1)[1].replace('.webp','') for p in sorted(expected)
                     if p.startswith('boss/')]
        call('Boss transition and finale scenes',sv._gif_from_scenes,boss_assets,
             'THE SNOW DON HAS FALLEN!',4_000_000)

        # Pack B actually replaces and is loaded through the EXISTING icon renderer.
        # This is intentionally not a manually registered path: spy on real Image.open.
        from PIL import Image as PILImage
        open_original=PILImage.open
        def observe_icon(fp,*a,**kw):
            path=Path(fp) if isinstance(fp,(str,Path)) else None
            if path is not None and path.parent==project/'src/snowfall/graphics/art/items':
                record('items/'+path.name)
            return open_original(fp,*a,**kw)
        PILImage.open=observe_icon
        try:
            with calling('Actual Pack B item icon renderer'):
                canvas=Image.new('RGBA',(960,540),(14,30,44,255))
                for item in EIGHT_ITEMS:
                    installed=project/'src/snowfall/graphics/art/items'/f'{item}.png'
                    original=art/'items'/f'{item}.png'
                    if not installed.is_file() or installed.read_bytes()!=original.read_bytes():
                        raise AssertionError(f'Old/incorrect legacy item image: {item}')
                    cards._icon(canvas,item,(10,10),size=40)
        finally:
            PILImage.open=open_original
    finally:
        sv._source,sv._paste,sv._image,sv._finish=saved_source,saved_paste,saved_image,saved_finish
        cards._canvas=saved_canvas
        sv._ORIG.clear();sv._ORIG.update(saved_orig)
    missing=sorted(expected-set(observed))
    dangling=sorted(set(observed)-expected)
    report={
       'release':'2.9.0a','expected_assets':len(expected),
       'covered_assets':len(expected-set(missing)),
       'uncovered':missing,'unrecognized_paths':dangling,
       'references':{p:sorted(observed[p]) for p in sorted(expected)},
       'note':'Each entry was requested by a driven runtime renderer path; physical PNG checksums independently verified. Not a live Discord UI test.'
    }
    if report_path:
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if missing or dangling:
        raise AssertionError(f'ARTWORK COVERAGE FAILED: {len(missing)} unused, {len(dangling)} invalid paths\n'
                             + '\n'.join('UNUSED '+p for p in missing)
                             + '\n'.join('UNKNOWN '+p for p in dangling))
    print(f'PASS: {len(expected)}/{len(expected)} images have exercised renderer paths')
    return report

if __name__=='__main__':
    project=Path(sys.argv[1]) if len(sys.argv)>1 else Path('.')
    audit(project,report_path=project/'snowverhaul_v290a_coverage.json')
