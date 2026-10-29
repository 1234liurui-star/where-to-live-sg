"""
Where to Live SG - web app (Streamlit).

A family adds its fixed points (workplaces, schools) with an address search that suggests matches
as they type, then sets commute limits, rent budget and bedrooms.
The app shows each candidate area's public-transport time to every fixed point (OneMap, live)
and what homes there usually rent for (real URA contracts in data/rent_contracts.csv),
on a map and in one table, with a link to current listings near each area.
It never ranks areas. The family makes the trade-off.

Run on your computer:   streamlit run app.py
"""

import json
import urllib.parse
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
from streamlit_searchbox import st_searchbox

import onemap
import rent

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

st.set_page_config(page_title="Where to Live SG", page_icon="🗺️", layout="wide")

COLOURS = {"ok": "#2f8a4e", "warn": "#c98a12", "bad": "#c2413a", "none": "#8a9699"}
BEDROOM_LABEL = {1: "1 bedroom", 2: "2 bedrooms", 3: "3 bedrooms", 4: "4 bedrooms", 5: "5 bedrooms"}


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
def search_places(_client, text):
    return _client.search_many(text)


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
def load_rent(path):
    return rent.load_contracts(path)


def load_build_info():
    p = DATA / "rent_build_info.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def listings_url(area, beds, lo, hi, home=("condo",)):
    """Search page for condos/apartments for rent near the area. A link only: no ranking, no referral."""
    # Sorted by price, lowest first, so the platform's own "Recommended" order (which can include paid boosts)
    # does not decide what the family sees first.
    q = urllib.parse.urlencode({"freetext": "%s MRT" % area, "bedrooms": beds,
                                "minPrice": int(lo), "maxPrice": int(hi), "sort": "price", "order": "asc"})
    home = set(home)
    # PropertyGuru lists ECs with condos; landed houses have their own page; a mix opens all private homes.
    path = ("landed-house-for-rent" if home == {"landed"} else
            "property-for-rent" if "landed" in home else "apartment-condo-for-rent")
    return "https://www.propertyguru.com.sg/%s?" % path + q


def money(v):
    return "S$%s" % f"{int(v):,}"



# ---------- language ------------------------------------------------------------------------
# Only the page's own words are translated. Station names, addresses and school names stay in English,
# because OneMap, URA and PropertyGuru all use the English names.

