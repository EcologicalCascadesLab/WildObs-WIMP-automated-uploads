---
name: "wimp-nextcloud-upload"
description: "Upload camera-trap deployment folders to the WildObs WIMP production site via the Nextcloud sync folder and link each to its existing deployment. Use for 'upload cameras to WIMP', bulk WIMP uploads, or Nextcloud camera uploads."
---

# WIMP upload via Nextcloud (production)

Bulk route for getting camera folders into WIMP (wimp.wildobs.org.au, an Agouti instance). This is the default route for Claude because it is fully automated; `wimp-direct-upload` needs Matthew to drag files.

## Rule: originals are read-only

Never edit, rename, move or delete the original camera folders or images in their original location, whether that is an external drive or a folder already on the Mac. Only ever read from them and copy out of them. All fixes (e.g. dropping a 0-byte file) and all deletions happen on copies: the staging folder and the Nextcloud sync folder.

- **Source on an external drive:** copy to a local staging folder so the drive can be ejected, and delete that staging folder and its contents when finished (see steps 3 and 9).
- **Source already on the Mac's internal drive:** do not stage, move or delete anything. Copy straight from the original folder into the Nextcloud sync folder; the only thing to clean up afterwards is the sync-folder copy.

## Rule: never upload 0 KB files or hidden files

A 0-byte (0 KB) image makes WIMP's import end in "Failed creating sequences", and a failed deployment is then locked (see step 10). macOS `._IMAG0001.jpg` resource files do the same. Before any copy or upload, list 0-byte files (`find <folder> -type f -size 0`), hidden files (`find <folder> -name '.*'`) and anything that is not a JPG/AVI, and leave them out: `rsync -a --exclude='.*' --min-size=1`. After copying, re-run both `find` checks on the copy and on the Nextcloud sync folder; both must be empty before linking. Also check each JPG starts with FFD8 and has an EXIF timestamp. Report every excluded file by name. Never remove them from the original folder.

## Fixed facts

- **Production only.** WIMP: `https://wimp.wildobs.org.au`. Nextcloud web: `https://uploads.wimp.wildobs.org.au`. Never use `wimp.test`.
- **Local sync folder (macOS):** `~/Library/CloudStorage/Nextcloud-uploads.wimp.wildobs.org.au-<your-account>/`. `~/Nextcloud` is a dead folder that nothing syncs. A second folder `Nextcloud-uploads.wimp.test...` is the test site: do not touch.
- **Browser:** Claude built-in browser pane (not Chrome), signed in to WIMP (UQ SSO) and, in a second tab, to the Nextcloud web UI. Use `javascript_tool` for everything; avoid screenshots.
- Deployments normally already exist (created by CSV import) with status "Needs files". The job is linking files, not creating deployments (except the recreate in step 10).
- **AI classification is not reliably automatic.** The project setting (Settings > Automatic annotation) is on, but newly imported deployments do not always get queued. Every upload ends with the AI check in step 8.
- A Nextcloud folder that is linked to a deployment is hidden from the folder dropdown of every other deployment, and deleting a deployment also deletes its linked Nextcloud folder from the server.
- WildObs support: support@wildobs.org.au (Matthew writes "Hi team,"; draft only, never send).

## Folder access to request up front (one prompt)

Source folder (read only), `~/Library/CloudStorage`, and, only when the source is an external drive, a staging folder on the Mac (e.g. `~/CT images for WildObs upload`). Delete permission only on the staging folder and `~/Library/CloudStorage`, never on the source.

## Procedure

1. **Inventory (device shell, read only).** For each camera folder: file count, size, 0-byte files, hidden files, and first/last EXIF timestamp (regex `20\d\d:\d\d:\d\d \d\d:\d\d:\d\d` on the first 4 KB of each JPG). Read the deployment CSV row. Cameras with no folder (e.g. "SD card missing" in the CSV) are skipped and reported. Check free disk space on the Mac (`df -h`).
2. **Exclude 0-byte, hidden or non-image files from the copies** (see the rule above; never remove them from the source). Report which files were excluded.
3. **External drive only: free the drive first.** Create one staging folder (e.g. `<staging>/<survey> staging`). `rsync -a --exclude='.*' --min-size=1` every camera that fits in free space into it, verify file counts match the source (minus excluded files), then tell Matthew the drive can be ejected. Device shell calls time out at ~3 min: rerun the same rsync until rc=0. Track the staging folder's size (`du -sh`) and the Mac's free space after each batch and report them. Cameras too big for free space go straight from the drive into the sync folder, last, and Matthew is told the drive must stay connected for those.
4. **Copy into the sync folder**, one folder per deployment at the top level, named as the WIMP location, images flat (no subfolders). Copy from staging (external source) or directly from the original folder (internal source), again with `--exclude='.*' --min-size=1`. If Matthew has already put a folder in Nextcloud himself, run the 0-byte, hidden-file and subfolder checks on it before linking, and stage a copy of it first if it may be his only copy. Keep at most ~10 folders in Nextcloud at once.
5. **Wait for sync, checked on the server.** In the Nextcloud web tab run a WebDAV count:
   `fetch('/remote.php/dav/files/'+encodeURIComponent(OC.currentUser)+'/'+folder,{method:'PROPFIND',headers:{Depth:'1',requesttoken:OC.requestToken}})` and count `<d:href>` minus 1. 404 means not there yet. Proceed only when the count equals the local file count. Observed speed: about 300 images/min.
