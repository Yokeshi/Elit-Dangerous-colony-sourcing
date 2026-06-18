#!/usr/bin/env python3
"""
colony_sourcing.py  -  2. fazis: hol szerezd be a hianyzo anyagokat?

1) Kiolvassa a journalbol az aktualis epitkezes hianylistajat + a jelenlegi
   tartozkodasi rendszeredet + a hajod rakteret.
2) Minden hianyzo anyaghoz lekerdezi az Ardent API-tol a legkozelebbi
   eladokat (ahonnan vehetsz), tavolsag szerint rendezve.

Csak beepitett Python modulokat hasznal (urllib). Semmit nem kell telepiteni.

Hasznalat:
    python3 colony_sourcing.py
    python3 colony_sourcing.py --system "Hborann"        # kezi referencia-rendszer
    python3 colony_sourcing.py --max-distance 50 --top 3 # max 50 ly, top 3 forras
    python3 colony_sourcing.py --no-carriers             # fleet carriereket kihagyja
    python3 colony_sourcing.py --debug                   # nyers API valasz mezok
"""

import argparse
import glob
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from i18n import t, set_lang

ARDENT = "https://api.ardent-insight.com/v2"
CACHE_DIR = os.path.expanduser("~/.cache/colony_tool/markets")
import math

# A jatek "Saved Games/Frontier Developments/Elite Dangerous" mappaja, ahova a
# journal es a Market.json kerul. A pontos helye platformfuggo, ezert tobb
# ismert helyen keresunk (lasd find_journal_dir).
JOURNAL_SUBPATH = os.path.join(
    "Saved Games", "Frontier Developments", "Elite Dangerous")


# ---------------------------------------------------------------------------
# JOURNAL OLVASAS
# ---------------------------------------------------------------------------

def _has_journals(path):
    return path and os.path.isdir(path) and glob.glob(
        os.path.join(path, "Journal.*.log"))


# A Steam compatdata utvonal vege az Elite Dangerous-hoz (AppID 359320)
ED_COMPAT = os.path.join(
    "steamapps", "compatdata", "359320", "pfx", "drive_c", "users",
    "steamuser", JOURNAL_SUBPATH)


def _steam_roots():
    home = os.path.expanduser("~")
    return [os.path.join(home, p) for p in (
        os.path.join(".steam", "steam"),
        os.path.join(".steam", "debian-installation"),
        os.path.join(".steam", "root"),
        os.path.join(".local", "share", "Steam"),
        os.path.join(".var", "app", "com.valvesoftware.Steam",
                     ".local", "share", "Steam"),
    )]


def _steam_library_paths():
    """Steam konyvtarak (a fo + a libraryfolders.vdf-bol kiolvasott extra
    konyvtarak, pl. masik meghajton). Gyors, nincs rekurziv pasztazas."""
    libs = []
    for root in _steam_roots():
        if os.path.isdir(root):
            libs.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, "r", encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
            for m in re.findall(r'"path"\s*"([^"]+)"', txt):
                libs.append(m.replace("\\\\", os.sep).replace("\\", os.sep))
        except OSError:
            pass
    seen, out = set(), []
    for l in libs:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out


def find_journal_dir(user_dir):
    # 1) ha a felhasznalo megadott egy mappat, azt nezzuk eloszor
    if _has_journals(user_dir):
        return user_dir

    home = os.path.expanduser("~")

    # 2) KOZVETLEN, AZONNALI jeloltek (nincs rekurzio -> gyors)
    direct = [
        os.path.join(home, JOURNAL_SUBPATH),                       # Windows/nativ
        os.path.join(home, "OneDrive", JOURNAL_SUBPATH),           # OneDrive
        os.path.join(home, "OneDrive", "Documents", JOURNAL_SUBPATH),
    ]
    # Steam/Proton (Linux) – a fo es a tovabbi konyvtarakbol
    for lib in _steam_library_paths():
        direct.append(os.path.join(lib, ED_COMPAT))
    for c in direct:
        if _has_journals(c):
            return c

    # 3) VEGSO esetben: korlatozott rekurziv kereses (csak kis, valoszinu
    #    mappak alatt — pl. macOS bottle-ok, Wine prefixek)
    bases = [
        os.path.join(home, "Library", "Application Support", "CrossOver",
                     "Bottles"),
        os.path.join(home, "Library", "Containers",
                     "com.isaacmarovitz.Whisky", "Data", "Bottles"),
        os.path.join(home, ".wine"),
        os.path.join(home, "Games"),
    ]
    for base in bases:
        if os.path.isdir(base):
            hits = glob.glob(os.path.join(
                base, "**", "Frontier Developments", "Elite Dangerous"),
                recursive=True)
            for h in hits:
                if _has_journals(h):
                    return h
    return None


