#!/usr/bin/env python3
"""WIMP (WildObs Image Management Platform / Agouti) API helper.

Subcommands
  check         confirm the key works and list projects
  upload        upload camera folders to their deployments, finalize, verify
  report        print the Camera | Images (sequences) | Current state table
  status-sheet  add WIMP status columns to a sign-up sheet CSV

API docs: https://api.wimp.wildobs.org.au/docs/
Key file: one line, either an API key (pk_...) or a session token (JWT).
Never print the key. Originals are only ever read.
"""
import argparse, csv, io, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import requests

BASES = {"prod": "https://api.wimp.wildobs.org.au/v1",
         "test": "https://api.wimp.test.wildobs.org.au/v1"}
MEDIA_EXT = {".jpg", ".jpeg", ".avi", ".mp4", ".mov"}
FIELD_CANDIDATES = ["files", "file", "images", "image", "files[]"]
EXIF_RE = re.compile(rb"(20\d\d):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)")


class Api:
    def __init__(self, env, key_file):
        self.env, self.base = env, BASES[env]
        key = Path(key_file).expanduser().read_text().strip()
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        self.h = {"X-API-KEY": key} if key.startswith("pk_") else {"Authorization": "Bearer " + key}
        self.s = requests.Session()

    def call(self, method, path, tries=4, **kw):
        last = None
        for i in range(tries):
            try:
                r = self.s.request(method, self.base + path, headers=self.h, timeout=kw.pop("timeout", 120), **kw)
            except requests.RequestException as e:
                last = str(e); time.sleep(3 * (i + 1)); continue
            if r.status_code == 401:
                sys.exit("AUTH: key rejected or expired (401). Save a fresh key to the key file and re-run.")
            if r.status_code >= 500 and i < tries - 1:
                last = f"{r.status_code} {r.text[:200]}"; time.sleep(3 * (i + 1)); continue
            return r
        raise RuntimeError(f"{method} {path} failed: {last}")

    def get(self, path):
        r = self.call("GET", path)
        if r.status_code != 200:
            raise RuntimeError(f"GET {path}: {r.status_code} {r.text[:300]}")
        return r.json()


def state_label(st):
    """Map an API status object to the wording used in run reports."""
    s, n = st.get("status"), int(st.get("nrAssets") or 0)
    ai, pct = st.get("aiModelState"), round(st.get("percentInspected") or 0)
    if s == "WaitingForFiles": return "Needs files"
    if s in ("SequenceCreationQueued", "SequenceCreationInProgress"): return "Creating sequences"
    if s == "SequenceCreationFailed": return "Failed creating sequences"
    if s in ("Invalid", "Unknown") or s is None: return str(s)
    if n == 0: return "No images"
    if s == "AIAnnotationFailed" or ai == "failed": return "AI failed"
    if s == "AIAnnotationQueued" or ai in ("scheduled", "queued"): return "AI in queue"
    if s == "AIAnnotationInProgress" or ai == "processing": return f"AI running ({pct}% progress)"
    if ai == "success" or s == "AIAnnotationCompleted": return f"AI done ({pct}% progress)"
    return f"Sequences created, AI not run ({pct}% progress)"


def images_label(st):
    n = int(st.get("nrAssets") or 0)
    return f"{n:,} ({int(st.get('nrSequences') or 0):,})" if n else ""


def pick_project(api, hint, names=()):
    projects = api.get("/me/projects")
    if hint:
        m = [p for p in projects if p["id"] == hint or hint.lower() in p["name"].lower()]
        if len(m) != 1:
            sys.exit("PROJECT: --project matched %d projects. Yours: %s" % (len(m), "; ".join(p["name"] for p in projects)))
        return m[0]
    best, score = None, 0
    for p in projects:
        locs = {l["name"] for l in api.get(f"/projects/{p['id']}/locations")}
        k = len(locs & set(names))
        if k > score: best, score = p, k
    if not best:
        sys.exit("PROJECT: no project has locations matching these cameras; pass --project. Yours: " + "; ".join(p["name"] for p in projects))
    return best