TEXT = {
    "title": ("Where to Live SG", "Where to Live SG 新加坡选区助手"),
    "intro": ("Add the places your family goes every weekday. Each area shows its commute to every place "
              "and what homes there usually rent for. The page marks your limits; it never ranks areas. You choose.",
              "添加家人每个工作日要去的地方。每个区域会显示到每个地点的通勤时间，以及那里的房子一般租多少钱。"
              "页面只标出是否超出你的限制，不给区域排名，由你自己选择。"),
    "no_login": ("OneMap login is missing. On your computer, put keys.txt next to app.py. "
                 "On Streamlit Cloud, add ONEMAP_EMAIL and ONEMAP_PASSWORD under Settings > Secrets.",
                 "缺少 OneMap 账号。本地运行时，把 keys.txt 放在 app.py 旁边；"
                 "在 Streamlit Cloud 上，在 Settings > Secrets 里填写 ONEMAP_EMAIL 和 ONEMAP_PASSWORD。"),
    "missing_files": ("Put these files in the data folder: ", "请把这些文件放进 data 文件夹："),
    "s1": ("1. Places your family goes every weekday", "1. 家人每个工作日要去的地方"),
    "remove": ("Remove", "删除"),
    "no_places": ("No places yet. Add a workplace or a school below.", "还没有地点。请在下面添加工作地点或学校。"),
    "add_place": ("**Add a place.** Type at least 3 letters of a name, street or postal code, then pick the right match. "
                  "The label is optional; without one, the place's name is used.",
                  "**添加地点。** 输入名称、街道或邮编（至少 3 个字母或数字），然后从列表中选出正确的那一个。"
                  "标签可以不填，不填就用地点的名称。"),
    "who": ("Who goes there", "谁去这里"),
    "adult": ("adult", "大人"),
    "child": ("child", "孩子"),
    "label": ("Label (optional)", "标签（可不填）"),
    "label_ph": ("e.g. Child 1 school", "例如：孩子1 学校"),
    "address": ("Address, name or postal code", "地址、名称或邮编"),
    "search_ph": ("Start typing, e.g. 'american school' or '738547'", "开始输入，例如 'american school' 或 '738547'"),
    "add_btn": ("Add this place", "添加这个地点"),
    "s2": ("2. Limits and home", "2. 限制条件和房屋"),
    "cap_adult": ("Max commute, adults (min)", "大人最长通勤（分钟）"),
    "cap_child": ("Max commute, children (min)", "孩子最长通勤（分钟）"),
    "bud_min": ("Rent from (S$/month)", "租金下限（新元/月）"),
    "bud_max": ("Rent to (S$/month)", "租金上限（新元/月）"),
    "beds": ("Bedrooms", "房间数"),
    "bed_n": ("%d bedroom", "%d 房"),
    "beds_n": ("%d bedrooms", "%d 房"),
    "home": ("Home type", "房屋类型"),
    "condo": ("Condo / apartment (private)", "公寓 / 共管公寓（私人）"),
    "ec": ("Executive condominium (EC)", "执行共管公寓（EC）"),
    "landed": ("Landed house", "有地住宅"),
    "pick_home": ("Pick at least one home type; showing condos for now.", "请至少选一种房屋类型；暂时按公寓显示。"),
    "home_help": ("Private homes from URA lease records. HDB flats are not included yet.",
                  "私人住宅，数据来自 URA 租约记录。暂不包括组屋（HDB）。"),
    "regions": ("Regions to search", "搜索区域"),
    "regions_help": ("Rough regions by position. Starts with the regions your places are in.",
                     "按位置粗略划分的区域。默认选中你的地点所在的区域。"),
    "only_budget": ("Only areas with recent leases in my budget", "只看近期有预算内租约的区域"),
    "areas": ("Areas to compare (%d match)", "要比较的区域（%d 个符合）"),
    "too_many_match": ("%d areas match; the first %d are selected. Narrow the regions or budget, or pick areas by hand.",
                       "共有 %d 个区域符合，已选中前 %d 个。可以缩小区域或预算，或手动挑选。"),
    "too_many": ("Please choose at most %d areas, so the comparison stays quick.", "请最多选择 %d 个区域，以免比较太慢。"),
    "speed": ("Each area takes about one second per place to look up on OneMap.",
              "每个区域、每个地点在 OneMap 上查询约需 1 秒。"),
    "compare": ("Compare areas", "比较区域"),
    "bad_budget": ("The rent 'from' amount is higher than the 'to' amount.", "租金下限比上限还高。"),
    "asking": ("Asking OneMap...", "正在查询 OneMap……"),
    "done": ("Done. %d routes asked.", "完成，共查询 %d 条路线。"),
    "start_hint": ("Add your places, set your limits, then press Compare areas.",
                   "添加地点、设置限制条件，然后点击「比较区域」。"),
    "map": ("Map", "地图"),
    "legend": ("Green: meets every limit · Amber: over 1 limit · Red: over 2 or more · Grey: has NOT FOUND. "
               "Click an area for its figures and a link to homes for rent nearby.",
               "绿色：满足所有限制 · 黄色：超出 1 项 · 红色：超出 2 项或以上 · 灰色：有查不到的数据。"
               "点击区域可查看具体数字和附近出租房源的链接。"),
    "table_title": ("All areas, grouped by your limits (not ranked)", "全部区域，按你的限制条件分组（不排名）"),
    "table_note": ("Areas that meet every limit come first, then those over one limit, then over two or more. "
                   "Inside each group the order is just the station list; the page does not weigh commute against rent.",
                   "满足所有限制的区域排在最前，其次是超出 1 项的，再其次是超出 2 项或以上的。"
                   "同一组内只按站点列表顺序排列，页面不替你权衡通勤和租金。"),
    "col_area": ("Area", "区域"),
    "col_min": ("%s (%s), min", "%s（%s），分钟"),
    "col_walk": ("%s, walk min", "%s，步行分钟"),
    "col_typ": ("Typical rent (S$/month)", "典型租金（新元/月）"),
    "col_range": ("Most leases between", "大多数租约在"),
    "col_inb": ("Recent leases in your budget", "近期预算内租约"),
    "col_list": ("Homes for rent now", "现在出租的房源"),
    "col_limits": ("Limits", "限制条件"),
    "of": ("%d of %d", "%d / %d"),
    "none_found": ("none found", "没有找到"),
    "ok": ("Meets every limit", "满足所有限制"),
    "over1": ("Over 1 limit", "超出 1 项"),
    "overn": ("Over %d limits", "超出 %d 项"),
    "has_nf": ("Has NOT FOUND", "有查不到的数据"),
    "nf": ("NOT FOUND", "查不到"),
    "min": ("%d min", "%d 分钟"),
    "walk": (" · walk %d", " · 步行 %d"),
    "rent": ("Rent: %s", "租金：%s"),
    "typ_line": ("Typical rent %s · most %s–%s", "典型租金 %s · 大多数 %s–%s"),
    "inb_line": ("%d of %d recent leases in your budget", "近期 %d 份租约中有 %d 份在预算内"),
    "see_homes": ("See homes for rent near %s (PropertyGuru asking prices, lowest first)",
                  "查看 %s 附近的出租房源（PropertyGuru 挂牌价，从低到高）"),
    "list_note": ("**Homes for rent now** opens PropertyGuru listings for that station name, your budget and bedrooms, "
                  "sorted by price (lowest first). These are agents' asking prices, not checked by this tool, and the search "
                  "matches the station name, so some homes may be more than 1 km away. The rent columns above come from "
                  "URA records of signed leases within 1 km of the station.",
                  "**现在出租的房源** 会打开 PropertyGuru 上按站名、你的预算和房间数筛选的房源，按价格从低到高排序。"
                  "这些是中介的挂牌价，本工具没有核实；搜索按站名匹配，有些房源可能在 1 公里以外。"
                  "上面的租金数字来自 URA 已签约租约的记录，范围是站点 1 公里内。"),
    "download": ("Download this table (CSV)", "下载这张表（CSV）"),
    "sources": ("Sources: every OneMap query behind these numbers", "数据来源：每个数字背后的 OneMap 查询"),
    "footer": ("Commute: OneMap routing API, public transport (MRT and bus, fastest of up to 3 routes), departing %s, "
               "from each area's MRT station. Trips under %.1f km also show OneMap walking time in the column beside it. "
               "Limits use the public-transport time, or the walking time when OneMap finds no transit route "
               "(for example, a place right at the station). Rent: %s; %s, %d-bedroom leases within 1 km "
               "of the MRT station. 'Typical rent' is the median lease; 'most leases between' is the middle half "
               "(25th to 75th percentile). Missing values read NOT FOUND; nothing is estimated. Listings links open "
               "PropertyGuru search results; this tool takes no fee or referral.",
               "通勤：OneMap 路线 API，公共交通（地铁和公交，取最多 3 条路线中最快的一条），出发时间 %s，"
               "从每个区域的 MRT 站出发。直线距离 %.1f 公里以内的行程，旁边一列会显示 OneMap 的步行时间。"
               "限制条件按公共交通时间判断；如果 OneMap 找不到公交路线（比如地点就在车站旁），则按步行时间判断。"
               "租金：%s；MRT 站 1 公里内的%s、%d 房租约。「典型租金」是租约的中位数；"
               "「大多数租约在」是中间一半（第 25 到第 75 百分位）。查不到的数据显示为「查不到」，不做任何估算。"
               "房源链接打开的是 PropertyGuru 的搜索结果，本工具不收任何费用或佣金。"),
    "rent_src": ("URA Residential Rental Search, %s, built %s", "URA 住宅租赁数据，%s，更新于 %s"),
    "rent_src0": ("URA Residential Rental Search, latest 4 quarters", "URA 住宅租赁数据，最近 4 个季度"),
}
REGION_ZH = {"Central": "中部", "North": "北部", "North-East": "东北部", "East": "东部", "West": "西部"}

