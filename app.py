"""
Where to Live SG - web app (Streamlit).

A family enters its fixed points (workplaces, schools), commute limits, rent budget and bedrooms.
The app shows each candidate area's public-transport time to every fixed point (OneMap, live)
and its rent range (real URA contracts in data/rent_contracts.csv), on a map and in one table.
It never ranks areas. The family makes the trade-off.

Run on your computer:   streamlit run app.py
"""

from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import onemap
import rent

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

st.set_page_config(page_title="Where to Live SG", page_icon="🗺️", layout="wide")

COLOURS = {"ok": "#2f8a4e", "warn": "#c98a12", "bad": "#c2413a", "none": "#8a9699"}


# ---------- credentials and data ------------------------------------------------------

def read_credentials():
    """Streamlit Cloud: Settings > Secrets. On your computer: keys.txt next to app.py."""
    try:
        if st.secrets.load_if_toml_exists() and "ONEMAP_EMAIL" in st.secrets:
            return st.secrets["ONEMAP_EMAIL"], st.secrets["ONEMAP_PASSWORD"]
    except Exception:
        pass
    path = HERE / "keys.txt"
    if path.exists():
        keys = {}
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
        if keys.get("ONEMAP_EMAIL") and keys.get("ONEMAP_PASSWORD"):
            return keys["ONEMAP_EMAIL"], keys["ONEMAP_PASSWORD"]
    return None, None


@st.cache_resource(ttl=60 * 60 * 24 * 2, show_spinner=False)   # OneMap tokens last about 3 days
def get_client(email, password):
    return onemap.OneMap(onemap.get_token(email, password))


@st.cache_data(ttl=60 * 60 * 24 * 7, show_spinner=False)
def geocode(_client, query):
    return _client.geocode(query)


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def transit(_client, a, b, date_str):
    return _client.transit(a, b, date_str)


@st.cache_data(ttl=60 * 60 * 24 * 7, show_spinner=False)
def walk(_client, a, b):
    return _client.walk(a, b)


