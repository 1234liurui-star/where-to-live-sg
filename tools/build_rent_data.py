"""
build_rent_data.py - builds data/rent_contracts.csv for the web app, for ALL bedroom counts.

Two ways to get the URA contracts:
  python tools/build_rent_data.py downloads
      Reads the CSV files you downloaded from URA Residential Rental Search
      (put them in tools/ura_downloads/). Same reading rules as rent_manual.py (Gate 2).
  python tools/build_rent_data.py api
      Asks the URA Data Service (PMI_Resi_Rental) directly. Needs URA_ACCESS_KEY.
      This is what the quarterly GitHub Action runs.

Both ways then:
  1. keep contracts from the last 4 complete quarters,
  2. find each candidate area's MRT station on OneMap,
  3. keep projects within RADIUS_M of that station (all bedroom counts),
  4. write data/rent_contracts.csv (one row per contract, with its source),
     data/rent_build_info.json (when, which quarters, how many) and append to data/rent_build_log.txt.

Rules kept from the Charter: every contract keeps its source; nothing is estimated;
duplicate downloads are skipped; a district that does not cover all 4 quarters is reported.

Keys: ONEMAP_EMAIL, ONEMAP_PASSWORD (and URA_ACCESS_KEY for 'api') from environment variables,
or from keys.txt next to app.py.
"""

import csv
import glob
import gzip
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

RADIUS_M = 1000
PAUSE_S = 0.25
TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
DATA = os.path.join(ROOT, "data")

ONEMAP_TOKEN_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
URA_TOKEN_URL = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"
URA_DATA_URL = "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"
UA = {"User-Agent": "Mozilla/5.0 (Where to Live SG, student project)"}
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
HEAD = ["area", "project", "street", "district", "property_type", "bedrooms", "area_sqm",
        "lease_month", "quarter", "rent_sgd", "metres_from_station", "source_file", "source_row"]


def stop(msg):
    print("\nSTOPPED: " + msg)
    sys.exit(1)


def http(url, headers=None, data=None):
    h = dict(UA)
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def keys():
    kv = {k: os.environ.get(k, "") for k in ("ONEMAP_EMAIL", "ONEMAP_PASSWORD", "URA_ACCESS_KEY")}
    p = os.path.join(ROOT, "keys.txt")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8-sig"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if not kv.get(k.strip().upper()):
                    kv[k.strip().upper()] = v.strip()
    return kv


def quarter_window(today=None):
    """Last 4 complete quarters, newest first, as (year, quarter)."""
    today = today or date.today()
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(4):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        out.append((y, q))
    return out