def journal_files(jdir, days):
    files = sorted(glob.glob(os.path.join(jdir, "Journal.*.log")))
    if days and days > 0:
        import time
        cutoff = time.time() - days * 86400
        files = [f for f in files if os.path.getmtime(f) >= cutoff]
    return files


def symbol_of(resource):
    """$cmmcomposite_name;  ->  cmmcomposite  (az Ardent ezt a format varja)"""
    raw = resource.get("Name", "")
    return raw.strip("$;").replace("_name", "").lower()


def display_of(resource):
    n = resource.get("Name_Localised")
    if n:
        return n
    return symbol_of(resource).title()


def parse_journal(files):
    """Visszaad: depots, current_system, cargo, cargo_capacity, system_coords"""
    depots = {}
    current_system = None
    cargo = {}
    cargo_capacity = None
    system_coords = {}  # {rendszernev: (x, y, z)}
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    et = ev.get("event")

                    # jelenlegi rendszer: barmi, aminek van StarSystem-e (legutobbi nyer)
                    if "StarSystem" in ev and ev.get("StarSystem"):
                        current_system = ev["StarSystem"]
                        # koordinatak, ha vannak (FSDJump / Location / CarrierJump)
                        if "StarPos" in ev and isinstance(ev["StarPos"], list):
                            system_coords[ev["StarSystem"]] = tuple(ev["StarPos"])

                    if et == "ColonisationConstructionDepot":
                        mid = ev.get("MarketID")
                        if mid is None:
                            continue
                        res = {}
                        for r in ev.get("ResourcesRequired", []):
                            res[symbol_of(r)] = {
                                "display": display_of(r),
                                "required": int(r.get("RequiredAmount", 0)),
                                "provided": int(r.get("ProvidedAmount", 0)),
                            }
                        depots[mid] = {
                            "progress": ev.get("ConstructionProgress", 0.0),
                            "complete": ev.get("ConstructionComplete", False),
                            "resources": res,
                        }

                    elif et == "Cargo" and ev.get("Vessel", "Ship") == "Ship":
                        if "Inventory" in ev:
                            cargo = {i["Name"].lower(): int(i.get("Count", 0))
                                     for i in ev["Inventory"]}

                    elif et == "Loadout":
                        if "CargoCapacity" in ev:
                            cargo_capacity = int(ev["CargoCapacity"])
        except OSError:
            continue
    return depots, current_system, cargo, cargo_capacity, system_coords


# ---------------------------------------------------------------------------
# HELYI PIAC (Market.json) + GYORSITOTAR
# ---------------------------------------------------------------------------

def load_local_markets(jdir):
    """Beolvassa az aktualis Market.json-t, elmenti a gyorsitotarba (MarketID
    szerint), majd visszaadja az osszes gyorsitotarazott piacot.
    Igy idovel felepul egy sajat, friss adatbazis a meglatogatott piacokrol."""
    os.makedirs(CACHE_DIR, exist_ok=True)

    # 1) aktualis Market.json elmentese a tarba (ha letezik)
    mpath = os.path.join(jdir, "Market.json")
    if os.path.isfile(mpath):
        try:
            with open(mpath, "r", encoding="utf-8", errors="replace") as fh:
                m = json.load(fh)
            mid = m.get("MarketID")
            if mid is not None:
                with open(os.path.join(CACHE_DIR, f"{mid}.json"), "w",
                          encoding="utf-8") as out:
                    json.dump(m, out)
        except (OSError, json.JSONDecodeError):
            pass

    # 2) az osszes tarolt piac beolvasasa
    markets = []
    for f in glob.glob(os.path.join(CACHE_DIR, "*.json")):
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                m = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        items = {}
        for it in m.get("Items", []):
            sym = it.get("Name", "").strip("$;").replace("_name", "").lower()
            stock = int(it.get("Stock", 0))
            buy = int(it.get("BuyPrice", 0))
            if stock > 0 and buy > 0:  # csak amit valoban vehetsz
                items[sym] = {"stock": stock, "buy": buy}
        markets.append({
            "station": m.get("StationName", "?"),
            "system": m.get("StarSystem", "?"),
            "type": m.get("StationType", ""),
            "timestamp": m.get("timestamp"),
            "items": items,
        })
    return markets


