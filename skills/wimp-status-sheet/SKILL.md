---
name: "wimp-status-sheet"
description: "Report every camera's WIMP status (prod or test) as new columns on a copy of a sign-up or tracking Google Sheet. Use for 'which cameras are on WIMP', 'full camera status report', 'update the WIMP status sheet'."
---

# WIMP camera status sheet

Produces a Google Sheet that copies a tracking sheet (one row per camera/deployment) and adds, per environment, two columns: `WIMP PROD status (<date>)` and `PROD images (sequences)` (or `TEST ...`). First run: 5 Oct 2026, built from the lab's volunteer sorting sheet.

## How

1. **Get the source rows as CSV.** If the sheet is link-readable: `https://docs.google.com/spreadsheets/d/<id>/export?format=csv&gid=<gid>` works with curl from the device shell. Otherwise export through the Drive connector.
2. **Get WIMP status and merge**, with the shared script (see `wimp-api-upload` for the script path and the key file):
   `python3 wimp_api.py status-sheet --env prod --project "<name fragment>" --source <csv or export URL> --out <out.csv>`
   It matches the sheet's `DeploymentID` (or `locationID`) column to WIMP location names, appends the two columns, adds rows for WIMP deployments missing from the sheet, and prints counts. For a second environment, run it again with `--env test` and the first output as `--source`.
3. **No key file?** If Matthew is signed in to that WIMP site in the Claude built-in browser, compute the status inside the page instead (the session token is used in place and never read out): fetch `/v1/projects/{id}/deployments`, `/locations` and each deployment's `/status` with the page's own session, return only a compact string `name,CODE,assets,sequences,aiState,pct;...` for deployments that are not WaitingForFiles (codes: W Q P F C AQ AP AF AC), save it as `{"n": <total>, "other": "<string>"}` and pass `--status-file`. Check first that the sheet's names and WIMP's location names are the same set, because with a status file every unlisted name is reported as "Needs files".
4. **Create the Google Sheet** from the output CSV with the Drive connector (`create_file`, `text/csv`, converted to a Sheet). Title: `<source title> - WIMP status report (<date>)`. The connector cannot edit an existing sheet; to update one in place, set up the Apps Script bridge from `google-sheets-editor` on that sheet, or create a new dated sheet.
5. **Tell Matthew** the counts by state and anything odd: duplicate rows in the source, cameras in WIMP but not in the sheet, deployments with sequences but no AI, image counts short of source.

## Status wording

Needs files; Creating sequences; Failed creating sequences; No images; AI in queue; AI running (NN% progress); AI done (NN% progress); AI failed; Sequences created, AI not run (NN% progress); No deployment in PROD/TEST. Progress is WIMP's percent of sequences inspected.

## Notes

- Only the Sheet1-style camera tab is copied; other tabs and cell formatting are not.
- "Needs files" in prod is expected for cameras the sheet lists as sorted on WildObs test or Wildlife Insights.
