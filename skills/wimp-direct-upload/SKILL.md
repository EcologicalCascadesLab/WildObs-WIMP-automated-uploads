---
name: "wimp-direct-upload"
description: "Manual-drag fallback for putting one small camera folder into a WildObs WIMP production deployment through the edit-deployment page. Use only when both the API route (wimp-api-upload) and Nextcloud are unavailable."
---

# WIMP direct upload by drag (fallback)

For automated direct upload use `wimp-api-upload`: the WIMP API has a documented upload endpoint (found 5 Oct 2026) and that skill needs no dragging. For bulk work without an API key use `wimp-nextcloud-upload`, which also holds the shared facts (production URLs, date rules, verification, troubleshooting). This skill remains only for the case where Matthew wants to drag files into the page himself.

## Rules

- Originals are read-only: never edit, rename, move or delete camera folders or images in their original location. External source: copy to a local staging folder, track its size, delete it when finished. Internal source: no staging, nothing to clean up.
- Never upload 0 KB or hidden files (they end in "Failed creating sequences" and lock the deployment). Copy with `rsync -a --exclude='.*' --min-size=1`, then re-check with `find <folder> -type f -size 0` and `find <folder> -name '.*'`; check each JPG starts with FFD8. Report every excluded file by name.

## Why Claude cannot do the drag

The built-in browser pane has no file-upload tool, the Chrome extension's upload is capped at 10 MB per call, and dragging from Finder into a browser by screen control is blocked (tried 4 Oct 2026). The hand-off is one drag per camera by Matthew.

## Procedure

1. **Prepare (device shell, read only on the source):** inventory the folder (count, size, 0-byte and hidden files, EXIF date range), read the CSV row, check free disk space. External source: rsync into one staging folder, verify counts, report its size, tell Matthew the drive can be ejected. Internal source: no copy; tell Matthew which files to leave out of the drag.
2. **Open the edit page** `/project/<projectId>/deployments/edit/<deploymentId>` in the Claude browser pane and check the location name.
3. **Set the dates** from the CSV (day-first; inputs are UTC; start `T00:00`, end `T23:59`) by JS. Do not save yet.
4. **Ask Matthew to drag the images** onto "Select files / drag and drop", giving the exact Finder path. Open one tab per camera so he can do all drags in one go.
5. **Watch progress by JS** until the upload bar completes; read duplicate or failed-file messages. The tab must stay open.
6. **Click Save** after the upload finishes; verify in the Deployments table: "Creating sequences", then Images = expected count (one or two short is reported, not a failure).
7. **AI, clean-up, sweep and report:** exactly as steps 8 to 11 of `wimp-nextcloud-upload` (click "Annotate by AI" if not queued; keep staged copies until sequences exist and AI has begun; delete empty duplicates; delete and recreate locked failed deployments; report with the Camera | Images (sequences) | Current state table).

## Notes

- Accepted types: JPG and AVI (input also accepts MP4/MOV).
- Same-named files from different folders are flagged as duplicates on this route.
- Abandoned, unsaved uploads leave stale files later flagged as duplicates; the edit page's "Delete all files" clears them.
