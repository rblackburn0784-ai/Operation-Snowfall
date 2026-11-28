# v2.9.10a — The Winter Underworld: Explorable City

- Open the city atlas from Winter Activities. The existing office, hotel and market open on day one; station, ice house, post office, press room, telegraph office and Christmas square unlock on days two through seven. The original loading bay retains its key requirement.
- Nine city souvenirs and a concealed hotel archive provide reasons to explore. The hidden location and its gated interaction are not returned until the player discovers the entrance.
- City navigation, visited locations and discoveries persist in the existing adventure record. Existing dispatch saves are upgraded on read without resetting the original chapter; completion does not prevent city exploration.
- Travel and discovery are server-validated by canonical player, event phase/day, revision, epoch and request identity. QA day rewinds block future locations; QA reset/restart clears the same adventure table. No official scoring, currency, prizes, arcade or Discord activity changes.
- Desktop schematic atlas and mobile-friendly location layout; original illustrations and existing mystery artwork are reused. Bespoke city artwork and the seven full investigations are deferred to subsequent releases.
- Added SQLite, PostgreSQL and browser regression checks for location gates, saved progress, secret discovery, replay protection and reset compatibility.