lang_col = st.columns([6, 1])[1]
LANG = lang_col.radio("Language", ["English", "中文"], horizontal=True, label_visibility="collapsed", key="lang")
ZH = LANG == "中文"


def t(key):
    return TEXT[key][1 if ZH else 0]


def region_name(r):
    return REGION_ZH.get(r, r) if ZH else r


def keep(name, value):
    """Remember a choice across a language switch (widgets whose option labels are translated get a
    per-language key, so they redraw in the new language; this carries the chosen value over)."""
    st.session_state["_" + name] = value
    return value


def kept(name, default):
    return st.session_state.get("_" + name, default)


def rent_status(s):
    if not ZH:
        return s
    if s.startswith("TOO FEW"):
        return "租约太少（少于 %d 份）" % rent.MIN_CONTRACTS
    return {"NONE FOUND": "没有找到"}.get(s, s)


# ---------- page ----------------------------------------------------------------------------

st.title(t("title"))
st.caption(t("intro"))

email, password = read_credentials()
if not email:
    st.error(t("no_login"))
    st.stop()
RENT_FILE = DATA / "rent_contracts.csv.gz" if (DATA / "rent_contracts.csv.gz").exists() else DATA / "rent_contracts.csv"
missing_files = [f for f, p in (("candidates.csv", DATA / "candidates.csv"),
                                ("rent_contracts.csv.gz", RENT_FILE)) if not p.exists()]