def distance_ly(a, b):
    if not a or not b:
        return None
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def local_sources(markets, system_coords, ref_system, symbol, min_supply):
    """A sajat (Market.json) adatokbol kikeresi az adott arut arulo piacokat."""
    ref = system_coords.get(ref_system)
    out = []
    for m in markets:
        item = m["items"].get(symbol)
        if not item or item["stock"] < min_supply:
            continue
        d = distance_ly(ref, system_coords.get(m["system"]))
        out.append({
            "station": m["station"], "system": m["system"],
            "distance": d if d is not None else 9e9,
            "stock": item["stock"], "buy": item["buy"],
            "timestamp": m.get("timestamp"),
            "carrier": "carrier" in str(m.get("type", "")).lower(),
        })
    out.sort(key=lambda x: x["distance"])
    return out


# ---------------------------------------------------------------------------
# ARDENT API
# ---------------------------------------------------------------------------

def ardent_exports(system, commodity, max_distance, max_days, fleet_carriers,
                   min_volume, debug=False):
    """Legkozelebbi eladok lekerdezese egy aruhoz. Lista dict-eket ad vissza."""
    sysq = urllib.parse.quote(system)
    comq = urllib.parse.quote(commodity)
    url = (f"{ARDENT}/system/name/{sysq}/commodity/name/{comq}/nearby/exports")
    params = {"maxDistance": max_distance, "maxDaysAgo": max_days,
              "minVolume": min_volume}
    if fleet_carriers is not None:
        params["fleetCarriers"] = "true" if fleet_carriers else "false"
    url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={"User-Agent": "colony-sourcing/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []  # nincs ilyen aru / rendszer adat
        raise
    if debug and data:
        print(t("debug_first"))
        print("  " + json.dumps(data[0], indent=2).replace("\n", "\n  "))
    return data if isinstance(data, list) else []


def g(rec, *keys, default=None):
    """Elso letezo, nem-None mezo a megadott kulcsok kozul."""
    for k in keys:
        if k in rec and rec[k] is not None:
            return rec[k]
    return default


def days_ago(rec):
    ts = g(rec, "updatedAt", "updated_at", "timestamp")
    if not ts:
        return None
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts / (1000 if ts > 1e12 else 1), timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, OSError):
        return None


def pad_label(rec):
    p = g(rec, "maxLandingPadSize", "padSize", "maxLandingPad")
    if p in (3, "3", "L", "Large"):
        return "L"
    if p in (2, "2", "M", "Medium"):
        return "M"
    if p in (1, "1", "S", "Small"):
        return "S"
    return "?"


def is_carrier(rec):
    if g(rec, "fleetCarrier", "isFleetCarrier") in (True, 1, "true"):
        return True
    st = str(g(rec, "stationType", default="")).lower()
    return "carrier" in st


def fmt_source(rec):
    station = g(rec, "stationName", "station_name", "station", default="?")
    system = g(rec, "systemName", "system_name", "system", default="?")
    dist = g(rec, "distance", "distanceLy", "distance_ly", default=None)
    price = g(rec, "buyPrice", "price", "buy_price", default=None)
    stock = g(rec, "stock", "supply", "amount", default=None)
    pad = pad_label(rec)
    da = days_ago(rec)

    dist_s = f"{dist:.1f} ly" if isinstance(dist, (int, float)) else "? ly"
    stock_s = f"{stock:,} t" if isinstance(stock, (int, float)) else "? t"
    price_s = f"{price:,} cr" if isinstance(price, (int, float)) else "? cr"
    age_s = t("age_days", da=da) if da is not None else t("age_unknown")
    carrier_s = " [FC]" if is_carrier(rec) else ""
    return t("src_ardent", station=station, system=system, fc=carrier_s,
             dist=dist_s, stock=stock_s, price=price_s, pad=pad, age=age_s)


def fmt_local(src):
    dist = src.get("distance")
    dist_s = (f"{dist:.1f} ly" if isinstance(dist, (int, float)) and dist < 9e8
              else "? ly")
    stock_s = f"{src['stock']:,} t"
    price_s = f"{src['buy']:,} cr"
    carrier_s = " [FC]" if src.get("carrier") else ""
    # frissesseg a Market.json timestamp-bol
    da = None
    ts = src.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            da = (datetime.now(timezone.utc) - dt).days
        except ValueError:
            da = None
    age_s = t("age_self_days", da=da) if da is not None else t("age_self")
    return t("src_local", station=src['station'], system=src['system'],
             fc=carrier_s, dist=dist_s, stock=stock_s, price=price_s, age=age_s)


