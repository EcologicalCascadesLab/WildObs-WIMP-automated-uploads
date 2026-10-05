---
name: "wimp-api-upload"
description: "Upload camera-trap folders to WildObs WIMP (prod or test) through the WIMP API with one command: folder path plus metadata CSV in, deployments populated, verified and reported. Use for 'upload this camera folder to WIMP', API or direct upload, overnight batches."
---

# WIMP upload via the API

One command takes a project folder (one subfolder per camera, named as the WIMP location) and its metadata CSV, and leaves every camera uploaded, finalized, verified and reported. No Nextcloud, no staging copy, no dragging. Sister skills: `wimp-nextcloud-upload` (holds the UI facts: date rules, AI button, delete-and-recreate in the UI) and `wimp-status-sheet` (whole-project status in a Google Sheet).

STATUS (5 Oct 2026): working end to end on PROD. DTNP_02_bush (520), DTNP_02_road (3,438), DTNP_03_road (3,549) and DTNP_04_road (5,205) uploaded with every image present and sequences created within minutes of finalize.

## Fixed facts

- Script: `~/Dropbox/WildObs master folder/WildObs_Image_Platform_Workshop_Resources/WIMP upload skills/scripts/wimp_api.py` (Python 3 + `requests`). Run it in the device shell with `PYTHONDONTWRITEBYTECODE=1`.
- API docs: https://api.wimp.wildobs.org.au/docs/ (OpenAPI JSON at `/docs/openapi.json`). Base URLs: prod `https://api.wimp.wildobs.org.au/v1`, test `https://api.wimp.test.wildobs.org.au/v1`. Default is prod; test only when Matthew says so.
- Endpoints used: `GET /me/projects`, `GET /projects/{p}/deployments|locations|cameras`, `GET .../deployments/{d}/status`, `PATCH .../deployments/{d}` (dates, `automaticAi`), `POST .../deployments/{d}/upload` (multipart), `POST .../deployments/{d}/finalizeUpload`, `DELETE .../deployments/{d}/uploads` (clear before finalize), `POST /projects/{p}/deployments|locations|cameras`, `POST /projects/{p}/tags/resolve`, `GET /projects/{p}/media.csv` (file names per deployment). There is no API call to delete a deployment.
- **Upload format (confirmed):** multipart field name `file`, repeated for several files per request (10 per request works). Response: `{"duplicates":0,"failed":0,"processed":10,"success":true}`.
- **AI:** finalize alone does NOT start the AI. PATCH `{"automaticAi": true}` on the deployment before `finalizeUpload` (the script does this) and the AI starts by itself after sequence creation. A deployment finalized without it needs "Annotate by AI" clicked in the Deployments table.
- **Speed:** about 2.5 to 3.5 images a second (roughly 200 a minute, limited by the uplink; more than 8 workers does not help). Sequence creation after finalize took only a few minutes even for 3,500 images, much faster than the Nextcloud route.
- Status values: WaitingForFiles, SequenceCreationQueued/InProgress/Failed/Completed, AIAnnotationQueued/InProgress/Failed/Completed. The script turns them into the report wording.
- Reference implementation by the BHA developer: a private WildObs repository (not reproduced here).

## Key file

The script reads `~/CT images for WildObs upload/.wimp/prod.key` and `test.key` (one line each; never in Dropbox).

- An API key (`pk_...`) from WIMP > User settings > API keys goes in the `X-API-KEY` header and does not expire weekly. prod.key was saved on 5 Oct 2026.
- Also accepted: a session token (JWT), sent as `Authorization: Bearer`; these last one week from login.
- Claude does not read tokens out of the browser session. If the script prints `KEY:` or `AUTH:`, ask Matthew for a fresh key; if he gives it in chat, write it to the key file (chmod 600) and do not repeat it.

## Folder access to request (one prompt)

The project folder(s) (read only; the AWT 2025 cameras are split across "AWT cam trap 2025 FC1" and "FC2" on the Luskin 2026 drive), `~/CT images for WildObs upload` (key and state files) and the workshop resources folder (script, reports).

## Procedure

1. **Check.** `python3 wimp_api.py check --env prod` must print his name and projects.
2. **Dry run.** `python3 wimp_api.py upload "<folder>" --dry-run [--metadata <csv>] [--only cam1,cam2] [--project "<name fragment>"]`. The metadata CSV is found automatically if it sits in or beside the folder (header contains `locationID`). Read the output: files per camera, exclusions, cameras with no folder, cameras already complete, count mismatches.
3. **Upload.** Same command without `--dry-run`, `--workers 8`.
   - Device shell calls are cut off at 180 s and background processes (nohup) do NOT survive the call, so each call is time-boxed and resumable: exit code 75 means "run the same command again". Use `--max-seconds 150` (125 when a camera is about to finish, because finalize plus the next camera's inventory must fit before the cut-off). A timed-out call loses nothing; just run it again.
   - That is about 450 images per call. **For more than about 5,000 images, do not loop in chat** (each call re-reads the whole conversation): give Matthew the one-line Terminal command with `--max-seconds 999999` to run on the Mac, or run the loop in a fresh, short session. Then come back for step 4.
   - Per camera the script: excludes 0 KB, hidden and non-image files and invalid JPEGs (source is only read); finds the WaitingForFiles deployment for that location, or creates location, camera, tag and deployment from the CSV row; sets dates from the CSV (day-first, start `T00:00`, end `T23:59` UTC) and warns if EXIF dates fall outside them; uploads in parallel batches of 10 with retries, falling back to one file at a time; sets `automaticAi`; finalizes only if every file went up; records everything in `.wimp/state/<env>_<projectId>.json`.
   - It reads straight from the source, so an external drive must stay connected until the upload finishes, and no disk space is used on the Mac.
4. **Verify and report.** `python3 wimp_api.py report --env prod --only ...` prints the standard table (Camera | Images (sequences) | Current state) and notes.
5. **Fix what the report flags, without asking:**
   - *AI not started* ("Sequences created, AI not run" and 0% progress): click **Annotate by AI** on that row in the Deployments table (see `wimp-nextcloud-upload` step 8). A deployment at 100% progress with no AI state was annotated by a person; leave it.
   - *One or two images short of source*: note it in the report and move on; Matthew ignores these.
   - *Many images short of source*: use `media.csv` to list the missing file numbers and report them with the cause if known; recreate (`upload ... --only <cam> --new-deployment`, verify, then delete the old one in the UI) only if Matthew asks.
   - *Failed creating sequences* or *upload-incomplete*: diagnose from the state file's `failed` entries, then recreate as above.
   - *extra empty deployments*: delete them in the UI (`wimp-nextcloud-upload` step 10).
   - *count-mismatch* on a deployment that already had images before this run: report it, do not touch it.
6. **Report to Matthew in chat**: the table first, then exclusions, recreated deployments (old ID, new ID, cause), anything left for him, and any follow-up check scheduled. Save a dated report in the workshop resources folder when the run is more than a couple of cameras.

## Rules carried from the other WIMP skills

Originals are read-only. Never upload 0 KB or hidden files. Production unless told otherwise. Work in the Claude built-in browser, not Chrome, whenever the UI is needed. Before uploading a camera to prod, check the status sheet: cameras that already have images on TEST or were sorted on Wildlife Insights are usually empty in prod on purpose; upload them to prod only when Matthew names them.