if missing_files:
    st.error(t("missing_files") + ", ".join(missing_files))
    st.stop()
try:
    client = get_client(email, password)
except onemap.OneMapError as e:
    st.error(str(e))
    st.stop()

cands = load_candidates()
contracts = load_rent(str(RENT_FILE))
beds_options = rent.bedrooms_available(contracts)

# Fixed points live in the session: each has who, label, and the OneMap match the family picked.
if "points" not in st.session_state:
    st.session_state["points"] = []
    for who, label, q in [("adult", "Parent 1 work", "National University of Singapore"),
                          ("adult", "Parent 2 work", "Raffles Place MRT Station")]:
        info, status, url = geocode(client, q)
        if info:
            st.session_state["points"].append({"who": who, "label": label, "info": info, "query": url})

# ---------- 1. places --------------------------------------------------------------------

st.subheader(t("s1"))
pts = st.session_state["points"]
if pts:
    for i, p in enumerate(pts):
        c1, c2, c3, c4 = st.columns([1, 2, 5, 1])
        c1.markdown("`%s`" % t(p["who"]))
        c2.markdown("**%s**" % p["label"])
        c3.markdown(p["info"]["matched"])
        if c4.button(t("remove"), key="rm%d" % i):
            pts.pop(i)
            st.session_state.pop("result", None)
            st.rerun()
else:
    st.info(t("no_places"))

with st.container(border=True):
    st.markdown(t("add_place"))

    def _search(text):
        return [("%s  (%s)" % (r["matched"], r["postal"]) if r["postal"] else r["matched"], r)
                for r in search_places(client, text or "")]

    # One row: who · address search · optional label · add
    a1, a2, a3, a4 = st.columns([1.2, 5, 2.2, 1.6], vertical_alignment="bottom")
    who_opts = ["adult", "child"]
    new_who = keep("who", a1.selectbox(t("who"), who_opts, index=who_opts.index(kept("who", "adult")),
                                       key="new_who_" + LANG, format_func=t))
    with a2:
        picked = st_searchbox(_search, placeholder=t("search_ph"), label=t("address"),
                              key="place_search", clear_on_submit=False)
    new_label = a3.text_input(t("label"), placeholder=t("label_ph"), key="new_label")
    if a4.button(t("add_btn"), type="primary", disabled=picked is None, width="stretch"):
        label = new_label.strip() or (picked.get("name") or picked["matched"])[:40]
        pts.append({"who": new_who, "label": label, "info": picked, "query": "OneMap search (picked by user)"})
        st.session_state.pop("result", None)
        st.rerun()

# ---------- 2. limits and home -------------------------------------------------------------

st.subheader(t("s2"))
c1, c2, c3, c4 = st.columns(4)
cap_adult = c1.number_input(t("cap_adult"), 0, 180, 45, step=5, key="cap_adult")
cap_child = c2.number_input(t("cap_child"), 0, 180, 30, step=5, key="cap_child")
bud_min = c3.number_input(t("bud_min"), 0, 50000, 5000, step=100, key="bud_min")
bud_max = c4.number_input(t("bud_max"), 0, 50000, 6000, step=100, key="bud_max")
c5, c6 = st.columns(2)
_b = kept("beds", 3)
beds = keep("beds", c5.selectbox(t("beds"), beds_options,
                                 index=beds_options.index(_b) if _b in beds_options else 0,
                                 format_func=lambda b: (t("bed_n") if b == 1 else t("beds_n")) % b,
                                 key="beds_" + LANG))