def project_status(api, pid):
    """-> {location name: [ {id, dep, st} ... ]}"""
    deps = api.get(f"/projects/{pid}/deployments")
    locs = {l["id"]: l["name"] for l in api.get(f"/projects/{pid}/locations")}
    def one(d):
        return d, api.get(f"/projects/{pid}/deployments/{d['id']}/status")
    out = {}
    with ThreadPoolExecutor(8) as ex:
        for d, st in ex.map(one, deps):
            out.setdefault(locs.get(d.get("location"), "(no location)"), []).append({"id": d["id"], "dep": d, "st": st})
    return out


# ---------------------------------------------------------------- inventory
def inventory(folder):
    good, bad = [], []
    for p in sorted(Path(folder).rglob("*")):
        if not p.is_file(): continue
        rel = p.relative_to(folder)
        if any(part.startswith(".") for part in rel.parts): bad.append((str(rel), "hidden")); continue
        if p.suffix.lower() not in MEDIA_EXT: bad.append((str(rel), "not an image/video")); continue
        if p.stat().st_size == 0: bad.append((str(rel), "0 KB")); continue
        if p.suffix.lower() in (".jpg", ".jpeg"):
            with open(p, "rb") as f: head = f.read(2)
            if head != b"\xff\xd8": bad.append((str(rel), "not a valid JPEG")); continue
        good.append(p)
    return good, bad


def exif_time(p):
    try:
        with open(p, "rb") as f: m = EXIF_RE.search(f.read(65536))
        return datetime(*map(int, m.groups())) if m else None
    except Exception:
        return None


