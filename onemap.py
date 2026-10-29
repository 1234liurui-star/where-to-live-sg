"""
OneMap calls for Where to Live SG.
Same calls as commute.py (Gate 2), moved into functions the web app can use.

Rules kept from the Charter:
  - Every number keeps the exact query behind it.
  - If OneMap cannot answer, the answer is NOT FOUND with the reason. No guessing.
"""

import datetime
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.onemap.gov.sg"
TOKEN_URL = BASE + "/api/auth/post/getToken"
SEARCH_URL = BASE + "/api/common/elastic/search"
ROUTE_URL = BASE + "/api/public/routingsvc/route"

DEPART_TIME = "08:00:00"   # Tuesday 08:00, decided 29 Oct 2026
DEPART_WEEKDAY = 1         # 0=Mon, 1=Tue
MAX_WALK_M = 1000          # max walking distance inside a public-transport trip
SHORT_TRIP_M = 1500        # straight line under this -> also ask for walking time
PAUSE_S = 0.2              # pause between calls, to stay polite to OneMap


class OneMapError(Exception):
    pass


def _call(url, body=None, token=None, bearer=False):
    headers = {"Content-Type": "application/json", "User-Agent": "WhereToLiveSG"}
    if token:
        headers["Authorization"] = ("Bearer " + token) if bearer else token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_token(email, password):
    try:
        res = _call(TOKEN_URL, {"email": email, "password": password})
    except urllib.error.HTTPError as e:
        raise OneMapError("OneMap refused the login (HTTP %s). Check the email and password." % e.code)
    except urllib.error.URLError as e:
        raise OneMapError("Cannot reach OneMap: %s" % e.reason)
    token = res.get("access_token")
    if not token:
        raise OneMapError("OneMap gave no token.")
    return token


class OneMap:
    def __init__(self, token):
        self.token = token
        self.bearer = False

    def _get(self, url):
        time.sleep(PAUSE_S)
        try:
            return _call(url, token=self.token, bearer=self.bearer)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and not self.bearer:
                self.bearer = True
                return _call(url, token=self.token, bearer=True)
            raise

    def geocode(self, query):
        """Returns (info or None, status, url). info has lat, lng, matched."""
        q = urllib.parse.urlencode({"searchVal": query, "returnGeom": "Y",
                                    "getAddrDetails": "Y", "pageNum": 1})
        url = SEARCH_URL + "?" + q
        try:
            res = self._get(url)
        except Exception as e:
            return None, "error: %s" % e, url
        hits = res.get("results") or []
        if not hits:
            return None, "no match", url
        h = hits[0]
        info = {"lat": float(h["LATITUDE"]), "lng": float(h["LONGITUDE"]),
                "matched": h.get("ADDRESS") or h.get("SEARCHVAL", ""),
                "n_hits": res.get("found", len(hits))}
        return info, "ok", url

    def transit(self, start, end, date_str):
        """Public transport, fastest of up to 3 itineraries."""
        q = urllib.parse.urlencode({
            "start": "%.6f,%.6f" % (start["lat"], start["lng"]),
            "end": "%.6f,%.6f" % (end["lat"], end["lng"]),
            "routeType": "pt", "mode": "TRANSIT", "date": date_str,
            "time": DEPART_TIME, "maxWalkDistance": MAX_WALK_M,
            "numItineraries": 3})
        url = ROUTE_URL + "?" + q
        try:
            res = self._get(url)
        except Exception as e:
            return None, "error: %s" % e, url
        its = (res.get("plan") or {}).get("itineraries") or []
        if not its:
            return None, "no itinerary", url
        best = min(its, key=lambda i: i.get("duration", 10**9))
        return {"minutes": round(best.get("duration", 0) / 60),
                "transfers": best.get("transfers", ""),
                "walk_in_trip_min": round(best.get("walkTime", 0) / 60)}, "ok", url

    def walk(self, start, end):
        """Walking route only. Used for short trips."""
        q = urllib.parse.urlencode({
            "start": "%.6f,%.6f" % (start["lat"], start["lng"]),
            "end": "%.6f,%.6f" % (end["lat"], end["lng"]),
            "routeType": "walk"})
        url = ROUTE_URL + "?" + q
        try:
            res = self._get(url)
        except Exception as e:
            return None, "error: %s" % e, url
        summ = res.get("route_summary") or {}
        if summ.get("total_time") is not None:
            return {"minutes": round(float(summ["total_time"]) / 60)}, "ok", url
        its = (res.get("plan") or {}).get("itineraries") or []
        if its:
            best = min(its, key=lambda i: i.get("duration", 10**9))
            return {"minutes": round(best.get("duration", 0) / 60)}, "ok", url
        return None, "no walking route", url


def straight_line_m(a, b):
    """Metres on the ground (haversine). Only decides whether to ask for a walking time."""
    r = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dl = math.radians(b["lng"] - a["lng"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)))


def next_tuesday(today=None):
    d = (today or datetime.date.today()) + datetime.timedelta(days=1)
    while d.weekday() != DEPART_WEEKDAY:
        d += datetime.timedelta(days=1)
    return d