home_opts = rent.home_types_available(contracts)
home = keep("home", c6.multiselect(t("home"), home_opts,
                                   default=[h for h in kept("home", ["condo"]) if h in home_opts] or home_opts[:1],
                                   format_func=t, help=t("home_help"), key="home_" + LANG))
if not home:
    st.warning(t("pick_home"))
    home = home_opts[:1]

# Which areas: narrow by region and by rent first (no OneMap calls), then compare commute for the rest.
MAX_AREAS = 25
has_region = "region" in cands.columns
if has_region:
    place_regions = sorted({onemap.region_of(p["info"]["lat"], p["info"]["lng"]) for p in pts})
    all_regions = sorted(cands["region"].dropna().unique())
    r1, r2 = st.columns([2, 1])
    regions = keep("regions", r1.multiselect(
        t("regions"), all_regions,
        default=kept("regions", [r for r in place_regions if r in all_regions] or all_regions),
        help=t("regions_help"), format_func=region_name, key="regions_" + LANG))
    only_budget = r2.checkbox(t("only_budget"), value=True, key="only_budget")
    pool = cands[cands["region"].isin(regions)]
else:
    only_budget = r2 = None
    pool = cands
if only_budget:
    keep = [a for a in pool["area"]
            if rent.summary(contracts, a, beds, bud_min, bud_max, home_type=home)["in_budget"] > 0]
    pool = pool[pool["area"].isin(keep)]
pool_areas = list(pool["area"])
sig = "|".join(pool_areas) + "|%s|%s|%s|%s" % (beds, bud_min, bud_max, ",".join(home))
areas = st.multiselect(t("areas") % len(pool_areas), list(cands["area"]),
                       default=pool_areas[:MAX_AREAS], key="areas_" + str(abs(hash(sig))))
if len(pool_areas) > MAX_AREAS:
    st.warning(t("too_many_match") % (len(pool_areas), MAX_AREAS))
if len(areas) > MAX_AREAS:
    st.warning(t("too_many") % MAX_AREAS)
st.caption(t("speed"))

go = st.button(t("compare"), type="primary", disabled=not pts or not areas or len(areas) > MAX_AREAS)

if go:
    if bud_min > bud_max:
        st.warning(t("bad_budget"))
        st.stop()
    day = onemap.next_tuesday()
    date_str = day.strftime("%m-%d-%Y")
    log = [{"step": "place (picked by user)", "from": p["label"], "to": "", "result": p["info"]["matched"],
            "status": "ok", "query": p["query"]} for p in pts]
    with st.status(t("asking"), expanded=False) as status:
        area_pts = {}
        for a in areas:
            row = cands.loc[cands["area"] == a].iloc[0]
            if "lat" in cands.columns and pd.notna(row.get("lat")):
                info, s, url = ({"lat": float(row["lat"]), "lng": float(row["lng"]),
                                 "matched": row.get("onemap_matched", a), "n_hits": 1}, "ok",
                                "data/candidates.csv (placed by OneMap in build_candidates.py)")
            else:
                info, s, url = geocode(client, row["search"])
            area_pts[a] = info
            log.append({"step": "find area", "from": a, "to": "", "result": info["matched"] if info else "NOT FOUND",
                        "status": s, "query": url})
        total = len(areas) * len(pts)
        bar = st.progress(0.0)
        commute, i = {}, 0
        for a in areas:
            for p in pts:
                i += 1
                bar.progress(i / max(total, 1))
                A, B = area_pts[a], p["info"]
                cell = {"min": None, "walk": None, "how": ""}
                if A and B:
                    r, s, url = transit(client, A, B, date_str)
                    cell["min"] = r["minutes"] if r else None
                    if r:
                        nt = r.get("transfers")
                        cell["how"] = "%s%s" % (r.get("modes", ""), "" if nt in ("", None) else
                                                ", %s transfer%s" % (nt, "" if nt == 1 else "s"))
                    log.append({"step": "public transport", "from": a, "to": p["label"],
                                "result": ("%s min (%s)" % (r["minutes"], cell["how"])) if r else "NOT FOUND",
                                "status": s, "query": url})
                    dist = onemap.straight_line_m(A, B)
                    if dist < onemap.SHORT_TRIP_M:
                        w, ws, wurl = walk(client, A, B)
                        cell["walk"] = w["minutes"] if w else None
                        log.append({"step": "walk (short trip, %d m)" % dist, "from": a, "to": p["label"],
                                    "result": w["minutes"] if w else "NOT FOUND", "status": ws, "query": wurl})
                commute[(a, p["label"])] = cell
        status.update(label=t("done") % total, state="complete")
    st.session_state["result"] = {
        "fixed": [dict(p) for p in pts], "areas": areas, "area_pts": area_pts, "commute": commute, "log": log,
        "settings": {"cap_adult": cap_adult, "cap_child": cap_child, "bud_min": bud_min, "bud_max": bud_max,
                     "beds": beds, "home": home, "depart": "%s %s" % (day.strftime("%a %d %b %Y"), onemap.DEPART_TIME[:5])}}

