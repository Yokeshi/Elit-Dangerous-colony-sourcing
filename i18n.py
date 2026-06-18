#!/usr/bin/env python3
"""
i18n.py  -  Simple translation layer (English / Hungarian).

Usage:
    from i18n import t, set_lang
    set_lang("en")
    print(t("ref_system", ref="Sol"))
"""

import json
import os

LANGS = ["en", "hu"]
DEFAULT = "en"
CONFIG = os.path.expanduser("~/.cache/colony_tool/config.json")

_current = DEFAULT

STR = {
    # --- engine / CLI ------------------------------------------------------
    "no_journal_dir": {
        "en": "Could not find the journal folder. Specify it with --dir \"/path\"",
        "hu": "Nem talaltam journal mappat. Add meg: --dir \"/eleresi/ut\""},
    "journal_dir": {
        "en": "Journal folder: {jdir}",
        "hu": "Journal mappa: {jdir}"},
    "no_journal_files": {
        "en": "No readable journal files in the selected period.",
        "hu": "Nincs olvashato journal fajl a megadott idoszakban."},
    "reading_journals": {
        "en": "Reading {n} journal files...",
        "hu": "Beolvasok {n} journal fajlt..."},
    "no_active_1": {
        "en": "No active construction in the journal. Dock at a construction",
        "hu": "Nincs aktiv epitkezes a journalban. Dokkolj be egy construction"},
    "no_active_2": {
        "en": "site so the game writes the data, then run again.",
        "hu": "site-ra, hogy a jatek kiirja az adatokat, aztan futtasd ujra."},
    "no_current_system": {
        "en": "Could not find your current system in the journal.",
        "hu": "Nem talaltam a jelenlegi rendszeredet a journalban."},
    "give_system": {
        "en": "Specify it manually:  --system \"System name\"",
        "hu": "Add meg kezzel:  --system \"Rendszer neve\""},
    "ref_system": {
        "en": "Reference system: {ref}",
        "hu": "Referencia-rendszer: {ref}"},
    "cargo_cap": {
        "en": "Cargo: {cap} t",
        "hu": "Rakter: {cap} t"},
    "search_params": {
        "en": "Search radius: {d} ly | data freshness: max {days} days",
        "hu": "Keresesi sugar: {d} ly | adatfrissesseg: max {days} nap"},
    "carriers_excluded": {
        "en": " | fleet carriers excluded",
        "hu": " | fleet carrierek kihagyva"},
    "local_cache": {
        "en": "Local (Market.json) cache: {n} markets",
        "hu": "Sajat (Market.json) gyorsitotar: {n} piac"},
    "construction": {
        "en": "CONSTRUCTION (MarketID {mid}) — {prog}% done",
        "hu": "EPITKEZES (MarketID {mid}) — {prog}% kesz"},
    "all_delivered": {
        "en": "  All materials delivered. ✔",
        "hu": "  Minden anyag leszallitva. ✔"},
    "material_line": {
        "en": "{disp} — still need: {rem} t",
        "hu": "{disp} — meg kell: {rem} t"},
    "in_cargo": {
        "en": " (in cargo: {have} t)",
        "hu": " (rakterben: {have} t)"},
    "no_source": {
        "en": "No known nearby seller (try increasing Max distance or Data age).",
        "hu": "Nincs ismert kozeli elado (probald novelni a Max tavolsag vagy Adatkor erteket)."},
    "ardent_error": {
        "en": "[Ardent query error: {e}]",
        "hu": "[hiba az Ardent lekeresnel: {e}]"},
    "src_local": {
        "en": "{station} ({system}){fc} — {dist}, stock {stock} @ {price}, {age}",
        "hu": "{station} ({system}){fc} — {dist}, keszlet {stock} @ {price}, {age}"},
    "src_ardent": {
        "en": "{station} ({system}){fc} — {dist}, stock {stock} @ {price}, pad {pad}, {age}",
        "hu": "{station} ({system}){fc} — {dist}, keszlet {stock} @ {price}, pad {pad}, {age}"},
    "age_self_days": {
        "en": "{da}d ago (yours)",
        "hu": "{da}n ezelott (sajat)"},
    "age_self": {
        "en": "your data",
        "hu": "sajat adat"},
    "age_days": {
        "en": "updated {da}d ago",
        "hu": "frissult {da}n ezelott"},
    "age_unknown": {
        "en": "unknown age",
        "hu": "ismeretlen kor"},
    # planner
    "plan_header": {
        "en": "PLANNER — sourcing summary",
        "hu": "TERVEZO — beszerzesi osszegzes"},
    "plan_total_trips": {
        "en": "  Total shortfall: {total} t | Cargo: {cap} t  →  ~{trips} trips",
        "hu": "  Osszes hiany: {total} t | Rakter: {cap} t  →  kb. {trips} fordulo"},
    "plan_total_nocap": {
        "en": "  Total shortfall: {total} t  (cargo unknown — no Loadout event in journal)",
        "hu": "  Osszes hiany: {total} t  (rakter ismeretlen — nincs Loadout esemeny a journalban)"},
    "plan_no_stations": {
        "en": "  No known source with the current filters.",
        "hu": "  Nincs egyetlen ismert forras sem a megadott szurokkel."},
    "plan_hubs": {
        "en": "  Covering hubs (fewest stops):",
        "hu": "  Lefedo hubok (a legkevesebb megallo):"},
    "plan_covers": {
        "en": "covers ({n} materials): {names}",
        "hu": "fedi ({n} anyag): {names}"},
    "plan_low_stock": {
        "en": "⚠ {mat}: stock {stock} t < need {need} t (needs more sources/trips)",
        "hu": "⚠ {mat}: keszlet {stock} t < kell {need} t (tobb forras/fordulo kell)"},
    "plan_leftover": {
        "en": "⚠ No known source for: {names}",
        "hu": "⚠ Nincs ismert forras ezekhez: {names}"},
    "plan_leftover_hint": {
        "en": "  (try increasing the Max distance / Data age slider)",
        "hu": "  (probald novelni a Max tavolsag / Adatkor csuszkat)"},
    "debug_first": {
        "en": "  [DEBUG] first raw record fields:",
        "hu": "  [DEBUG] elso nyers rekord mezoi:"},
    # --- GUI ---------------------------------------------------------------
    "app_title": {
        "en": "Colony Sourcing — ED colonisation",
        "hu": "Colony Sourcing — ED kolonizacio"},
    "lbl_maxdist": {"en": "Max distance (ly)", "hu": "Max tavolsag (ly)"},
    "lbl_top": {"en": "Results / material", "hu": "Talalat / anyag"},
    "lbl_maxdays": {"en": "Data age max (days)", "hu": "Adatkor max (nap)"},
    "lbl_minsupply": {"en": "Min. stock (t)", "hu": "Min. keszlet (t)"},
    "lbl_jdays": {"en": "Journal: last N days (0=all)",
                  "hu": "Journal: utolso N nap (0=mind)"},
    "lbl_refsys": {"en": "Reference system (empty = auto):",
                   "hu": "Referencia-rendszer (ures = automatikus):"},
    "chk_nocarrier": {"en": "Exclude fleet carriers",
                      "hu": "Fleet carrierek kihagyasa"},
    "chk_plan": {"en": "Planner summary (hubs + trips)",
                 "hu": "Tervezo osszegzes (hubok + fordulok)"},
    "btn_search": {"en": "Search", "hu": "Keresés"},
    "btn_clear": {"en": "Clear", "hu": "Törlés"},
    "lbl_lang": {"en": "Language", "hu": "Nyelv"},
    "status_ready": {"en": "Ready.", "hu": "Keszen allok."},
    "status_working": {"en": "Working... (reading journal + Ardent query)",
                       "hu": "Dolgozom... (journal olvasas + Ardent lekeres)"},
    "status_done": {"en": "Done.", "hu": "Kész."},
    "copied": {"en": "Copied: {name}", "hu": "Másolva: {name}"},
    "clip_fallback": {
        "en": "(for reliable paste into the game install xclip: sudo apt install xclip)",
        "hu": "(megbizhato beillesztshez a jatekba telepitsd: sudo apt install xclip)"},
    "click_hint": {
        "en": "Tip: left-click a result = copy system (for routing); right-click = copy station name.",
        "hu": "Tipp: bal klikk egy talalaton = rendszer masolasa (utvonalhoz); jobb klikk = allomasnev masolasa."},
}


def set_lang(lang):
    global _current
    _current = lang if lang in LANGS else DEFAULT


def get_lang():
    return _current


def t(key, **kw):
    entry = STR.get(key, {})
    s = entry.get(_current) or entry.get("en") or key
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError):
            return s
    return s


def load_saved_lang():
    try:
        with open(CONFIG, "r", encoding="utf-8") as fh:
            return json.load(fh).get("lang", DEFAULT)
    except (OSError, json.JSONDecodeError):
        return DEFAULT


def save_lang(lang):
    try:
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as fh:
            json.dump({"lang": lang}, fh)
    except OSError:
        pass