6. **Link in WIMP.** Open `/project/<projectId>/deployments/edit/<deploymentId>` (get IDs from the Deployments table: `tr.datatable-row-body`, the first cell's `title` is the full ID). Keep each JS call under ~40 s (the tool times out at 45 s), so split into two calls:
   - call 1: check the page's location name matches the camera; set the two `input[type=datetime-local]` values (native value setter + `input`/`change`/`blur` events); wait for the **Choose nextcloud directory** button (can take up to a minute to appear after page load); click it; open the `.ember-power-select-trigger` reading "Select Nextcloud Folder" with synthetic `mousedown`/`mouseup`/`click`, then do the same on the `.ember-power-select-option` whose text equals the folder name;
   - call 2: confirm the page shows "Files in <folder>:" then click **Save**.
7. **Verify the import.** Deployments table: status goes "Creating sequences" (10+ minutes is normal; 700+ images took over 30 minutes) then shows Sequences and Images counts. Images should equal the local file count; WIMP drops exact duplicate images, so a count one or two short is reported, not treated as a failure. The Nextcloud folder disappears from the server once imported.
8. **Make sure the AI is running on every uploaded deployment.** Once a deployment shows its Sequences and Images counts, read its Progress cell and its last (actions) cell in the Deployments table, `.ag-annotate-button`:
   - "in queue" in the Progress cell, or a robot icon titled "processing" (`img.ag-ai-state-processing`): the AI has it, nothing to do;
   - a robot icon titled "success" with "Annotate" and "Rerun AI" and a Progress percentage: the AI has finished;
   - an **"Annotate by AI"** button (`.ag-annotate-button-ai button`): it was NOT sent to the model automatically. Click it (a plain JS `.click()` works, no dialog), then re-read the row and confirm it changed to "in queue" / processing.
   Do this for every deployment uploaded in the run, after the last upload is done. Imports can take an hour or more for big cameras, so if some are still "Creating sequences" when the rest of the work is finished, schedule a follow-up check rather than skipping this step, and say so in the report.
9. **Clean up copies, late.** Keep each camera's staging copy and local sync copy until WIMP has confirmed BOTH that its sequences were created (Sequences and Images counts shown, images matching) AND that AI processing has begun (processing or finished, not merely "Annotate by AI" or still "Creating sequences"). Only then:
   - delete that camera's copy from staging and from the local sync folder (the sync copy only when the server already returns 404 for it, otherwise the delete propagates to the server);
   - when every camera has reached that point, delete the staging folder itself and all its contents, check with `ls` and `du` that it is gone and report the free space recovered. If any camera has not, keep its copy and say so.
   - Never delete or alter anything in the source location, external or internal.
10. **Sweep the project for problem deployments.** Read the whole Deployments table (page size 100, every page; confirm the number of distinct rows read equals the "of N results" total) and handle:
   - **Empty duplicates:** deployments with no location, no dates and no files (stray drafts, e.g. from "Add deployment" then Cancel). Always delete these without asking: open the edit page, confirm it is empty, click **Delete deployment**, set the dialog's text box to `delete` by JS (native value setter + `input`/`change`/`keyup` events; plain typing leaves the button disabled), click **Confirm removal**, and check the total drops by one.
   - **Failed deployments:** status "Failed creating sequences" / "Import failed", or an image count well off the source folder. For each:
     - **Diagnose:** find its source folder; check for 0-byte files, hidden `._` files, non-image or corrupt files, a file-count mismatch between source, Nextcloud and WIMP (the edit page's "N Files in directory" and its thumbnail file names show what WIMP actually ingested), and wrong, blank or reversed deployment dates.
     - **A failed deployment is locked:** its edit page offers only Save and Delete deployment, even after "Delete all files", so it cannot be uploaded again. When deleting and recreating is the only route left in the UI, always do it, without asking:
       1. Record the old deployment's ID and every field on its edit page (location, UTC offset, dates, tags, groups, camera identifier, heights/heading/tilt, bait, persons, notes). Where fields are blank, fill them from the deployment CSV row (tags, camera ID, setup person, day-first dates).
       2. Put a clean copy of the images in Nextcloud under a NEW folder name (e.g. `<location>_v2`), because the old folder is tied to the old deployment and is deleted with it; wait until the server count matches. Keep a staging copy until the new deployment is confirmed.
       3. Create the new deployment first: Deployments > **Add deployment**; fill Location, Tags, Camera identifier and Persons through their `.ember-power-select-trigger` dropdowns (open with synthetic mouse events, type into the search input, pick the exact option), set the dates, click **Choose nextcloud directory**, pick the new folder, confirm "Files in <folder>:" and click the form's **Add deployment** button.
       4. Then delete the old failed deployment (Delete deployment, set the box to `delete` by JS, Confirm removal). Deletion runs in the background for a minute or two; confirm the old ID is gone and only one deployment remains for that location.
       5. Verify the new one as in steps 7-8 and include it in the report as "recreated" with the old and new IDs and the cause.
     - Never delete a healthy deployment, or one whose images cannot be re-uploaded because the source is unavailable; report those instead.
     - If the recreate itself fails, stop, keep the copies, and draft (never send) an email to WildObs support in Matthew's voice with the project URL, deployment IDs, file counts, offending file names and what was tried.
11. **Report to Matthew in the chat when everything is done.** Lead with this table, one row per camera:

   | Camera | Images (sequences) | Current state |
   |---|---|---|
   | Koombooloomba_07_road | 222 (56) | AI done (91% progress) |
   | Koombooloomba_15_road | 629 (57) | AI running (74% progress) |
   | Koombooloomba_17_road | 670 (126) | AI in queue |
   | Koombooloomba_10_road | 5,196 expected | Creating sequences |

   - Middle column: images in WIMP with sequences in parentheses; before the import finishes, give the expected image count and say "expected".
   - "Current state" is one of: Needs files; Creating sequences; AI in queue; AI running (NN% progress); AI done (NN% progress); Failed creating sequences; No images (reason). Add a short suffix where it applies: "recreated", "clicked Annotate by AI", "1 image short of source".
   - Below the table, briefly: files excluded (0-byte, hidden); empty deployments deleted; deployments deleted and recreated (old ID, new ID, cause); any support email drafted; anything left for him; staging folder state (deleted, or what remains and its size); any follow-up check scheduled.

## Dates

- The deployment CSV is day-first (8/7/2025 = 8 July). Older imports read it month-first, giving wrong or reversed start/end. Always correct them from the CSV and cross-check against the EXIF range.
- The edit form's datetime inputs are UTC; the table displays AEST (+10). Enter start `T00:00` and end `T23:59` on the CSV dates; the table then shows 10:00 and next-day 09:59, which is expected.

## Troubleshooting

- **Nextcloud option missing on the edit page:** wait a minute and reload; check Project settings > "users can upload images from Nextcloud" is ticked (toggling it off/on and saving has fixed it); check the folder is actually on the server. If the deployment is in a failed state, see step 10.
- **Folder missing from the "Select Nextcloud Folder" dropdown:** it is already linked to another deployment (often the failed one). Use a new folder name.
- **Local folder not syncing to the web version:** quit and reopen the Nextcloud app on the Mac; that restarts the sync. Ask Matthew to do this. If one folder name will not re-sync after its server copy was deleted, copy it again under a new name.
- **A few files never arrive** (count stuck 1-7 short): re-copy just those files over themselves in the sync folder and `touch` them.
- **"Failed creating sequences" / "Import failed":** follow step 10.
- **Deployments table scraping:** paging is flaky. After clicking `<` or `>`, wait until the first row's ID changes before reading (the "Showing" text updates before the rows do); never click `<` or `<<` on page 1 (the table goes to "Showing -99-0" and must be reloaded); stop paging forward when the "Showing a-b of N" upper bound equals N; keep reading until the distinct rows read equal the total, reloading and retrying if not.
- Do not click "Add deployment" to explore: Cancel can leave an empty draft deployment (delete it per step 10 if it happens).