def money(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


class OneMap:
    def __init__(self, email, pw):
        r = http(ONEMAP_TOKEN_URL, data={"email": email, "password": pw})
        self.token = r.get("access_token")
        if not self.token:
            stop("OneMap did not give a token.")
        self.bearer = False

    def search(self, text):
        q = urllib.parse.urlencode({"searchVal": text, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1})
        url = ONEMAP_SEARCH_URL + "?" + q
        time.sleep(PAUSE_S)
        try:
            r = http(url, {"Authorization": ("Bearer " if self.bearer else "") + self.token})
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and not self.bearer:
                self.bearer = True
                return self.search(text)
            return url, None
        res = r.get("results") or []
        if not res:
            return url, None
        t = res[0]
        return url, (float(t["X"]), float(t["Y"]), t.get("ADDRESS") or t.get("SEARCHVAL", ""))

    def search_full(self, text, must_contain="MRT"):
        """First match whose address contains `must_contain` (for stations). None if no such match."""
        q = urllib.parse.urlencode({"searchVal": text, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1})
        time.sleep(PAUSE_S)
        try:
            r = http(ONEMAP_SEARCH_URL + "?" + q, {"Authorization": ("Bearer " if self.bearer else "") + self.token})
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and not self.bearer:
                self.bearer = True
                return self.search_full(text, must_contain)
            return None
        for t in r.get("results") or []:
            addr = t.get("ADDRESS") or t.get("SEARCHVAL", "")
            if must_contain.upper() in (addr + " " + t.get("SEARCHVAL", "")).upper():
                return {"lat": float(t["LATITUDE"]), "lng": float(t["LONGITUDE"]),
                        "x": float(t["X"]), "y": float(t["Y"]), "address": addr}
        return None


# ---------- source 1: URA website downloads ------------------------------------------------

def lease_quarter_download(s):
    """'Sep-26' -> (2026, 3)"""
    try:
        m, yy = s.strip().split("-")
        return 2000 + int(yy), (MONTHS[m[:3].title()] - 1) // 3 + 1
    except Exception:
        return None


def from_downloads(window, om, log):
    files = sorted(glob.glob(os.path.join(TOOLS, "ura_downloads", "*.csv")))
    if not files:
        stop("No CSV files in tools/ura_downloads. Put the URA downloads there.")
    seen, contracts, cover = {}, [], {}
    for f in files:
        name = os.path.basename(f)
        digest = hashlib.sha256(open(f, "rb").read()).hexdigest()
        if digest in seen:
            log.append("%s is identical to %s: SKIPPED (duplicate download)" % (name, seen[digest]))
            continue
        seen[digest] = name
        for i, row in enumerate(csv.DictReader(open(f, encoding="utf-8-sig")), start=2):
            lq = lease_quarter_download(row.get("Lease Commencement Date", ""))
            dist = (row.get("Postal District") or "").strip()
            if lq:
                cover.setdefault(dist, set()).add(lq)
            if lq not in window:
                continue
            rent = money(row.get("Monthly Rent ($)", ""))
            if rent is None:
                continue
            contracts.append({"project": row["Project Name"].strip(), "street": row["Street Name"].strip(),
                              "district": dist, "type": row["Property Type"], "beds": row["No of Bedroom"].strip(),
                              "sqm": row["Floor Area (SQM)"], "lease": row["Lease Commencement Date"],
                              "quarter": "%dQ%d" % lq, "rent": rent, "file": name, "row": i, "xy": None})
    for d in sorted(cover):
        miss = [q for q in window if q not in cover[d]]
        log.append("District %s: %s" % (d, "OK, all 4 quarters" if not miss else
                                       "MISSING " + ", ".join("%dQ%d" % q for q in miss)))

    # project locations: reuse project_locations.csv from Gate 2, ask OneMap only for new ones
    cache_f = os.path.join(TOOLS, "project_locations.csv")
    cache = {}
    if os.path.exists(cache_f):
        for r in csv.DictReader(open(cache_f, encoding="utf-8-sig")):
            cache[(r["project"], r["street"])] = r
    todo = sorted({(c["project"], c["street"]) for c in contracts} - set(cache))
    print("Locating %d new projects on OneMap (%d already known) ..." % (len(todo), len(cache)))
    for p, s in todo:
        url, hit = om.search(p)
        if not hit:
            url, hit = om.search(s)
        cache[(p, s)] = {"project": p, "street": s, "x_svy21": hit[0] if hit else "",
                         "y_svy21": hit[1] if hit else "", "onemap_matched": hit[2] if hit else "NOT FOUND",
                         "matched_by": "", "query": url, "retrieved_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(cache_f, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["project", "street", "x_svy21", "y_svy21",
                                          "onemap_matched", "matched_by", "query", "retrieved_at"])
        w.writeheader()
        w.writerows(cache.values())
    for c in contracts:
        loc = cache.get((c["project"], c["street"]))
        if loc and loc.get("x_svy21"):
            c["xy"] = (float(loc["x_svy21"]), float(loc["y_svy21"]))
    return contracts, "URA Residential Rental Search downloads"


# ---------- source 2: URA Data Service API ----------------------------------------------------

def lease_quarter_api(s):
    """'0926' (mmyy) -> (2026, 3)"""
    try:
        return 2000 + int(s[2:4]), (int(s[0:2]) - 1) // 3 + 1
    except Exception:
        return None


