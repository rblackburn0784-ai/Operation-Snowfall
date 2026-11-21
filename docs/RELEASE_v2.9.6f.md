# v2.9.6f — City Wars & World Map Visual Expansion

Original Discord map with its original six landmark coordinates, all six city skylines, crests and district banners, and completed-day victory/defeat artwork. Select cities and available days; display dynamic rivalry links, strongholds, frontier control, rally marks, scored hits, cooperative missions, quorum and season standings. Ties stay neutral; live results are not final victories. Official points retain two-decimal precision and are separate from territory honours.

Staging GET /v1/web/territory returns only aggregate data from the existing TerritoryEngine, with no viewer identity or private missions; original Discord registration checks remain intact. No new gameplay writes or prize changes. Existing standby, paused and historical day behavior follows the engine. QA website only, rollback to 643f147d102a42c17bbeac801fb3d06fb2efd328.
