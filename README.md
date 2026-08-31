# safeflight-il-data

Live data feed for **SafeFlight IL** (drone flight planner). This repo holds `notams.json`,
refreshed on a schedule by a GitHub Action from the IAA Mobile AeroInfo public NOTAM service.

The app fetches `notams.json` from this repo's raw URL directly in the browser (CORS-open),
so temporary flight restrictions stay current without redeploying the app.

- Source: https://brin.iaa.gov.il/MobileAeroinfo/maiNotam.aspx (public, government aeronautical info)
- Refresh: every 3 hours via `.github/workflows/notams.yml`
- Data only. No app code here.