def parse_day_first(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try: return datetime.strptime(s.strip(), fmt)
        except ValueError: pass
    return None


def find_metadata(folder):
    c = []
    for p in list(Path(folder).glob("*.csv")) + list(Path(folder).parent.glob("*.csv")):
        try:
            head = p.read_text(errors="ignore")[:400]
        except Exception:
            continue
        if "locationID" in head: c.append(p)
    return c[0] if c else None


def read_metadata(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["locationID"].strip(): r for r in csv.DictReader(f) if r.get("locationID")}


# ---------------------------------------------------------------- upload
def upload_cmd(a):
    t0 = time.time()
    api = Api(a.env, a.key_file)
    root = Path(a.folder).expanduser()
    if not root.is_dir(): sys.exit(f"FOLDER: {root} not found (drive not mounted?)")
    cams = [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        missing = want - {c.name for c in cams}
        cams = [c for c in cams if c.name in want]
        for m in sorted(missing): print(f"NOFOLDER {m}: no folder of that name in {root}")
    meta_path = Path(a.metadata).expanduser() if a.metadata else find_metadata(root)
    meta = read_metadata(meta_path) if meta_path else {}
    print(f"metadata: {meta_path} ({len(meta)} rows)")
    proj = pick_project(api, a.project, [c.name for c in cams])
    pid = proj["id"]
    print(f"project: {proj['name']} [{a.env}]")
    work = Path(a.key_file).expanduser().parent / "state"; work.mkdir(parents=True, exist_ok=True)
    sf = work / f"{a.env}_{pid}.json"
    state = json.loads(sf.read_text()) if sf.exists() else {"field": None, "cams": {}}
    save = lambda: sf.write_text(json.dumps(state, indent=1))
    status = None  # fetched only when a camera still needs its deployment looked up
    locs = {l["name"]: l for l in api.get(f"/projects/{pid}/locations")}
    more = False

    for cam in cams:
        name = cam.name
        cs = state["cams"].setdefault(name, {"done": [], "failed": {}, "phase": "new"})
        if cs["phase"] in ("finalized", "skipped-complete") and not a.new_deployment: continue
        good, bad = inventory(cam)
        cs["excluded"] = bad; cs["expected"] = len(good)
        if not good:
            cs["phase"] = "no-images"; save(); print(f"SKIP {name}: no usable images ({len(bad)} excluded)"); continue
        row = meta.get(name)
        # ---- find or create the deployment
        if not cs.get("deployment") or (a.new_deployment and cs["phase"] != "uploading"):
            if status is None: status = project_status(api, pid)
            cands = status.get(name, [])
            waiting = [c for c in cands if c["st"]["status"] == "WaitingForFiles"]
            have = [c for c in cands if int(c["st"].get("nrAssets") or 0) > 0]
            if a.new_deployment:
                waiting, have = [], []
                cs["replaces"] = [c["id"] for c in cands]
            if have and not waiting:
                n = int(have[0]["st"]["nrAssets"])
                cs["deployment"] = have[0]["id"]
                cs["phase"] = "skipped-complete" if n == len(good) else "count-mismatch"
                cs["wimp_images"] = n; save()
                print(f"{'DONE' if n == len(good) else 'MISMATCH'} {name}: WIMP already has {n} images, folder has {len(good)}"); continue
            if waiting:
                cs["deployment"] = waiting[0]["id"]
                cs["extra_empty"] = [c["id"] for c in waiting[1:]]
            else:
                if not row:
                    cs["phase"] = "no-metadata"; save(); print(f"SKIP {name}: no deployment in WIMP and no metadata row"); continue
                if a.dry_run: print(f"DRY {name}: would create deployment"); continue
                cs["deployment"] = create_deployment(api, pid, name, row, locs, cands)
                cs["created"] = True
            save()
        did = cs["deployment"]
        # ---- dates from the metadata (day-first), stored as UTC 00:00 / 23:59
        if row:
            s, e = parse_day_first(row.get("deploymentStart", "")), parse_day_first(row.get("deploymentEnd", ""))
            times = [t for t in (exif_time(good[0]), exif_time(good[-1])) if t]
            if s and e and e >= s:
                if times and (min(times) < s - timedelta(days=2) or max(times) > e + timedelta(days=2)):
                    cs["date_warning"] = f"EXIF {min(times):%Y-%m-%d}..{max(times):%Y-%m-%d} outside metadata {s:%Y-%m-%d}..{e:%Y-%m-%d}"
                body = {"startDate": s.strftime("%Y-%m-%dT00:00:00.000Z"), "endDate": e.strftime("%Y-%m-%dT23:59:00.000Z")}
                if not a.dry_run and not cs.get("dates_set"):
                    r = api.call("PATCH", f"/projects/{pid}/deployments/{did}", json=body)
                    cs["dates_set"] = r.status_code == 200
                    if r.status_code != 200: cs["date_warning"] = f"PATCH dates {r.status_code}: {r.text[:150]}"
            else:
                cs["date_warning"] = "metadata dates missing or reversed; left unchanged"
        if a.dry_run:
            print(f"DRY {name}: {len(good)} files -> deployment {did[:8]}, {len(bad)} excluded"); continue
        # ---- upload in batches, resumable
        cs["phase"] = "uploading"; done = set(cs["done"])
        todo = [p for p in good if str(p.relative_to(cam)) not in done]
        chunks = [todo[i:i + a.batch] for i in range(0, len(todo), a.batch)]
        if chunks and not state.get("field"):  # probe the field name on one batch before going parallel
            first = chunks.pop(0)
            ok, msg = send(api, pid, did, cam, first, state)
            if ok: cs["done"] += [str(p.relative_to(cam)) for p in first]
            else: chunks.insert(0, first)
            save()
        def work(chunk):
            if time.time() - t0 > a.max_seconds: return chunk, None, {}
            ok, msg = send(api, pid, did, cam, chunk, state)
            if ok: return chunk, [str(p.relative_to(cam)) for p in chunk], {}
            good1, bad1 = [], {}
            for p in chunk:  # retry one by one so a single bad file does not sink the batch
                ok1, msg1 = send(api, pid, did, cam, [p], state)
                if ok1: good1.append(str(p.relative_to(cam)))
                else: bad1[str(p.relative_to(cam))] = msg1
            return chunk, good1, bad1
        with ThreadPoolExecutor(a.workers) as ex:
            for k, (chunk, good1, bad1) in enumerate(ex.map(work, chunks)):
                if good1 is None: more = True; continue
                cs["done"] += good1; cs["failed"].update(bad1)
                if k % 10 == 0: save()
        save()
        if more:
            print(f"PART {name}: {len(cs['done'])}/{len(good)} uploaded"); break
        left = [p for p in good if str(p.relative_to(cam)) not in set(cs["done"])]
        if left:
            cs["phase"] = "upload-incomplete"; save()
            print(f"FAIL {name}: {len(left)} files would not upload; NOT finalized. First error: {next(iter(cs['failed'].values()), '')}"); continue
        ra = api.call("PATCH", f"/projects/{pid}/deployments/{did}", json={"automaticAi": True})  # ask WIMP to queue the AI after sequence creation
        cs["automatic_ai"] = ra.status_code == 200
        r = api.call("POST", f"/projects/{pid}/deployments/{did}/finalizeUpload")
        if r.status_code == 200:
            cs["phase"] = "finalized"; cs["finalized_at"] = datetime.now().isoformat(timespec="seconds")
            print(f"OK {name}: {len(good)} uploaded and finalized")
        else:
            cs["phase"] = "finalize-failed"; cs["finalize_error"] = f"{r.status_code} {r.text[:200]}"
            print(f"FAIL {name}: finalize {cs['finalize_error']}")
        save()
    save()
    print(f"state: {sf}")
    if more:
        print("MORE: time box reached; run the same command again to continue."); sys.exit(75)


def send(api, pid, did, cam, paths, state):
    fields = [state["field"]] if state.get("field") else FIELD_CANDIDATES
    msg = ""
    for field in fields:
        handles = [open(p, "rb") for p in paths]
        try:
            files = [(field, (str(p.relative_to(cam)).replace("/", "_"), h, "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream")) for p, h in zip(paths, handles)]
            r = api.call("POST", f"/projects/{pid}/deployments/{did}/upload", files=files, timeout=600, tries=3)
        finally:
            for h in handles: h.close()
        if r.status_code == 200:
            if not state.get("field"):
                state["field"] = field; state["first_response"] = r.text[:1500]
            return True, ""
        msg = f"{r.status_code} {r.text[:200]}"
        if state.get("field"): break
    return False, msg


def create_deployment(api, pid, name, row, locs, cands):
    loc = locs.get(name)
    if not loc:
        r = api.call("POST", f"/projects/{pid}/locations", json={"name": name, "lat": float(row["latitude"]), "lng": float(row["longitude"])})
        if r.status_code not in (200, 201): raise RuntimeError(f"create location {name}: {r.status_code} {r.text[:200]}")
        loc = r.json(); locs[name] = loc
    body = {"location": loc["id"], "utcOffset": "+10:00"}
    if cands:  # recreate: copy the fields of the deployment being replaced
        for k in ("utcOffset", "camera", "tags", "groups", "cameraHeight", "cameraHeading", "cameraTilt", "bait", "personDeploy", "personDetect", "notes"):
            v = cands[0]["dep"].get(k)
            if v not in (None, [], ""): body[k] = v
    else:
        label = (row.get("cameraID") or "").strip()
        if label:
            cams = {c["label"]: c for c in api.get(f"/projects/{pid}/cameras")}
            cam = cams.get(label)
            if not cam:
                r = api.call("POST", f"/projects/{pid}/cameras", json={"label": label, "make": row.get("cameraMake") or None})
                cam = r.json() if r.status_code in (200, 201) else None
            if cam: body["camera"] = cam["id"]
        tag = (row.get("deploymentTags") or "").strip()
        if tag:
            r = api.call("POST", f"/projects/{pid}/tags/resolve", json={"tags": [tag]})
            if r.status_code == 200:
                j = r.json(); ids = [t["id"] if isinstance(t, dict) else t for t in (j.get("tags", j) if isinstance(j, dict) else j)]
                body["tags"] = ids
    r = api.call("POST", f"/projects/{pid}/deployments", json=body)
    if r.status_code not in (200, 201): raise RuntimeError(f"create deployment {name}: {r.status_code} {r.text[:200]}")
    return r.json()["id"]


# ---------------------------------------------------------------- report
def report_cmd(a):
    api = Api(a.env, a.key_file)
    proj = pick_project(api, a.project, a.only.split(",") if a.only else ())
    pid = proj["id"]
    sf = Path(a.key_file).expanduser().parent / "state" / f"{a.env}_{pid}.json"
    state = json.loads(sf.read_text()) if sf.exists() else {"cams": {}}
    names = [x.strip() for x in a.only.split(",")] if a.only else list(state["cams"])
    status = project_status(api, pid)
    print(f"Project: {proj['name']} [{a.env}]\n\n| Camera | Images (sequences) | Current state |\n|---|---|---|")
    notes = []
    for n in names:
        cs = state["cams"].get(n, {})
        deps = status.get(n, [])
        d = next((x for x in deps if x["id"] == cs.get("deployment")), None) or (max(deps, key=lambda x: int(x["st"].get("nrAssets") or 0)) if deps else None)
        if not d: print(f"| {n} | | No deployment |"); continue
        st = d["st"]; lab = state_label(st); img = images_label(st)
        exp = cs.get("expected")
        if cs.get("phase") == "no-images": lab = "No images (no usable files in folder)"
        if lab in ("Creating sequences", "Needs files") and exp and cs.get("phase") == "finalized": img = f"{exp:,} expected"
        suffix = []
        if cs.get("created") and cs.get("replaces"): suffix.append("recreated")
        n_w = int(st.get("nrAssets") or 0)
        if exp and n_w and n_w != exp and lab.startswith(("AI", "Sequences")): suffix.append(f"{exp - n_w} image(s) short of source")
        if cs.get("phase") in ("upload-incomplete", "finalize-failed", "count-mismatch", "no-metadata"): suffix.append(cs["phase"])
        print(f"| {n} | {img} | {', '.join([lab] + suffix)} |")
        for f, why in cs.get("excluded", []): notes.append(f"excluded {n}/{f} ({why})")
        if cs.get("date_warning"): notes.append(f"{n}: {cs['date_warning']}")
        if cs.get("extra_empty"): notes.append(f"{n}: extra empty deployments to delete in the UI: {cs['extra_empty']}")
        if cs.get("replaces"): notes.append(f"{n}: new deployment {cs.get('deployment')} replaces {cs['replaces']} (delete the old one in the UI once the new one is verified)")
        if lab.startswith("Sequences created, AI not run"): notes.append(f"{n}: AI not started; click Annotate by AI in the Deployments table")
    if notes: print("\n" + "\n".join("- " + x for x in notes))


# ---------------------------------------------------------------- sheet
def status_sheet_cmd(a):
    env = a.env.upper()
    if a.status_file:  # "name,CODE,assets,sequences,aiState,pct;..." plus every other name = waiting
        codes = {"W": "WaitingForFiles", "Q": "SequenceCreationQueued", "P": "SequenceCreationInProgress", "F": "SequenceCreationFailed", "C": "SequenceCreationCompleted", "AQ": "AIAnnotationQueued", "AP": "AIAnnotationInProgress", "AF": "AIAnnotationFailed", "AC": "AIAnnotationCompleted"}
        j = json.loads(Path(a.status_file).read_text()); status = {}
        for rec in j["other"].split(";"):
            n, c, na, ns, ai, pct = rec.split(",")
            status[n] = {"status": codes.get(c, c), "nrAssets": int(na), "nrSequences": int(ns), "aiModelState": None if ai == "-" else ai, "percentInspected": float(pct)}
        waiting_default = True; total = j.get("n")
    else:
        api = Api(a.env, a.key_file)
        proj = pick_project(api, a.project)
        status = {}
        for n, deps in project_status(api, proj["id"]).items():
            status[n] = max(deps, key=lambda x: int(x["st"].get("nrAssets") or 0))["st"]
        waiting_default = False; total = len(status)
    src = a.source
    text = requests.get(src, timeout=60).text if src.startswith("http") else Path(src).expanduser().read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    head, body = rows[0], rows[1:]
    key = next(i for i, h in enumerate(head) if h.strip().lower() in ("deploymentid", "locationid", "camera", "deployment"))
    c1, c2 = f"WIMP {env} status ({a.date})", f"{env} images (sequences)"
    out = [head + [c1, c2]]; seen = set(); counts = {}
    for r in body:
        r = r + [""] * (len(head) - len(r)); n = r[key].strip(); seen.add(n)
        st = status.get(n)
        if st is None and waiting_default and n: st = {"status": "WaitingForFiles"}
        lab = state_label(st) if st else (f"No deployment in {env}" if n else "")
        out.append(r + [lab, images_label(st) if st else ""])
        k = lab.split(" (")[0]; counts[k] = counts.get(k, 0) + 1
    extra = sorted(set(status) - seen)
    for n in extra:
        r = [""] * len(head); r[key] = n
        out.append(r + [state_label(status[n]), images_label(status[n])])
    with open(a.out, "w", newline="") as f: csv.writer(f).writerows(out)
    print(json.dumps({"rows": len(out) - 1, "deployments_in_wimp": total, "in_wimp_not_in_sheet": extra, "counts": counts, "out": a.out}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def common(p):
        p.add_argument("--env", choices=["prod", "test"], default="prod")
        p.add_argument("--key-file", default=None)
        p.add_argument("--project", default=None, help="project name fragment or ID")
    p = sub.add_parser("check"); common(p)
    p = sub.add_parser("upload"); common(p)
    p.add_argument("folder"); p.add_argument("--metadata"); p.add_argument("--only")
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--new-deployment", action="store_true")
    p.add_argument("--batch", type=int, default=10); p.add_argument("--workers", type=int, default=4); p.add_argument("--max-seconds", type=int, default=150)
    p = sub.add_parser("report"); common(p); p.add_argument("--only")
    p = sub.add_parser("status-sheet"); common(p)
    p.add_argument("--source", required=True); p.add_argument("--out", required=True)
    p.add_argument("--status-file"); p.add_argument("--date", default=datetime.now().strftime("%-d %b %Y"))
    a = ap.parse_args()
    if not a.key_file:
        dirs = [os.environ.get("WIMP_KEY_DIR"), "~/mnt/CT images for WildObs upload/.wimp", "~/CT images for WildObs upload/.wimp", "~/.wimp"]
        found = [Path(d).expanduser() / f"{a.env}.key" for d in dirs if d]
        a.key_file = str(next((f for f in found if f.exists()), found[-1]))
        if not Path(a.key_file).exists() and not getattr(a, "status_file", None):
            sys.exit(f"KEY: no {a.env}.key found. Create an API key in WIMP ({'wimp' if a.env == 'prod' else 'wimp.test'}.wildobs.org.au > User settings > API keys) and save it as '~/CT images for WildObs upload/.wimp/{a.env}.key' (never in Dropbox, never in chat).")
    if a.cmd == "check":
        api = Api(a.env, a.key_file); me = api.get("/me")
        print(f"OK {a.env}: {me.get('firstName')} {me.get('lastName')}"); [print(" -", p["name"]) for p in api.get("/me/projects")]
    elif a.cmd == "upload": upload_cmd(a)
    elif a.cmd == "report": report_cmd(a)
    else: status_sheet_cmd(a)


if __name__ == "__main__":
    main()
