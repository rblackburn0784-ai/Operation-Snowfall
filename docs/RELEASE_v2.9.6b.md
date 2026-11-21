# v2.9.6b — Hero Layout Correction & HQ Card Scaling

QA website only. Restore the original v2.9.6 illustrated Snow Don introduction and
move the supplied 2048x682 artwork into the top navigation branding, replacing
the small text title. Preserve the circular Snow Don brand icon and favicon.

HQ uses a 340px desktop square portrait well and a stacked, larger mobile
layout (up to 300px). Original square frame artwork is rendered without
stretching, with a slightly expanded overlay and minimal outer mat. Portrait,
frame, banner, gear, and trail remain driven by owned and equipped shared
wardrobe data. No purchase, gear, score, identity, or prize logic changes.

Only deploy Snowfall-Web-QA. Verify /v1/web/config version 2.9.6b and both
branding flags, original hero artwork, actual header logo width, square HQ
frame, mobile viewport overflow and all five wardrobe layers. The Discord and
Underworld services and PostgreSQL settings stay unchanged.

Rollback: pin the web service back to db324d6fcc32b528fde837317931138a6dde126c.