res = st.session_state.get("result")
if not res:
    st.info(t("start_hint"))
    st.stop()

S, fixed = res["settings"], res["fixed"]

# ---------- evaluate each area ---------------------------------------------------------

rows, marks, popups = [], {}, {}
for a in res["areas"]:
    over, missing = 0, False
    row = {"Area": a}
    lines = []
    for f in fixed:
        c = res["commute"][(a, f["label"])]
        col = "%s (%s), min" % (f["label"], f["who"])
        row[col] = c["min"]
        row["%s, walk min" % f["label"]] = c["walk"]       # only filled for trips under 1.5 km
        txt = t("nf") if c["min"] is None else t("min") % c["min"]
        if c.get("how"):
            txt += " (%s)" % c["how"]
        # The limit uses public transport. If OneMap found no transit route but a short walk exists
        # (e.g. the place is right at the station), the walk is the trip.
        used = c["min"] if c["min"] is not None else c["walk"]
        if used is None:
            missing = True
        else:
            cap = S["cap_child"] if f["who"] == "child" else S["cap_adult"]
            if used > cap:
                over += 1
        if c["walk"] is not None:
            txt += t("walk") % c["walk"]
        lines.append("%s: %s" % (f["label"], txt))
    r = rent.summary(contracts, a, S["beds"], S["bud_min"], S["bud_max"], home_type=S.get("home", ["condo"]))
    row["Typical rent (S$/month)"] = r["median"]
    row["Most leases between"] = ("%s – %s" % (money(r["p25"]), money(r["p75"]))) if r["median"] is not None else rent_status(r["status"])
    row["Recent leases in your budget"] = (t("of") % (r["in_budget"], r["n"])) if r["n"] else t("none_found")
    row["Listings"] = listings_url(a, S["beds"], S["bud_min"], S["bud_max"], S.get("home", ["condo"]))
    if r["median"] is None:
        missing = True
        lines.append(t("rent") % rent_status(r["status"]))
    else:
        if r["median"] > S["bud_max"]:
            over += 1
        lines.append(t("typ_line") % (money(r["median"]), money(r["p25"]), money(r["p75"])))
        lines.append((t("inb_line") % (r["n"], r["in_budget"])) if ZH else (t("inb_line") % (r["in_budget"], r["n"])))
    cls = "none" if (missing and over == 0) else "ok" if over == 0 else "warn" if over == 1 else "bad"
    row["Limits"] = (t("has_nf") if cls == "none" else t("ok") if cls == "ok"
                     else t("over1") if over == 1 else t("overn") % over)
    lines.insert(0, "<b>%s</b> · %s" % (a, row["Limits"]))
    lines.append('<a href="%s" target="_blank">%s</a>' % (row["Listings"], t("see_homes") % a))
    marks[a], popups[a] = cls, "<br>".join(lines)
    rows.append(row)
table = pd.DataFrame(rows)
# Column order: each place's transit time, then its walk time right beside it (only if any trip was short).
walk_cols = []
order = ["Area"]
for f in fixed:
    order.append("%s (%s), min" % (f["label"], f["who"]))
    wc = "%s, walk min" % f["label"]
    if table[wc].notna().any():
        order.append(wc)
        walk_cols.append(wc)
