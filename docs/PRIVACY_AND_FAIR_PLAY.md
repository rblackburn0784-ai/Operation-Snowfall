# Operation Snowfall — Privacy, Identity & Fair Play (organiser draft)

This is an unofficial **MafiaReturns community** game. Discord membership is not a proof of ownership of a MafiaReturns name. Registration is by **self-declaration**. No MafiaReturns passwords, session tokens or payment details are requested or stored.

## Data processed

- Discord user ID, declared MafiaReturns name, city affiliation and registration time;
- action and hit logs, cooldowns and resources, point history and time-limited game states;
- organiser audit entries and reasons for identity/score disputes;
- prize fulfilment notes (individual awards only).

The public boards show declared MR names, city affiliation and scores. Only staff/hosts can invoke exports, audits and correction tools. A TEST channel in the same server uses a separate disposable SQLite database and test-only scores.

## Identity disputes and moderation

Members should contact Kat or authorised staff to report impersonation, unfair play or accidental name claims. Staff can flag (temporarily ineligible for payouts), clear or disqualify a claim, with an auditable reason. Staff score corrections **append** a signed ledger row; original actions are never edited. Disputes and appeals should be resolved before host finalises prize exports. The leaderboard does not constitute automatic proof of prize entitlement.

## Fair-play limits

Thirty-second attack cooldown; target eligibility and inactivity protection; no self or same-city attacks; pair/day scoring limits; an anti-camping shield and KO immunity; one gift/day; item caps; capped PvP/PvE/quest awards. Automation, collusion, using alternative Discord accounts to evade limits or impersonating other players may result in staff review. Hosts must document corrections.

## Retention and deletion

**Kat must publish a specific retention deadline before registration opens.** During gameplay and the announced prize/appeal period, state and backups are retained for event operation and dispute resolution. The bot creates separate timestamped backups; **it does not automatically delete historical player data**. Staff must maintain a protected off-site backup, choose the retention period and schedule deletion of SQLite files, backups and exports after any legitimate appeal/payout needs end. Participants may request a copy or removal from Kat; existing game and anti-fraud evidence may require case review before deletion. Avoid storing personal information in audit reasons.

## Prizes

Prizes are for **individual players only**. City standings are for titles and bragging rights—never credits or perks. The bot exports a pending **individual-only** CSV; Kat manually assigns/delivers any MR rewards and records the outcome. No MR external API or payment transaction is used.

## Test environment

**TEST / NO PRIZES** in the designated testing channel is not an official event or award. Test participants self-declare in the disposable session; switching days retains test-only registrations. Ending a test deletes all temporary records by default, or a host may retain a private local archive for debugging, subject to the same privacy and retention obligations. No production participant data is copied into practice.