# ---------------------------------------------------------------------------
# FO LOGIKA
# ---------------------------------------------------------------------------

def run(depots, current_system, cargo, cargo_capacity, system_coords,
        markets, args):
    active = [(mid, d) for mid, d in depots.items() if not d.get("complete")]
    if not active:
        print(t("no_active_1"))
        print(t("no_active_2"))
        return

    ref = args.system or current_system
    if not ref:
        print(t("no_current_system"))
        print(t("give_system"))
        return

    print(t("ref_system", ref=ref))
    if cargo_capacity:
        print(t("cargo_cap", cap=cargo_capacity))
    print(t("search_params", d=args.max_distance, days=args.max_days)
          + (t("carriers_excluded") if args.no_carriers else ""))
    print(t("local_cache", n=len(markets)))
    print()

    fleet_carriers = False if args.no_carriers else None
    want_plan = getattr(args, "plan", True)

    for mid, depot in active:
        prog = depot.get("progress", 0.0) * 100
        print("=" * 70)
        print("  " + t("construction", mid=mid, prog=f"{prog:.1f}"))
        print("=" * 70)

        rows = []
        for sym, r in depot["resources"].items():
            rem = r["required"] - r["provided"]
            if rem > 0:
                rows.append((sym, r["display"], rem, cargo.get(sym, 0)))
        rows.sort(key=lambda x: x[2], reverse=True)

        if not rows:
            print(t("all_delivered") + "\n")
            continue

        # a tervezohoz: anyagonkent osszegyujtjuk a forrasokat
        material_sources = {}  # sym -> {"display","remaining","sources":[...]}

        for sym, disp, rem, have in rows:
            have_s = t("in_cargo", have=have) if have else ""
            print("\n  ▸ " + t("material_line", disp=disp.upper(),
                                rem=f"{rem:,}") + have_s)
            collected = []

            # 1) SAJAT, friss forrasok (Market.json gyorsitotar)
            locals_ = local_sources(markets, system_coords, ref, sym,
                                    args.min_supply)
            for src in locals_[:args.top]:
                print(f"      ✓ {fmt_local(src)}")
            for src in locals_:
                collected.append({
                    "station": src["station"], "system": src["system"],
                    "distance": src.get("distance"), "stock": src["stock"],
                    "carrier": src.get("carrier", False), "local": True})

            # 2) ARDENT kozossegi forrasok (kiegeszitesnek)
            try:
                results = ardent_exports(
                    ref, sym, args.max_distance, args.max_days,
                    fleet_carriers, args.min_supply, debug=args.debug)
            except Exception as e:  # noqa: BLE001
                results = []
                if not locals_:
                    print("      " + t("ardent_error", e=e))

            results.sort(key=lambda x: g(x, "distance", "distanceLy",
                                         "distance_ly", default=9e9))
            for rec in results[:args.top]:
                print(f"      {fmt_source(rec)}")
            for rec in results:
                collected.append({
                    "station": g(rec, "stationName", "station_name", "station",
                                 default="?"),
                    "system": g(rec, "systemName", "system_name", "system",
                                default="?"),
                    "distance": g(rec, "distance", "distanceLy", "distance_ly"),
                    "stock": g(rec, "stock", "supply", "amount", default=0),
                    "carrier": is_carrier(rec), "local": False})

            if not locals_ and not results:
                print("      " + t("no_source"))

            material_sources[sym] = {"display": disp, "remaining": rem,
                                     "sources": collected}
        print()

        if want_plan:
            make_plan(material_sources, cargo_capacity, args.no_carriers)


# ---------------------------------------------------------------------------
# TERVEZOMOTOR
# ---------------------------------------------------------------------------

