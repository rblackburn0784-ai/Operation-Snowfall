# v2.9.8b3 — Persistent right-hand chat and mobile drawer

The existing WidgetBot iframe is moved out of the Community page and into the always-mounted sidebar. Only one iframe is present in the DOM. Desktop's top sidebar card is a sticky #the-streets chat; all original radio, community, status, and rules cards remain below. Wide layouts allocate up to 410px to the chat sidebar, with at least 340px at supported desktop sizes. The sticky top clearance accounts for the website's persistent resource bar.

On devices narrower than 981px, a floating Chat button opens the same iframe in a right-side drawer over the current page, rather than moving or recreating it. Closing the drawer keeps the WidgetBot session loaded. Explicit Disconnect or account change unloads it. Backdrop and Escape close the drawer; visibility and body scrolling are restored after close.

The in-page Streets article now directs players to this dock. All existing chat entry buttons open the dock directly; they don't navigate away from gameplay. Clicking chat is an opt-in external WidgetBot connection, protected by the existing Underworld identity gate. Discord channel URL remains configured via SNOWFALL_DISCORD_STREETS_URL. No chat mirroring, API secrets, migration, DB mutations, score updates or Discord worker changes.

Browser QA checks chat presence on the persistent aside, URL validation, actual iframe reuse when navigating between Community and Combat, mobile drawer reopening, account-change disconnect, sidebar geometry, 320px and 390px viewport overflow, and existing gameplay regression tests. WidgetBot itself is stubbed in automated browser tests; real two-way message tests remain a manual acceptance step.