@st.cache_data(show_spinner=False)
def load_candidates():
    return pd.read_csv(DATA / "candidates.csv", encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_rent():
    return rent.load_contracts(DATA / "rent_contracts.csv")


# ---------- page ----------------------------------------------------------------------------

st.title("Where to Live SG")
st.caption("Enter what your family needs. Each area shows its commute to every fixed point and its rent range. "
           "The page marks limits; it never ranks areas. You choose.")

email, password = read_credentials()
if not email:
    st.error("OneMap login is missing. On your computer, put keys.txt next to app.py. "
             "On Streamlit Cloud, add ONEMAP_EMAIL and ONEMAP_PASSWORD under Settings > Secrets.")
    st.stop()

missing_files = [f for f in ("candidates.csv", "rent_contracts.csv") if not (DATA / f).exists()]
if missing_files:
    st.error("Put these files in the data folder: " + ", ".join(missing_files))
    st.stop()

cands = load_candidates()
contracts = load_rent()
beds_options = rent.bedrooms_available(contracts)

with st.form("needs"):
    st.subheader("Family needs")
    st.markdown("**Fixed points.** One row per place someone in the family goes every weekday. "
                "Use a postal code or a full name OneMap knows.")
    points_default = pd.DataFrame([
        {"who": "adult", "label": "Parent 1 work", "address": "National University of Singapore"},
        {"who": "adult", "label": "Parent 2 work", "address": "Raffles Place MRT Station"},
        {"who": "child", "label": "Child 1 school", "address": ""},
    ])
    points = st.data_editor(
        points_default, num_rows="dynamic", use_container_width=True, key="points",
        column_config={
            "who": st.column_config.SelectboxColumn("Who", options=["adult", "child"], required=True),
            "label": st.column_config.TextColumn("Label", required=True),
            "address": st.column_config.TextColumn("Address or postal code"),
        })

    c1, c2, c3, c4 = st.columns(4)
    cap_adult = c1.number_input("Max commute, adults (min)", 0, 180, 45, step=5)
    cap_child = c2.number_input("Max commute, children (min)", 0, 180, 30, step=5)
    bud_min = c3.number_input("Rent from (S$/month)", 0, 50000, 5000, step=100)
    bud_max = c4.number_input("Rent to (S$/month)", 0, 50000, 6000, step=100)

    c5, c6, c7 = st.columns(3)
    beds = c5.selectbox("Bedrooms", beds_options,
                        index=beds_options.index(3) if 3 in beds_options else 0,
                        help="Only bedroom counts that exist in rent_contracts.csv are offered.")
    c6.selectbox("Home type", ["Non-landed private"], help="Version 1 covers non-landed private homes only.")
    areas = c7.multiselect("Candidate areas", list(cands["area"]), default=list(cands["area"]))

    go = st.form_submit_button("Compare areas", type="primary")

if go:
    pts = points.fillna("")
    pts = pts[(pts["address"].str.strip() != "") & (pts["label"].str.strip() != "")]
    if pts.empty:
        st.warning("Add at least one fixed point with an address.")
        st.stop()
    if bud_min > bud_max:
        st.warning("The rent 'from' amount is higher than the 'to' amount.")
        st.stop()
    try:
        client = get_client(email, password)
    except onemap.OneMapError as e:
        st.error(str(e))
        st.stop()

    day = onemap.next_tuesday()
    date_str = day.strftime("%m-%d-%Y")
    log = []

    with st.status("Asking OneMap...", expanded=False) as status:
        fixed = []
        for _, p in pts.iterrows():
            info, s, url = geocode(client, p["address"].strip())
            fixed.append({"who": p["who"], "label": p["label"].strip(), "address": p["address"].strip(),
                          "info": info, "status": s})
            log.append({"step": "find place", "from": p["label"], "to": "", "result": info["matched"] if info else "NOT FOUND",
                        "status": s, "query": url})
        area_pts = {}
        for a in areas:
            q = cands.loc[cands["area"] == a, "search"].iloc[0]
            info, s, url = geocode(client, q)
            area_pts[a] = info
            log.append({"step": "find area", "from": a, "to": "", "result": info["matched"] if info else "NOT FOUND",
                        "status": s, "query": url})

        total = len(areas) * len(fixed)
        bar = st.progress(0.0)
        commute, i = {}, 0
        for a in areas:
            for f in fixed:
                i += 1
                bar.progress(i / max(total, 1))
                A, B = area_pts[a], f["info"]
                cell = {"min": None, "walk": None, "status": "NOT FOUND: place not found"}
                if A and B:
                    r, s, url = transit(client, A, B, date_str)
                    cell["status"] = "ok" if r else "NOT FOUND: " + s
                    cell["min"] = r["minutes"] if r else None
                    log.append({"step": "public transport", "from": a, "to": f["label"],
                                "result": r["minutes"] if r else "NOT FOUND", "status": s, "query": url})
                    dist = onemap.straight_line_m(A, B)
                    if dist < onemap.SHORT_TRIP_M:
                        w, ws, wurl = walk(client, A, B)
                        cell["walk"] = w["minutes"] if w else None
                        log.append({"step": "walk (short trip, %d m)" % dist, "from": a, "to": f["label"],
                                    "result": w["minutes"] if w else "NOT FOUND", "status": ws, "query": wurl})
                commute[(a, f["label"])] = cell
        status.update(label="Done. %d routes asked." % total, state="complete")

    st.session_state["result"] = {
        "fixed": fixed, "areas": areas, "area_pts": area_pts, "commute": commute, "log": log,
        "settings": {"cap_adult": cap_adult, "cap_child": cap_child, "bud_min": bud_min, "bud_max": bud_max,
                     "beds": beds, "depart": "%s %s" % (day.strftime("%a %d %b %Y"), onemap.DEPART_TIME[:5])},
    }

res = st.session_state.get("result")
if not res:
    st.info("Fill in the family needs and press Compare areas.")
    st.stop()

S = res["settings"]
fixed = res["fixed"]

bad_places = [f for f in fixed if not f["info"]]
if bad_places:
    st.warning("OneMap could not find: " + ", ".join(f["label"] for f in bad_places) +
               ". Their commute shows NOT FOUND. Try a postal code.")
with st.expander("Check what OneMap matched for each fixed point", expanded=bool(bad_places)):
    st.dataframe(pd.DataFrame([{"Label": f["label"], "You typed": f["address"],
                                "OneMap matched": f["info"]["matched"] if f["info"] else "NOT FOUND",
                                "Other possible matches": (f["info"]["n_hits"] - 1) if f["info"] else ""}
                               for f in fixed]), hide_index=True, use_container_width=True)

# ---------- evaluate each area ---------------------------------------------------------

rows, marks = [], {}
for a in res["areas"]:
    over, missing = 0, False
    row = {"Area": a}
    for f in fixed:
        c = res["commute"][(a, f["label"])]
        col = "%s (%s), min" % (f["label"], f["who"])
        row[col] = c["min"]
        if c["min"] is None:
            missing = True
        else:
            cap = S["cap_child"] if f["who"] == "child" else S["cap_adult"]
            if c["min"] > cap:
                over += 1
        if c["walk"] is not None:
            row["%s, walk min" % f["label"]] = c["walk"]
    r = rent.summary(contracts, a, S["beds"], S["bud_min"], S["bud_max"])
    row.update({"Rent p25": r["p25"], "Rent median": r["median"], "Rent p75": r["p75"],
                "Contracts": r["n"], "In budget": r["in_budget"], "Rent status": r["status"]})
    if r["median"] is None:
        missing = True
    elif r["median"] > S["bud_max"]:
        over += 1
    cls = "none" if (missing and over == 0) else "ok" if over == 0 else "warn" if over == 1 else "bad"
    row["Limits"] = ("Has NOT FOUND" if cls == "none" else "Meets every limit" if cls == "ok"
                     else "Over %d limit%s" % (over, "s" if over > 1 else ""))
    marks[a] = cls
    rows.append(row)
table = pd.DataFrame(rows)

# ---------- map --------------------------------------------------------------------------

st.subheader("Map")
m = folium.Map(location=[1.33, 103.83], zoom_start=12, tiles="OpenStreetMap")
for f in fixed:
    if f["info"]:
        folium.Marker([f["info"]["lat"], f["info"]["lng"]], tooltip=f["label"],
                      icon=folium.Icon(color="black", icon="star" if f["who"] == "adult" else "education",
                                       prefix="glyphicon")).add_to(m)
for _, row in table.iterrows():
    a = row["Area"]
    pt = res["area_pts"].get(a)
    if not pt:
        continue
    lines = ["<b>%s</b> · %s" % (a, row["Limits"])]
    for f in fixed:
        v = row["%s (%s), min" % (f["label"], f["who"])]
        w = row.get("%s, walk min" % f["label"])
        txt = "NOT FOUND" if pd.isna(v) else "%d min" % v
        if w is not None and not pd.isna(w):
            txt += " · walk %d" % w
        lines.append("%s: %s" % (f["label"], txt))
    if row["Rent median"] is None or pd.isna(row["Rent median"]):
        lines.append("Rent: %s" % row["Rent status"])
    else:
        lines.append("Rent S$%s / %s / %s (n=%d)" % (f"{int(row['Rent p25']):,}", f"{int(row['Rent median']):,}",
                                                    f"{int(row['Rent p75']):,}", row["Contracts"]))
    folium.CircleMarker([pt["lat"], pt["lng"]], radius=11, color="white", weight=2, fill=True,
                        fill_color=COLOURS[marks[a]], fill_opacity=0.95, tooltip=a,
                        popup=folium.Popup("<br>".join(lines), max_width=320)).add_to(m)
st_folium(m, height=520, use_container_width=True, returned_objects=[])
st.caption("Green: meets every limit · Amber: over 1 limit · Red: over 2 or more · Grey: has NOT FOUND. "
           "Click an area for its figures.")

# ---------- table ------------------------------------------------------------------------

st.subheader("All areas, side by side (not ranked)")
minute_cols = ["%s (%s), min" % (f["label"], f["who"]) for f in fixed]


def colour(df):
    out = pd.DataFrame("", index=df.index, columns=df.columns)
    for f, col in zip(fixed, minute_cols):
        cap = S["cap_child"] if f["who"] == "child" else S["cap_adult"]
        out.loc[df[col] > cap, col] = "background-color:#fbe7e5;color:#c2413a"
    out.loc[df["Rent median"] > S["bud_max"], "Rent median"] = "background-color:#fbe7e5;color:#c2413a"
    return out


st.dataframe(table.style.apply(colour, axis=None).format(na_rep="NOT FOUND", precision=0, thousands=","),
             hide_index=True, use_container_width=True)
st.download_button("Download this table (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                   file_name="where_to_live_sg_comparison.csv", mime="text/csv")

with st.expander("Sources: every OneMap query behind these numbers"):
    st.dataframe(pd.DataFrame(res["log"]).astype(str), hide_index=True, use_container_width=True)

st.caption(
    "Commute: OneMap routing API, public transport, departing %s, from each area's MRT station. "
    "Trips under %.1f km also show OneMap walking time. Limits use the public-transport time. "
    "Rent: URA Residential Rental Search, non-landed private, %d-bedroom contracts within 1 km of the MRT "
    "station, latest 4 quarters (rent_contracts.csv). Missing values read NOT FOUND; nothing is estimated."
    % (S["depart"], onemap.SHORT_TRIP_M / 1000, S["beds"]))