def from_api(window, access_key, log):
    if not access_key:
        stop("URA_ACCESS_KEY is missing.")
    r = http(URA_TOKEN_URL, {"AccessKey": access_key})
    token = r.get("Result")
    if r.get("Status") != "Success" or not token:
        stop("URA did not give a token. Reply: %s" % {k: v for k, v in r.items() if k != "Result"})
    contracts = []
    for y, q in window:
        period = "%02dq%d" % (y % 100, q)
        url = URA_DATA_URL + "?" + urllib.parse.urlencode({"service": "PMI_Resi_Rental", "refPeriod": period})
        res = http(url, {"AccessKey": access_key, "Token": token})
        projects = res.get("Result") or []
        n = 0
        for pi, p in enumerate(projects):
            try:
                xy = (float(p["x"]), float(p["y"]))
            except (KeyError, ValueError, TypeError):
                xy = None
            for ri, rr in enumerate(p.get("rental") or []):
                lq = lease_quarter_api(str(rr.get("leaseDate", "")))
                rent = money(rr.get("rent", ""))
                if lq not in window or rent is None:
                    continue
                n += 1
                contracts.append({"project": p.get("project", ""), "street": p.get("street", ""),
                                  "district": rr.get("district", ""), "type": rr.get("propertyType", ""),
                                  "beds": str(rr.get("noOfBedRoom", "")).strip(), "sqm": rr.get("areaSqm", ""),
                                  "lease": rr.get("leaseDate", ""), "quarter": "%dQ%d" % lq, "rent": rent,
                                  "file": "URA API PMI_Resi_Rental %s" % period, "row": "%d.%d" % (pi, ri), "xy": xy})
        log.append("URA API %s: %d projects, %d contracts" % (period, len(projects), n))
        if not projects:
            log.append("URA API %s: EMPTY - the quarter may not be published yet" % period)
    return contracts, "URA Data Service PMI_Resi_Rental"


# ---------- main -------------------------------------------------------------------------------

def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "downloads").lower()
    if mode not in ("downloads", "api"):
        stop("Use: python tools/build_rent_data.py downloads   or   ... api")
    k = keys()
    if not k.get("ONEMAP_EMAIL") or not k.get("ONEMAP_PASSWORD"):
        stop("ONEMAP_EMAIL and ONEMAP_PASSWORD are needed (environment or keys.txt).")
    window = quarter_window()
    wlabel = "%s to %s" % ("%dQ%d" % window[-1], "%dQ%d" % window[0])
    print("Quarters kept: " + wlabel)
    log = []
    om = OneMap(k["ONEMAP_EMAIL"], k["ONEMAP_PASSWORD"])
    if mode == "downloads":
        contracts, source = from_downloads(window, om, log)
    else:
        contracts, source = from_api(window, k.get("URA_ACCESS_KEY"), log)

    areas = list(csv.DictReader(open(os.path.join(DATA, "candidates.csv"), encoding="utf-8-sig")))
    rows, no_xy = [], sum(1 for c in contracts if not c["xy"])
    for a in areas:
        if a.get("x_svy21") and a.get("y_svy21"):
            cx, cy = float(a["x_svy21"]), float(a["y_svy21"])     # already placed by build_candidates.py
        else:
            url, hit = om.search(a["search"])
            if not hit:
                log.append("Area %s: NOT FOUND on OneMap, left out" % a["area"])
                continue
            cx, cy, _ = hit
        n = 0
        for c in contracts:
            if not c["xy"]:
                continue
            d = math.hypot(c["xy"][0] - cx, c["xy"][1] - cy)
            if d > RADIUS_M:
                continue
            n += 1
            rows.append([a["area"], c["project"], c["street"], c["district"], c["type"], c["beds"], c["sqm"],
                         c["lease"], c["quarter"], int(c["rent"]), round(d), c["file"], c["row"]])
        log.append("Area %s: %d contracts within %d m" % (a["area"], n, RADIUS_M))
    if not rows:
        stop("No contracts matched any area. Nothing was written, the old data stays.")

    os.makedirs(DATA, exist_ok=True)
    # Compressed, so the file stays well under GitHub's 25 MB upload limit. pandas reads it directly.
    with gzip.open(os.path.join(DATA, "rent_contracts.csv.gz"), "wt", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEAD)
        w.writerows(rows)
    built = datetime.now().strftime("%Y-%m-%d %H:%M")
    info = {"built_at": built, "source": source, "quarters": wlabel, "radius_m": RADIUS_M,
            "n_contracts": len(rows), "contracts_without_location": no_xy}
    json.dump(info, open(os.path.join(DATA, "rent_build_info.json"), "w", encoding="utf-8"), indent=1)
    with open(os.path.join(DATA, "rent_build_log.txt"), "a", encoding="utf-8") as f:
        f.write("%s | %s | %s | %d contracts kept | %d without location\n" % (built, source, wlabel, len(rows), no_xy))
        for line in log:
            f.write("    " + line + "\n")
    print("\n".join(log))
    print("\nDone. %d contracts written to data/rent_contracts.csv.gz (all bedroom counts)." % len(rows))


if __name__ == "__main__":
    main()
