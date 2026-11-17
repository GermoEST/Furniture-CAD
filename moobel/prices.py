"""Maksumuse arvutus käsitsi sisestatud hindadega.

Programm koostab vajalike materjalide ja tarvikute nimekirja koos kogustega.
Ühikuhinna (koos käibemaksuga) sisestab kasutaja ise – hinnad jäävad meelde failis
'hinnakiri.json' programmi kaustas ja kehtivad ka järgmistes projektides.
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "hinnakiri.json")
VERSION = 2

# tüüpilised plaadimõõdud (pikkus, laius mm) – kasutaja saab muuta
SHEETS = {
    "Puitlaastplaat (LMDP)": [2800, 2070], "MDF": [2800, 2070], "Vineer": [2500, 1250],
    "HDF (kõvapapp)": [2440, 1220], "Papp / kõvapapp": [2440, 1220], "Täispuit": [3000, 1200],
    "Liimpuit": [3000, 1200], "Klaas": [1000, 1000], "Metall": [1000, 1000],
}
EDGE_KEY = "servakant"


def load():
    st = dict(version=VERSION, currency="€", waste=15, whole=True, edging=True, items={})
    if os.path.exists(PATH):
        try:
            with open(PATH, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("version") == VERSION:
                st.update(d)
        except Exception:
            pass
    return st


def save(st):
    st["version"] = VERSION
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)


def item(st, key):
    return st["items"].setdefault(key, {})


def calculate(project, st):
    """Tagastab dict(rows, panels, hardware, total, missing, warnings).
    Rida: key, group, name, qty, unit, unit_price, total, sheet (plaatidel)."""
    from .fasteners import hardware_summary
    waste = float(st.get("waste", 15)) / 100.0
    whole = bool(st.get("whole", True))
    rows, warns = [], []
    groups = {}
    edge_m = 0.0
    for p in project.parts:
        if getattr(p, "role", None) in ("slide", "handle") or getattr(p, "leg", None):
            continue
        L, W, Tk = p.dims()
        key = f"{p.material}|{Tk:g}"
        g = groups.setdefault(key, dict(mat=p.material, t=Tk, area=0.0, n=0, maxL=0.0, maxW=0.0))
        g["area"] += L * W / 1e6
        g["n"] += 1
        g["maxL"] = max(g["maxL"], L)
        g["maxW"] = max(g["maxW"], W)
        if p.material in ("Puitlaastplaat (LMDP)", "MDF") and Tk >= 12:
            edge_m += 2 * (L + W) / 1000

    try:
        from .cutplan import plan as _plan
        cp = _plan(project, st)
    except Exception:
        cp = {}
    panels = 0.0
    for key, g in sorted(groups.items()):
        it = item(st, key)
        sheet = it.get("sheet") or SHEETS.get(g["mat"], [2800, 2070])
        sa = sheet[0] * sheet[1] / 1e6
        price = float(it.get("price", 0) or 0)
        need = g["area"] * (1 + waste)
        if g["maxL"] > max(sheet) + 1 or g["maxW"] > min(sheet) + 1:
            warns.append(f"{g['mat']} {g['t']:g} mm: mõni detail on suurem kui plaat {sheet[0]:g}×{sheet[1]:g}.")
        c = cp.get((g["mat"], g["t"]))
        if c and c["too_big"]:
            warns.append(f"{g['mat']} {g['t']:g} mm: ei mahu plaadile – " + ", ".join(c["too_big"]))
        if whole:
            qty = len(c["sheets"]) if c and c["sheets"] else max(1, math.ceil(need / sa - 1e-9))
            total = qty * price
        else:
            qty = round(need / sa, 2)
            total = qty * price
        rows.append(dict(key=key, group="plaat", name=f"{g['mat']} {g['t']:g} mm",
                         info=(f"{g['n']} detaili, {g['area']:.2f} m², lõikeplaani järgi" if whole and c else
                               f"{g['n']} detaili, {g['area']:.2f} m² + {waste * 100:.0f}% jääke"),
                         qty=qty, unit="plaat", unit_price=price, total=total, sheet=list(sheet)))
        panels += total
    per_part = {}
    for p in project.parts:
        if hasattr(p, "edge_lengths"):
            for t, m in p.edge_lengths().items():
                per_part[t] = per_part.get(t, 0.0) + m
    if per_part:
        for t, m in sorted(per_part.items()):
            key = f"{EDGE_KEY}|{t:g}"
            it = item(st, key)
            m = round(m * 1.1, 1)
            price = float(it.get("price", 0) or 0)
            rows.append(dict(key=key, group="plaat", name=f"Servakant {t:g} mm", info="määratud servad, +10%",
                             qty=m, unit="jm", unit_price=price, total=m * price))
    elif st.get("edging", True) and edge_m > 0:
        it = item(st, EDGE_KEY)
        m = round(edge_m * 1.1, 1)
        price = float(it.get("price", 0) or 0)
        rows.append(dict(key=EDGE_KEY, group="plaat", name="Servakant", info="kõik servad (umbkaudu), +10%",
                         qty=m, unit="jm", unit_price=price, total=m * price))

    hw = 0.0
    hw_rows = list(hardware_summary(project).items())
    legs = {}
    for p in project.parts:
        if getattr(p, "leg", None):
            k = p.description or p.name
            legs[k] = legs.get(k, 0) + 1
    for name, n in hw_rows + [(k, n) for k, n in legs.items()]:
        unit = "tk"
        qty = n
        if name.endswith("(paar)"):
            unit = "paar"
        it = item(st, name)
        price = float(it.get("price", 0) or 0)
        rows.append(dict(key=name, group="tarvik", name=name, info="", qty=qty, unit=unit, unit_price=price,
                         total=qty * price))
        hw += qty * price
    # kasutaja lisatud read
    for i, ex in enumerate(getattr(project, "extra_rows", []) or []):
        key = "oma|" + ex.get("name", "")
        price = float(item(st, key).get("price", 0) or 0)
        q = float(ex.get("qty", 1) or 0)
        rows.append(dict(key=key, group="oma", name=ex.get("name", ""), info="", qty=q, unit=ex.get("unit", "tk"),
                         unit_price=price, total=q * price, extra=i))
    # käsitsi muudetud kogused
    ov = getattr(project, "qty_override", {}) or {}
    panels = hw = 0.0
    for r in rows:
        r["calc_qty"] = r["qty"]
        if r.get("extra") is None and r["key"] in ov:
            r["qty"] = ov[r["key"]]
            r["overridden"] = True
        r["total"] = r["qty"] * r["unit_price"]
        if r["group"] == "plaat":
            panels += r["total"]
        else:
            hw += r["total"]
    missing = sum(1 for r in rows if not r["unit_price"])
    return dict(rows=rows, panels=panels, hardware=hw, total=panels + hw, missing=missing, warnings=warns)