def make_plan(material_sources, cargo_capacity, no_carriers):
    """Mohó lefedés: a legkevesebb hub, ami az osszes hianyzo anyagot fedi."""
    import math as _math

    total_remaining = sum(m["remaining"] for m in material_sources.values())

    # allomasok osszesitese: (station, system) -> {distance, anyagok:{sym:stock}}
    stations = {}
    for sym, m in material_sources.items():
        for s in m["sources"]:
            if no_carriers and s.get("carrier"):
                continue
            key = (s["station"], s["system"])
            st = stations.setdefault(key, {
                "distance": s.get("distance"), "carrier": s.get("carrier"),
                "items": {}})
            # a legjobb (legnagyobb) keszletet tartjuk az adott aruhoz
            prev = st["items"].get(sym, 0)
            st["items"][sym] = max(prev, s.get("stock") or 0)
            d = s.get("distance")
            if d is not None and (st["distance"] is None or d < st["distance"]):
                st["distance"] = d

    print("─" * 70)
    print("  " + t("plan_header"))
    print("─" * 70)

    if cargo_capacity:
        trips = _math.ceil(total_remaining / cargo_capacity)
        print(t("plan_total_trips", total=f"{total_remaining:,}",
                cap=cargo_capacity, trips=trips))
    else:
        print(t("plan_total_nocap", total=f"{total_remaining:,}"))

    needed = set(material_sources.keys())
    if not stations:
        print(t("plan_no_stations") + "\n")
        return

    print("\n" + t("plan_hubs"))
    step = 0
    covered_total = set()
    while True:
        uncovered = needed - covered_total
        if not uncovered:
            break
        # válaszd az állomást, ami a legtöbb még lefedetlen anyagot adja;
        # döntetlennél a közelebbi nyer
        best_key, best_cov = None, set()
        for key, st in stations.items():
            cov = uncovered & set(st["items"].keys())
            if len(cov) > len(best_cov) or (
                    len(cov) == len(best_cov) and best_key is not None
                    and (st["distance"] or 9e9) < (stations[best_key]["distance"] or 9e9)):
                best_key, best_cov = key, cov
        if not best_cov:
            break
        step += 1
        st = stations[best_key]
        dist = st["distance"]
        dist_s = f"{dist:.1f} ly" if isinstance(dist, (int, float)) and dist < 9e8 else "? ly"
        fc = " [FC]" if st.get("carrier") else ""
        names = ", ".join(material_sources[s]["display"] for s in best_cov)
        print(f"   {step}. {best_key[0]} ({best_key[1]}){fc} — {dist_s}")
        print("        " + t("plan_covers", n=len(best_cov), names=names))
        # jelezzuk, ha valamelyik anyagbol kevés a készlet
        for s in best_cov:
            need = material_sources[s]["remaining"]
            stock = st["items"].get(s, 0)
            if stock < need:
                print("        " + t("plan_low_stock",
                                     mat=material_sources[s]['display'],
                                     stock=f"{stock:,}", need=f"{need:,}"))
        covered_total |= best_cov

    leftover = needed - covered_total
    if leftover:
        names = ", ".join(material_sources[s]["display"] for s in leftover)
        print("\n  " + t("plan_leftover", names=names))
        print(t("plan_leftover_hint"))
    print()


def main():
    ap = argparse.ArgumentParser(
        description="ED kolonizacio: hol szerezd be a hianyzo anyagokat (Ardent API)")
    ap.add_argument("--dir", help="Journal mappa eleresi utja")
    ap.add_argument("--system", help="Referencia-rendszer (felulirja a journalbol vett helyzetet)")
    ap.add_argument("--days", type=int, default=120,
                    help="Csak ennyi naonal ujabb journal fajlok (0 = mind)")
    ap.add_argument("--max-distance", type=int, default=100,
                    help="Max tavolsag feny-evben (max 500)")
    ap.add_argument("--max-days", type=int, default=30,
                    help="Max ennyi napos piaci adatot fogad el")
    ap.add_argument("--min-supply", type=int, default=1,
                    help="Minimalis keszlet az eladonal (tonna)")
    ap.add_argument("--top", type=int, default=3,
                    help="Hany legkozelebbi forrast mutasson anyagonkent")
    ap.add_argument("--no-carriers", action="store_true",
                    help="Fleet carriereket kihagyja")
    ap.add_argument("--no-plan", action="store_true",
                    help="Ne mutassa a tervezo osszegzest")
    ap.add_argument("--debug", action="store_true",
                    help="Kiirja az elso nyers API rekord mezoit")
    ap.add_argument("--lang", choices=["en", "hu"], default=None,
                    help="Nyelv / language (en vagy hu)")
    args = ap.parse_args()
    args.plan = not args.no_plan
    set_lang(args.lang or "en")

    jdir = find_journal_dir(args.dir)
    if not jdir:
        print(t("no_journal_dir"))
        sys.exit(1)
    print(t("journal_dir", jdir=jdir), flush=True)
    files = journal_files(jdir, args.days)
    if not files:
        print(t("no_journal_files"))
        sys.exit(1)
    print(t("reading_journals", n=len(files)), flush=True)

    depots, current_system, cargo, cap, system_coords = parse_journal(files)
    markets = load_local_markets(jdir)
    run(depots, current_system, cargo, cap, system_coords, markets, args)


if __name__ == "__main__":
    main()
