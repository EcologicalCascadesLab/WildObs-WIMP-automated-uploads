# WildObs WIMP automated uploads

Upload camera-trap image folders to the [WildObs Image Management Platform (WIMP)](https://wimp.wildobs.org.au) through its API with one command, then verify and report every deployment. Developed by the Ecological Cascades Lab (University of Queensland) with Claude, October 2026.

WIMP is an Agouti instance. The API is documented at <https://api.wimp.wildobs.org.au/docs/>.

## What it does

`wimp_api.py` takes a project folder (one subfolder per camera, named as the WIMP location) and a deployment metadata CSV. For each camera it:

1. skips 0 KB files, hidden files (macOS `._*`), non-image files and invalid JPEGs. These make WIMP's import fail. The source folder is only ever read;
2. finds the empty ("Needs files") deployment for that location, or creates the location, camera, tag and deployment from the CSV row;
3. sets the deployment dates from the CSV (day-first dates, start 00:00, end 23:59) and warns if the image EXIF dates fall outside them;
4. uploads the images in parallel batches, with retries, and records progress so a run can be stopped and resumed;
5. switches on automatic AI, then finalizes the deployment, but only if every file uploaded;
6. reports each camera as `Camera | Images (sequences) | Current state`.

It can also add WIMP status columns to a camera tracking sheet (`status-sheet`).

## Setup

- Python 3 with `requests`.
- A WIMP API key: WIMP > User settings > API keys. Save it as one line in a file **outside any shared or synced folder**, for example `~/.wimp/prod.key`, and `chmod 600` it. Use a separate `test.key` for the test site. **Never commit a key.** `.gitignore` here excludes `*.key`.
- Metadata CSV with the columns `locationID, latitude, longitude, cameraID, cameraMake, deploymentStart, deploymentEnd, deploymentTags` (dates day-first).

## Use

```bash
# 1. confirm the key works
python3 wimp_api.py check --env prod

# 2. dry run: what would be uploaded, what is excluded, what is already there
python3 wimp_api.py upload "/path/to/project folder" --project "name fragment" --dry-run

# 3. upload (resumable; exit code 75 means run the same command again)
python3 wimp_api.py upload "/path/to/project folder" --project "name fragment" --workers 8 --max-seconds 999999

# 4. report
python3 wimp_api.py report --project "name fragment" --only CAM_01,CAM_02
```

Options: `--only cam1,cam2` limits the run to some cameras; `--metadata file.csv` if the CSV is not in or beside the folder; `--env test` targets the test site; `--key-file` points at the key; `--new-deployment` creates a replacement deployment for a camera whose existing one failed.

## What we learned about the API

| Topic | Finding |
|---|---|
| Base URLs | prod `https://api.wimp.wildobs.org.au/v1`, test `https://api.wimp.test.wildobs.org.au/v1` |
| Auth | `X-API-KEY: pk_...` (API key) or `Authorization: Bearer <session token>`; session tokens last one week |
| Upload | `POST /projects/{p}/deployments/{d}/upload`, multipart, field name `file`, several files per request (10 works). Response `{"duplicates":0,"failed":0,"processed":10,"success":true}` |
| Finalize | `POST .../finalizeUpload` queues sequence creation. Not possible to add files afterwards |
| AI | Finalize alone does not start the AI. `PATCH` the deployment with `{"automaticAi": true}` first and it starts after sequence creation |
| Status | `GET .../deployments/{d}/status` returns status, image and sequence counts, AI state and percent inspected |
| File list | `GET /projects/{p}/media.csv` lists every file per deployment; use it to find which images are missing |
| Not in the API | deleting a deployment; starting AI on an already finalized deployment (both need the web UI) |
| Speed | about 200 images a minute on our connection; sequences were created within minutes of finalize |

First run (5 October 2026, production): four cameras, 12,712 images, all present after import.

## Running a large upload from Terminal

Above roughly 5,000 images, run the upload in your own Terminal rather than through an AI assistant: it is resumable, needs no supervision and can run for hours. Keep an external drive connected until it finishes.

```bash
python3 -m pip install --user requests      # one-off; add --break-system-packages if pip says "externally managed"
cd "/path/to/scripts"
PYTHONDONTWRITEBYTECODE=1 python3 wimp_api.py upload "/Volumes/MyDrive/project folder" --project "name fragment" --workers 8 --max-seconds 999999
```

Rerunning the same command after a stop or an error loses nothing. Chain several folders with `&&`.

**Troubleshooting**

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'requests'` | `python3 -m pip install --user requests` |
| macOS Terminal opens then shows `login: /bin/CustomShellStaff: No such file or directory` / `[Process completed]` (seen on a university-managed Mac whose account login shell is a missing managed program; the Terminal shell settings can be locked) | Use **Shell > New Command...** in the Terminal menu bar, type `/bin/zsh -l` and click Run. Or use the VS Code integrated terminal |
| A dry run over a large external drive takes minutes | Normal: it lists every file. Run one project folder at a time |

## Other routes

`skills/` holds the instructions we give Claude for this work, including the Nextcloud sync route (`wimp-nextcloud-upload`), a manual-drag fallback, and the status-sheet report. They are written for our lab's setup and are shared as worked examples.

## Caveats

- Written against the API as of October 2026; endpoints may change.
- Check with your project coordinator before filling production deployments: cameras may be empty on purpose because they were processed elsewhere.
- No warranty. Test on the WIMP test site first.