order += [c for c in table.columns if c not in order and not c.endswith(", walk min")]
table = table[order]
# Group by the family's own limits: areas that meet every limit first, then over 1, over 2+, then NOT FOUND.
# Inside each group the areas keep the list order (no weighting of commute against rent; that stays the family's).
GROUP = {"ok": 0, "warn": 1, "bad": 2, "none": 3}
table["_g"] = table["Area"].map(lambda a: GROUP[marks[a]])
table["_i"] = range(len(table))
table = table.sort_values(["_g", "_i"]).drop(columns=["_g", "_i"]).reset_index(drop=True)

# ---------- map --------------------------------------------------------------------------

st.subheader(t("map"))
m = folium.Map(location=[1.33, 103.83], zoom_start=12, tiles="OpenStreetMap")
for f in fixed:
    folium.Marker([f["info"]["lat"], f["info"]["lng"]], tooltip=f["label"],
                  icon=folium.Icon(color="black", icon="star" if f["who"] == "adult" else "education",
                                   prefix="glyphicon")).add_to(m)
for a in res["areas"]:
    pt = res["area_pts"].get(a)
    if pt:
        folium.CircleMarker([pt["lat"], pt["lng"]], radius=11, color="white", weight=2, fill=True,
                            fill_color=COLOURS[marks[a]], fill_opacity=0.95, tooltip=a,
                            popup=folium.Popup(popups[a], max_width=340)).add_to(m)
st_folium(m, height=520, use_container_width=True, returned_objects=[])   # streamlit-folium's own argument
st.caption(t("legend"))

# ---------- table ------------------------------------------------------------------------

st.subheader(t("table_title"))
st.caption(t("table_note"))
minute_cols = ["%s (%s), min" % (f["label"], f["who"]) for f in fixed]


# Show the table in the chosen language. Numbers are written out as text so a missing value reads
# "NOT FOUND" (or stays blank in a walk column) instead of "None"; colours are worked out from the numbers.
RED = "background-color:#fbe7e5;color:#c2413a"
headers = {"Area": t("col_area"), "Typical rent (S$/month)": t("col_typ"), "Most leases between": t("col_range"),
           "Recent leases in your budget": t("col_inb"), "Limits": t("col_limits")}
for f in fixed:
    headers["%s (%s), min" % (f["label"], f["who"])] = t("col_min") % (f["label"], t(f["who"]))
    headers["%s, walk min" % f["label"]] = t("col_walk") % f["label"]


def as_text(v, missing):
    return missing if v is None or pd.isna(v) else f"{int(v):,}"


disp = table.copy()
for col in minute_cols:
    disp[col] = disp[col].map(lambda v: as_text(v, t("nf")))
for col in walk_cols:
    disp[col] = disp[col].map(lambda v: as_text(v, ""))
disp["Typical rent (S$/month)"] = disp["Typical rent (S$/month)"].map(lambda v: as_text(v, "—"))
style = pd.DataFrame("", index=table.index, columns=table.columns)
for f, col in zip(fixed, minute_cols):
    cap = S["cap_child"] if f["who"] == "child" else S["cap_adult"]
    style.loc[table[col] > cap, col] = RED
style.loc[table["Typical rent (S$/month)"] > S["bud_max"], "Typical rent (S$/month)"] = RED
disp = disp.rename(columns=headers)
style = style.rename(columns=headers)
st.dataframe(disp.style.apply(lambda _: style, axis=None), hide_index=True, width="stretch",
             column_config={"Listings": st.column_config.LinkColumn(t("col_list"), display_text="PropertyGuru ↗")})
st.caption(t("list_note"))
st.download_button(t("download"), disp.to_csv(index=False).encode("utf-8-sig"),
                   file_name="where_to_live_sg_comparison.csv", mime="text/csv")

with st.expander(t("sources")):
    st.dataframe(pd.DataFrame(res["log"]).astype(str), hide_index=True, width="stretch")

info = load_build_info()
rent_src = (t("rent_src") % (info.get("quarters", ""), info.get("built_at", "")) if info else t("rent_src0"))
st.caption(t("footer") % (S["depart"], onemap.SHORT_TRIP_M / 1000, rent_src, " / ".join(t(h) for h in S.get("home", ["condo"])), S["beds"]))
