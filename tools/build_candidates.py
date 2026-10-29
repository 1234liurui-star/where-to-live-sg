"""
build_candidates.py - builds data/candidates.csv: every MRT station as a candidate area.

For each station name below it asks OneMap where "<name> MRT STATION" is, and keeps the first match
whose address contains "MRT". A name OneMap cannot place is reported as NOT FOUND and left out.

Each row gets a rough region (Central, North, North-East, East, West) from its position, by the
fixed rule in region_of(). The region only helps the family narrow the list; it is not a ranking.

Run (from the wheretolive folder):   python tools/build_candidates.py
Needs ONEMAP_EMAIL and ONEMAP_PASSWORD (environment or keys.txt).
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_rent_data as b   # reuses its OneMap login and search

STATIONS = """
Jurong East, Bukit Batok, Bukit Gombak, Choa Chu Kang, Yew Tee, Kranji, Marsiling, Woodlands, Admiralty,
Sembawang, Canberra, Yishun, Khatib, Yio Chu Kang, Ang Mo Kio, Bishan, Braddell, Toa Payoh, Novena, Newton,
Orchard, Somerset, Dhoby Ghaut, City Hall, Raffles Place, Marina Bay, Marina South Pier,
Pasir Ris, Tampines, Simei, Tanah Merah, Bedok, Kembangan, Eunos, Paya Lebar, Aljunied, Kallang, Lavender,
Bugis, Tanjong Pagar, Outram Park, Tiong Bahru, Redhill, Queenstown, Commonwealth, Buona Vista, Dover,
Clementi, Chinese Garden, Lakeside, Boon Lay, Pioneer, Joo Koon, Expo, Changi Airport,
HarbourFront, Chinatown, Clarke Quay, Little India, Farrer Park, Boon Keng, Potong Pasir, Woodleigh,
Serangoon, Kovan, Hougang, Buangkok, Sengkang, Punggol,
Bras Basah, Esplanade, Promenade, Nicoll Highway, Stadium, Mountbatten, Dakota, MacPherson, Tai Seng,
Bartley, Lorong Chuan, Marymount, Caldecott, Botanic Gardens, Farrer Road, Holland Village, one-north,
Kent Ridge, Haw Par Villa, Pasir Panjang, Labrador Park, Telok Blangah, Bayfront,
Bukit Panjang, Cashew, Hillview, Beauty World, King Albert Park, Sixth Avenue, Tan Kah Kee, Stevens,
Rochor, Downtown, Telok Ayer, Fort Canning, Bencoolen, Jalan Besar, Bendemeer, Geylang Bahru, Mattar,
Ubi, Kaki Bukit, Bedok North, Bedok Reservoir, Tampines West, Tampines East, Upper Changi,
Woodlands North, Woodlands South, Springleaf, Lentor, Mayflower, Bright Hill, Upper Thomson, Napier,
Orchard Boulevard, Great World, Havelock, Maxwell, Shenton Way, Gardens by the Bay, Tanjong Rhu,
Katong Park, Tanjong Katong, Marine Parade, Marine Terrace, Siglap, Bayshore
"""

from onemap import region_of   # one rule, shared with the web app


def main():
    k = b.keys()
    if not k.get("ONEMAP_EMAIL") or not k.get("ONEMAP_PASSWORD"):
        b.stop("ONEMAP_EMAIL and ONEMAP_PASSWORD are needed (environment or keys.txt).")
    om = b.OneMap(k["ONEMAP_EMAIL"], k["ONEMAP_PASSWORD"])
    names = [n.strip() for n in STATIONS.replace("\n", " ").split(",") if n.strip()]
    names = list(dict.fromkeys(names))
    rows, lost = [], []
    for n in names:
        q = "%s MRT STATION" % n
        hit = om.search_full(q)
        if not hit:
            lost.append(n)
            print("  %-22s NOT FOUND" % n)
            continue
        rows.append({"area": n, "search": q, "lat": hit["lat"], "lng": hit["lng"],
                     "x_svy21": hit["x"], "y_svy21": hit["y"], "region": region_of(hit["lat"], hit["lng"]),
                     "onemap_matched": hit["address"]})
        print("  %-22s %-11s %s" % (n, rows[-1]["region"], hit["address"][:50]))
    out = os.path.join(b.DATA, "candidates.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nDone. %d stations written to data/candidates.csv, %d NOT FOUND: %s"
          % (len(rows), len(lost), ", ".join(lost) or "none"))


if __name__ == "__main__":
    main()
