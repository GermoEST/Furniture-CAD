"""Keeletugi (eesti / inglise).

Lähtetekstid on koodis eesti keeles. T(s) tõlgib:
  1) täpne vaste sõnastikust,
  2) lausemallid (regex) – sõnajärg,
  3) fraasid (pikemad enne) sõnapiiridega.
translate_tree(widget) tõlgib valmis akna kõik nähtavad tekstid ja jätab originaali meelde,
et keelt saaks töö ajal vahetada.
"""
import re

LANGS = {"et": "Eesti", "en": "English"}
_lang = None


def lang():
    global _lang
    if _lang is None:
        try:
            from PySide6.QtCore import QSettings
            _lang = QSettings("Foral", "Moobel").value("lang", "et") or "et"
        except Exception:
            _lang = "et"
    return _lang


def set_lang(code):
    global _lang
    _lang = code
    try:
        from PySide6.QtCore import QSettings
        QSettings("Foral", "Moobel").setValue("lang", code)
    except Exception:
        pass


# ---------------------------------------------------------------- täpsed vasted
EXACT = {
    # rakendus / menüüd
    "Mööbli disainer": "Furniture Designer",
    "MÖÖBLI DISAINER": "FURNITURE DESIGNER",
    "Valmistatud Eestis": "Made in Estonia",
    "Käivitan…": "Starting…",
    "Laen 3D mootorit (VTK)…": "Loading 3D engine (VTK)…",
    "Laen geomeetria tööriistu…": "Loading geometry tools…",
    "Valmistan kinnitusi ja sahtleid…": "Preparing fasteners and drawers…",
    "Peaaegu valmis…": "Almost ready…",
    "Ehitan 3D vaadet…": "Building 3D view…",
    "Valmis": "Ready",
    "&Fail": "&File", "&Muuda": "&Edit", "&Abi": "&Help",
    "Uus": "New", "Ava…": "Open…", "Salvesta": "Save", "Salvesta nimega…": "Save as…",
    "Näidis: kirjutuslaud": "Sample: desk", "Ekspordi STL (kogu mööbel)…": "Export STL (whole piece)…",
    "Projekti nimi…": "Project name…", "Välju": "Exit", "Võta tagasi": "Undo", "Tee uuesti": "Redo",
    "Dubleeri detail": "Duplicate part", "Kustuta detail": "Delete part", "Tühista tööriist": "Cancel tool",
    "Kuidas kasutada": "How to use", "Klahvid ja hiir": "Keys and mouse",
    "Graafika režiim (kui 3D vaade on must/tühi)…": "Graphics mode (if 3D view is black/empty)…",
    "Detailid": "Parts", "Omadused": "Properties", "Tööriistad": "Tools", "Vaade": "View",
    "➕ Plaat / latt": "➕ Panel / batten", "🦵 Mööblijalad…": "🦵 Furniture legs…",
    "📦 3D fail…": "📦 3D file…", "⧉ Dubleeri": "⧉ Duplicate", "⇋ Koopia teisele poole": "⇋ Copy to other side",
    "🗑 Kustuta": "🗑 Delete", "🗄 Lisa sahtlid…": "🗄 Add drawers…",
    "Mitu detaili: Ctrl + klikk (nimekirjas või 3D vaates)": "Several parts: Ctrl + click (in list or 3D view)",
    "Nimi": "Name", "Materjal": "Material", "Värv": "Colour", "Paksus": "Thickness", "Laius": "Width",
    "Kõrgus": "Height", "Nurga raadius": "Corner radius", "Asukoht ja pööre": "Position and rotation",
    "Pööre X": "Rotation X", "Pööre Y": "Rotation Y", "Pööre Z": "Rotation Z",
    "Põrandale": "To floor", "Nihuta…": "Move…", "Kirjeldus": "Description",
    "Kinnitused selles detailis": "Fasteners in this part",
    "Kustuta valitud kinnitus (ja selle augud)": "Delete selected fastener (and its holes)",
    "🧲 Liida pinnad": "🧲 Join faces", "Kinnitus:": "Fastener:", "⚙": "⚙",
    "🔩 Lisa kinnitus": "🔩 Add fastener", "mutter/ekstsentrik teisele poole": "nut/cam on other side",
    "Lahti:": "Explode:", "Kinnitused": "Fasteners", "Läbipaistev": "Transparent", "Vaade:": "View:",
    "🔒 Lukusta vaade": "🔒 Lock view", "🔓 Vabasta vaade": "🔓 Unlock view", "📐 Ortho": "📐 Ortho",
    "Iso": "Iso", "Eest": "Front", "Tagant": "Back", "Paremalt": "Right", "Vasakult": "Left", "Pealt": "Top",
    "Küljelt": "Side", "Sobita": "Fit", "⌨ Klahvid": "⌨ Keys", "📋 Nimekiri": "📋 Parts list",
    "🪜 Sammud": "🪜 Steps", "📘 Monteerimisjuhend": "📘 Assembly guide",
    "Kinnituse mõõdud": "Fastener dimensions", "Sobita kõik vaatesse (F)": "Fit everything in view (F)",
    "Vaade ei pöördu: vasak hiir nihutab, ratas suumib.": "View does not rotate: left mouse pans, wheel zooms.",
    "Ilma perspektiivita vaade (nagu tehniline joonis).": "View without perspective (like a technical drawing).",
    "Kliki paigal oleva detaili pinnale, siis liigutatava detaili pinnale. Teine detail keeratakse ja lükatakse esimese vastu.":
        "Click a face of the part that stays, then a face of the part to move. The second part is rotated and pushed against the first.",
    "Kliki detaili välispinnale kohas, kust kinnitus sisse läheb. Selle taga peab olema teine detail. Esc lõpetab.":
        "Click the outer face of a part where the fastener goes in. Another part must be behind it. Esc ends.",
    "Tere! Alusta: 'Plaat / latt', 'Mööblijalad' või 'Näidis: kirjutuslaud'.":
        "Hello! Start with 'Panel / batten', 'Furniture legs' or 'Sample: desk'.",
    "Vali detail nimekirjast või 3D vaates.": "Select a part in the list or the 3D view.",
    "Salvestan muudatused?": "Save changes?", "Projekti nimi": "Project name", "Nimi:": "Name:",
    "Ava projekt": "Open project", "Salvesta projekt": "Save project", "Ava 3D fail": "Open 3D file",
    "Suurus": "Size", "Suurim mõõt mm (0 = jäta failist):": "Largest dimension mm (0 = keep from file):",
    "Nihuta": "Move", "Nihe X Y Z mm (nt: 0 0 -18):": "Offset X Y Z mm (e.g. 0 0 -18):",
    "Kustuta": "Delete", "Viga": "Error", "Juhend": "Guide", "Monteerimisjuhend": "Assembly guide",
    "Kuhu juhend salvestada?": "Where to save the guide?", "Teen pilte…": "Rendering images…",
    "Graafika": "Graphics", "Ekspordi STL": "Export STL", "Käivita programm uuesti.": "Restart the program.",
    "Projekt on tühi.": "The project is empty.", "Tagasi võetud": "Undone",
    "Vali TEISE detaili pind.": "Select a face of the OTHER part.",
    "Kliki järgmist kohta või Esc.": "Click the next spot or Esc.",
    "Valimine: kliki detailil. Hiire vasak = pööra, parem/ratas = suumi, keskmine = nihuta.":
        "Select: click a part. Left mouse = rotate, right/wheel = zoom, middle = pan.",
    "LIIDA 1/2: kliki pinnal, mille vastu teine detail tuleb (see detail jääb paigale). Esc = katkesta.":
        "JOIN 1/2: click the face the other part goes against (this part stays). Esc = cancel.",
    "LIIDA 2/2: kliki liigutatava detaili pinnal, mis läheb esimese vastu.":
        "JOIN 2/2: click the face of the moving part that goes against the first one.",
    "LIIDA 2/2: kliki liigutatava detaili pinnal, mis läheb esimese vastu. Esc = katkesta.":
        "JOIN 2/2: click the face of the moving part that goes against the first one. Esc = cancel.",
    "KINNITUS: kliki detaili VÄLISPINNAL kohas, kust kinnitus läheb läbi teise detaili sisse. Esc = lõpeta.":
        "FASTENER: click the OUTER face of a part where the fastener goes through into the other part. Esc = finish.",
    "Vaade LUKUS: vasak hiir nihutab, ratas suumib, pööramine keelatud. L = vabasta.":
        "View LOCKED: left mouse pans, wheel zooms, rotation disabled. L = unlock.",
    "Vaade vaba: vasak hiir pöörab.": "View free: left mouse rotates.",
    "Näidislaud laaditud: 4 detaili, Minifixid, ristmutrid ja tüüblid.":
        "Sample desk loaded: 4 parts, Minifix cams, cross dowels and dowels.",
    "Vali kaks küljeseina, mille vahele sahtlid tulevad:\nkliki esimesel, siis Ctrl + klikk teisel (nimekirjas või 3D vaates).":
        "Select the two side panels the drawers go between:\nclick the first, then Ctrl + click the second (in list or 3D view).",
    "auto (soovitatav)": "auto (recommended)", "riistvara (videokaart)": "hardware (graphics card)",
    "tarkvara (aeglasem, töötab alati)": "software (slower, always works)",
    "teadmata": "unknown", "ristkülik": "rectangle", "pildist kontuur": "contour from image",
    "AI 3D": "AI 3D", "3D fail": "3D file",
    # dialoogid
    "Uus plaat / latt": "New panel / batten", "Plaat": "Panel", "Laius (pikkus)": "Width (length)",
    "Kõrgus (laius)": "Height (width)", "Asend": "Orientation", "Kogus": "Quantity",
    "Lamav (horisontaalne)": "Lying (horizontal)", "Püstine, eest vaadates (nt tagasein)": "Upright, facing front (e.g. back panel)",
    "Püstine, küljelt vaadates (nt külg)": "Upright, facing sideways (e.g. side)",
    "Poldi läbimõõt": "Bolt diameter", "Poldi pikkus": "Bolt length", "Pea läbimõõt": "Head diameter",
    "Mutri läbimõõt": "Nut diameter", "Ekstsentriku kaugus servast": "Cam distance from edge",
    "Ekstsentriku Ø": "Cam Ø", "Ekstsentriku ava sügavus": "Cam hole depth",
    "Poldi ava Ø (vastasdetailis)": "Bolt hole Ø (mating part)", "Poldi ava sügavus": "Bolt hole depth",
    "Serva ava Ø": "Edge hole Ø", "Läbimõõt": "Diameter", "Pikkus": "Length", "Juhtava Ø": "Pilot hole Ø",
    "Sügavus esimeses detailis": "Depth in first part", "Ava sügavus jalas": "Hole depth in leg",
    "Ava Ø jalas": "Hole Ø in leg", "Keermesmuhvi ava Ø": "Threaded insert hole Ø",
    "Keermesmuhvi ava sügavus": "Threaded insert hole depth",
    "Monteerimise sammud": "Assembly steps", "Automaatne": "Automatic", "Lisa": "Add",
    "Ühenda eelmisega": "Merge with previous", "Pealkiri": "Title", "Märkus": "Note",
    "Uued detailid selles sammus": "New parts in this step", "Uus samm": "New step",
    "Detailide ja kinnituste nimekiri": "Parts and fasteners list", "Detail": "Part",
    "Auke": "Holes", "Kinnitus": "Fastener", "<b>Detailid</b>": "<b>Parts</b>",
    "<b>Kinnitused</b>": "<b>Fasteners</b>", "Salvesta CSV (Excel)…": "Save CSV (Excel)…", "Sulge": "Close",
    "Salvesta nimekiri": "Save list",
    "Mööblijalad": "Furniture legs", "Jala tüüp": "Leg type", "Värv / puit": "Colour / wood",
    "Mõõdud": "Dimensions", "Paigutus": "Placement", "Kuhu": "Where",
    "Lisa eraldi (paigutan ise)": "Add separately (I place them)",
    "Kaugus plaadi servast": "Distance from panel edge", "Kogus (eraldi lisamisel)": "Quantity (when added separately)",
    "Lisa kinnitused automaatselt (kruvid / jalapoldid)": "Add fasteners automatically (screws / hanger bolts)",
    "Lisa sahtlid": "Add drawers", "Tüüp": "Type", "Sahtlid": "Drawers",
    "Klaviatuurisahtel (siinidega)": "Keyboard tray (on slides)", "Sahtlite arv": "Number of drawers",
    "Ava alumine serv (Z)": "Opening bottom edge (Z)", "Ava ülemine serv (Z)": "Opening top edge (Z)",
    "Mööbli esikülg": "Furniture front", "Siinid": "Slides", "Siini pikkus": "Slide length",
    "Automaatne (pikim, mis mahub)": "Automatic (longest that fits)", "Sahtlikast": "Drawer box",
    "Küljed, esi- ja tagaosa": "Sides, front and back", "Põhi (kuni 600 mm)": "Bottom (up to 600 mm)",
    "Üle 600 mm laiad": "Wider than 600 mm", "Paksem põhi (vineer 12 mm) + tugiliist": "Thicker bottom (12 mm plywood) + support batten",
    "Paksem põhi (vineer 12 mm)": "Thicker bottom (12 mm plywood)",
    "Tavaline põhi + keskmine tugiliist": "Normal bottom + centre support batten",
    "Esipaneel ja käepide": "Front panel and handle", "Paigaldus": "Mounting",
    "Sisse (ava sisse, esiservaga tasa)": "Inset (flush with front edge)",
    "Peale (katab külgseinte servad)": "Overlay (covers side panel edges)",
    "Vahe paneelide vahel": "Gap between fronts", "Käepide": "Handle", "Käepideme viimistlus": "Handle finish",
    "Puudub (vajutusavaja)": "None (push-to-open)", "Klaviatuurisahtel": "Keyboard tray",
    "Alusplaadi laius": "Tray board width", "Alusplaadi pealmine pind (Z)": "Tray board top surface (Z)",
    "Lisa käepide esiliistule": "Add handle to front lip", "Stiil": "Style", "Kinnitusavade vahe": "Hole spacing",
    "Viimistlus": "Finish", "Muuda kõiki käepidemeid": "Change all handles",
    "Mõõdud (mm)": "Dimensions (mm)", "Pikkus mm": "Length mm", "Laius mm": "Width mm", "Paksus mm": "Thickness mm",
    # materjalid ja värvid
    "Puitlaastplaat (LMDP)": "Particleboard (melamine)", "Vineer": "Plywood", "Täispuit": "Solid wood",
    "Liimpuit": "Glued laminated wood", "Metall": "Metal", "Klaas": "Glass", "Plast": "Plastic", "Muu": "Other",
    "HDF (kõvapapp)": "HDF (hardboard)", "Papp / kõvapapp": "Cardboard / hardboard",
    "Must": "Black", "Valge": "White", "Kroom / hõbe": "Chrome / silver", "Antratsiit": "Anthracite",
    "Tamm": "Oak", "Pöök": "Beech", "Pähkel": "Walnut", "Mänd": "Pine", "Kroom": "Chrome",
    "Harjatud teras": "Brushed steel", "Messing": "Brass", "Nahk pruun": "Leather brown", "Nahk must": "Leather black",
    # jalad
    "Puit – kandiline sirge": "Wood – square straight", "Puit – kandiline koonusjas": "Wood – square tapered",
    "Puit – ümar sirge": "Wood – round straight", "Puit – ümar koonusjas (skandi)": "Wood – round tapered (Scandi)",
    "Metall – ümar toru + kinnitusplaat": "Metal – round tube + mounting plate",
    "Metall – kandiline toru + kinnitusplaat": "Metal – square tube + mounting plate",
    "Metall – ümar toru + 3-labaline plaat (6 kruvi)": "Metal – round tube + 3-lobe plate (6 screws)",
    "Metall – kandiline raamjalg (kirjutuslaua U-jalg)": "Metal – square frame leg (desk U-leg)",
    "Külg (ülal)": "Side (top)", "Külg all": "Side (bottom)", "Läbimõõt (ülal)": "Diameter (top)",
    "Läbimõõt all": "Diameter (bottom)", "Kinnitusplaat (külg)": "Mounting plate (side)",
    "Plaadi paksus": "Plate thickness", "Raami laius (sügavus)": "Frame width (depth)",
    # käepidemed
    "U-sang, ümar": "U-bar, round", "U-sang, kandiline": "U-bar, square", "T-latt (üleulatuv toru)": "T-bar (overhanging rod)",
    "Kaarkäepide": "Arched handle", "D-sang, lame lattmetall": "D-handle, flat bar", "Nupp, ümar": "Knob, round",
    "Nupp, kandiline": "Knob, square", "Profiilkäepide ülaservas (alumiinium)": "Edge profile handle (aluminium)",
    "Nahkrihm": "Leather strap", "Süvistatud kausskäepide": "Recessed cup handle",
    # kinnitused
    "Mööblipolt + ristmutter (pikk vastasmutter)": "Furniture bolt + cross dowel (barrel nut)",
    "Minifix 15 (veerandpöörde ekstsentrik)": "Minifix 15 (quarter-turn cam lock)",
    "Konfirmaat (euro-kruvi) 7×50": "Confirmat (euro screw) 7×50", "Puittüübel 8×35": "Wooden dowel 8×35",
    "Puidukruvi 4×40": "Wood screw 4×40", "Läbiv mööblipolt + kuppelmutter": "Through furniture bolt + cap nut",
    "Jalapolt M8 + keermesmuhv (puitjalg)": "Hanger bolt M8 + threaded insert (wooden leg)",
    "Polt läheb läbi A, ristmutter (Ø10 silinder) pannakse B külje sisse risti poldiga.":
        "The bolt goes through A; the cross dowel (Ø10 cylinder) goes into the side of B across the bolt.",
    "Ekstsentrik Ø15 detaili B siseküljel, polt keeratakse A sisepinda. Väljast ei paista.":
        "Cam Ø15 on the inside of part B, bolt screwed into the inner face of A. Not visible from outside.",
    "Läbiv ava Ø7 detailis A, juhtava Ø5 detailis B.": "Through hole Ø7 in part A, pilot hole Ø5 in part B.",
    "Peidetud tüübel. A sisse 12 mm, ülejäänu B sisse.": "Hidden dowel. 12 mm into A, the rest into B.",
    "Läbiv ava A-s, eelpuuritud juhtava B-s.": "Through hole in A, pre-drilled pilot hole in B.",
    "Kahepoolne polt: puidukeere jala sisse, M8 keere plaati paigaldatud keermesmuhvi. Kliki jala alumisele pinnale.":
        "Double-ended bolt: wood thread into the leg, M8 thread into a threaded insert in the panel. Click the bottom face of the leg.",
    "Kahe pinnapidi kokku pandud detaili läbiv polt (nt jalg raami külge).":
        "Bolt through two parts joined face to face (e.g. leg to frame).",
    "Ei leidnud detaili paksust selles kohas.": "Could not find the part thickness at this spot.",
    "Selle koha taga pole teist detaili (B). Kliki kohale, kus teine detail on vastu selle detaili sisepinda.":
        "There is no other part (B) behind this spot. Click where another part is against the inner face of this part.",
    "Detail A on Minifixi poldi jaoks õhuke.": "Part A is thin for the Minifix bolt.",
    "Ava B-s lühendatud (pinnapidi ühendus) – vali lühem kinnitus.": "Hole in B shortened (face joint) – choose a shorter fastener.",
    "Tundmatu kinnitus": "Unknown fastener",
    # sahtlid – vead
    "Vali kaks plaati (küljeseina).": "Select two panels (side panels).",
    "Valitud plaadid ei ole paralleelsed.": "The selected panels are not parallel.",
    "Valitud plaadid on lamavad – vali kaks püstist küljeseina.": "The selected panels are lying flat – select two upright side panels.",
    "Plaadid kattuvad – nende vahel pole ava.": "The panels overlap – there is no opening between them.",
    "Küljeseinte ühine osa on sahtlite jaoks liiga väike.": "The shared area of the side panels is too small for drawers.",
    "Ava kõrgus on liiga väike.": "The opening height is too small.",
    "Sahtleid on selle kõrguse jaoks liiga palju.": "Too many drawers for this height.",
    # juhend
    "Kirjutuslaud": "Desk", "Lauaplaat": "Tabletop", "Külg vasak": "Left side", "Külg parem": "Right side",
    "Tagapaneel": "Back panel", "Uus mööbel": "New furniture", "Valmis!": "Done!",
}

# ---------------------------------------------------------------- lausemallid (sõnajärg)
TEMPLATES = [
    (r"Kinnita (.+?) detaili (.+?) külge", r"Attach \1 to \2"),
    (r"Kinnita ([^<\n]+?)(?=</|\n|$)", r"Attach \1"),
    (r"Aseta (.+?) tööpinnale", r"Place \1 on the work surface"),
    (r"Pane kokku ja paigalda: ", r"Assemble and install: "),
    (r"'(.+?)' liidetud detaili '(.+?)' külge\. Täpsusta vajadusel asukohta paremalt paneelilt\.",
     r"'\1' joined to '\2'. Fine-tune the position in the right panel if needed."),
    (r"Kustutan detaili '(.+?)' \(ja selle kinnitused\)\?", r"Delete part '\1' (and its fasteners)?"),
    (r"Käepide muudetud \((\d+) tk\)\.", r"Handle changed (\1 pcs)."),
    (r"Lisatud (\d+) jalga \((.+?)\)\.", r"Added \1 legs (\2)."),
    (r"Lisatud: (.+?) \((\d+) detaili\)\.", r"Added: \1 (\2 parts)."),
    (r"Ava '(.+?)' ja '(.+?)' vahel: laius <b>(.+?) mm</b>, sügavus (.+?) mm, kõrgus (.+?) mm",
     r"Opening between '\1' and '\2': width <b>\3 mm</b>, depth \4 mm, height \5 mm"),
    (r"<b>(\d+) sahtlit</b>: esipaneel (\S+) mm kõrge; kast (.+?) mm \(L×S×K\); siinid (\S+) mm; põhi (\S+) mm",
     r"<b>\1 drawers</b>: front \2 mm high; box \3 mm (W×D×H); slides \4 mm; bottom \5 mm"),
    (r"Valitud plaadi '(.+?)' alla nurkadesse", r"Under the selected panel '\1', in the corners"),
    (r"(\S) väiksem pool \(−(\S)\)", r"\1 smaller side (−\2)"),
    (r"(\S) suurem pool \(\+(\S)\)", r"\1 larger side (+\2)"),
    (r"Vaba sügavust on (\S+) mm – liiga vähe \(lühim siin 250 mm\)\.",
     r"Free depth is \1 mm – too little (shortest slide 250 mm)."),
    (r"Vaba sügavus piiratud teise detailiga: (\S+) mm", r"Free depth limited by another part: \1 mm"),
    (r"Kasti sisemõõt on üle (\d+) mm – ", r"Inner box width is over \1 mm – "),
    (r"Alus (\S+) × (\S+) mm, siinid (\S+) mm", r"Tray \1 × \2 mm, slides \3 mm"),
    (r", siini aluslatid (\S+) mm paksused \(täidavad vahe küljeseinteni\)",
     r", slide spacer battens \1 mm thick (fill the gap to the side panels)"),
    (r"Sammud: (\d+)\. Kas tahad enne samme vaadata/muuta\?", r"Steps: \1. Do you want to review/edit the steps first?"),
    (r"'(.+?)' ei ole telgedega joondatud \(pööra 90° kaupa\)\.", r"'\1' is not axis-aligned (rotate in 90° steps)."),
    (r"(.+?) vajab, et detaili B serv oleks vastu detaili A pinda\.", r"\1 needs the edge of part B against the face of part A."),
    (r"(.+?) on kahe pinnapidi kokku pandud plaadi jaoks\.", r"\1 is for two panels joined face to face."),
    (r"Kõrgus (\S+) mm", r"Height \1 mm"),
    (r"Lisatud (\d+) jalga", r"Added \1 legs"),
    (r"Valitud (\d+) detaili\.", r"\1 parts selected."),
    (r"(\d+) auku", r"\1 holes"),
    (r"Samm (\d+): ", r"Step \1: "),
    (r"Sahtel (\d+)", r"Drawer \1"),
    (r"Klaviatuurisahtel (\d+)", r"Keyboard tray \1"),
]
TEMPLATES = [(re.compile(a), b) for a, b in TEMPLATES]

# ---------------------------------------------------------------- fraasid (pikemad enne)
PHRASES = {
    # detailide nimed
    "– esipaneel": "– front panel", "– põhja tugiliist": "– bottom support batten", "– põhi": "– bottom",
    "– külg V": "– side L", "– külg P": "– side R", "– kasti esiosa": "– box front", "– tagaosa": "– box back",
    "– siini aluslatt V": "– slide spacer L", "– siini aluslatt P": "– slide spacer R",
    "– siin V": "– slide L", "– siin P": "– slide R", "– käepide": "– handle", "– alus": "– tray board",
    "– küljeliist V": "– side rail L", "– küljeliist P": "– side rail R", "– esiliist": "– front lip",
    "Klaviatuurisahtel": "Keyboard tray", "Raamjalg vasak": "Frame leg left", "Raamjalg parem": "Frame leg right",
    "Raamjalg": "Frame leg", "Jalg vasak ees": "Leg front left", "Jalg parem ees": "Leg front right",
    "Jalg vasak taga": "Leg back left", "Jalg parem taga": "Leg back right", "Jalg": "Leg",
    "Lauaplaat": "Tabletop", "Külg vasak": "Left side", "Külg parem": "Right side", "Tagapaneel": "Back panel",
    "Vahesein": "Divider", "(koopia)": "(copy)", "(teine pool)": "(other side)",
    # riistvara
    "Mööblipolt": "Furniture bolt", "ristmutter": "cross dowel", "kuppelmutter": "cap nut",
    "Minifix 15 ekstsentrik + polt": "Minifix 15 cam + bolt", "Puittüübel": "Wooden dowel",
    "Puidukruvi": "Wood screw", "Konfirmaat": "Confirmat", "Jalapolt": "Hanger bolt",
    "keermesmuhv": "threaded insert", "Käepideme kruvi": "Handle screw", "Klamber/nael": "Staple/nail",
    "Kuullaagersiin": "Ball-bearing slide", "Rullsiin": "Roller slide", "Sahtlisiin": "Drawer slide",
    "(paar)": "(pair)", "(siinid)": "(slides)", "(kast)": "(box)", "(esipaneel)": "(front panel)",
    "(põhi)": "(bottom)", "(tugiliist)": "(support batten)", "(aluslatid)": "(spacer battens)",
    "mööblipolt": "furniture bolt", "tüübel": "dowel", "konfirmaat": "confirmat", "puidukruvi": "wood screw",
    "jalapolt": "hanger bolt", "Käepide:": "Handle:",
    "vahe": "gap", "mm/pool": "mm/side", "pikk vastasmutter": "barrel nut",
    # olekuribad, info
    "Vaade:": "View:", "(lukus – L vabastab)": "(locked – L unlocks)", "(L = lukusta)": "(L = lock)",
    "Salvestatud:": "Saved:", "Eksporditud:": "Exported:", "Juhend valmis:": "Guide ready:",
    "Teen pilte:": "Rendering images:", "Ei saanud avada:": "Could not open:",
    "Detaili ei saanud luua:": "Could not create part:", "Juhendi tegemine ebaõnnestus:": "Creating the guide failed:",
    "Mõned kinnitused jäid lisamata:": "Some fasteners were not added:",
    "<b>Mõõdud:</b>": "<b>Dimensions:</b>", "<b>Allikas:</b>": "<b>Source:</b>", "<b>Ruumis:</b>": "<b>In space:</b>",
    "<b>Auke:</b>": "<b>Holes:</b>", "(näidatud tumedalt – kujund pole kinnine)": "(shown dark – shape is not closed)",
    "<b>Lai sahtel (&gt;600 mm):</b>": "<b>Wide drawer (&gt;600 mm):</b>", "paksem põhi": "thicker bottom",
    "+ keskmine tugiliist": "+ centre support batten", "– kasuta 45 kg siine": "– use 45 kg slides",
    "lisatud paksem põhi": "thicker bottom added", "lisatud põhja tugiliist": "bottom support batten added",
    "Kasuta tugevamaid (45 kg) siine.": "Use stronger (45 kg) slides.", " ja ": " and ",
    "Kogus": "Qty", "Materjal": "Material", "Auke": "Holes", "Mõõdud (mm)": "Dimensions (mm)",
    "Detailide ülevaade": "Parts overview", "Monteerimisjuhend": "Assembly guide", "Detailid": "Parts",
    "Kinnitused": "Fasteners", "Kinnitus": "Fastener", "Vaja:": "Needed:", "Kasuta:": "Use:",
    ", kõrgus": ", height", "kõrgus": "height", "toru": "tube", "Plaatide kogupindala": "Total panel area",
    "Klahvid": "Keys", "Abi": "Help", "salvestamata": "unsaved", "Sahtel": "Drawer",
    "mm, ": "mm, ", "tk": "pcs",
    # värvid jne kirjeldustes
    "must": "black", "valge": "white", "kroom": "chrome", "harjatud teras": "brushed steel", "messing": "brass",
    "antratsiit": "anthracite", "tamm": "oak", "pöök": "beech", "pähkel": "walnut", "mänd": "pine",
    "nahk pruun": "leather brown", "nahk must": "leather black", "kroom / hõbe": "chrome / silver",
}

EXACT.update({
    "💶 Hinnakiri": "💶 Price list", "Hinnakiri": "Price list", "Hinnakiri ja maksumus": "Price list and cost",
    "Materjalide ja tarvikute umbkaudne maksumus": "Approximate cost of materials and hardware",
    "💶 Maksumus": "💶 Cost", "📋 Hinnakiri": "📋 Price list", "Jääkide varu": "Waste allowance",
    "Plaadid:": "Panels:", "täisplaatidena (nii nagu poest ostad)": "as whole sheets (as you buy them)",
    "ainult kulunud m² järgi": "by used m² only", "Arvesta servakanti": "Include edge banding",
    "Rühm": "Group", "Nimetus": "Item", "Ühik": "Unit", "Ühikuhind €": "Unit price €", "Summa €": "Sum €",
    "Kopeeri tekstina": "Copy as text", "Kood": "Code", "Hind €": "Price €", "Pakis tk": "Pack qty",
    "Plaadi mõõt (L×L×P)": "Sheet size (L×W×T)", "Link": "Link", "Uuendatud": "Updated",
    "🔄 Uuenda hinnad internetist": "🔄 Update prices from the internet",
    "🔍 Otsi valitud reale toode poest…": "🔍 Find a shop product for the selected row…",
    "🌐 Ava link": "🌐 Open link", "💡 Võrdle hind.ee-s (brauseris)": "💡 Compare on hind.ee (browser)", "Taasta vaikehinnad": "Restore default prices",
    "💾 Salvesta hinnakiri": "💾 Save price list", "Otsi poest": "Search shop", "Pood": "Shop", "Otsing": "Search",
    "🔍 Otsi": "🔍 Search", "Plaadid": "Panels", "Tarvikud": "Hardware", "Plaat": "Panel", "Tarvik": "Hardware",
    "Vali tulemus ja vajuta OK – hind ja link salvestatakse hinnakirja reale.":
        "Choose a result and press OK – the price and link are saved to the price list row.",
    "Hinnad on umbkaudsed (KM-ga). Plaadimaterjali hind arvutatakse terve plaadi hinnast; teise paksuse korral arvutatakse hind paksuse järgi ümber. Täpsustamiseks muuda hinnakirja või otsi poest õige toode.":
        "Prices are approximate (incl. VAT). Panel cost is based on the whole-sheet price; for other thicknesses the price is scaled by thickness. To refine, edit the price list or find the right product in a shop.",
    "Hinnakiri asub failis hinnakiri.json programmi kaustas. Lingiga ridade hinna saab uuendada (Bauhof, Decora, Javicar jt poed, mis näitavad tooteandmeid). K-Rauta leht keelab automaatse lugemise – sealt hinna sisestamiseks kirjuta see käsitsi lahtrisse 'Hind €'.":
        "The price list is stored in hinnakiri.json in the program folder. Rows with a link can be updated (Bauhof, Decora, Javicar and other shops that publish product data). K-Rauta blocks automatic reading – type its prices into the 'Price €' cell by hand.",
    "Vali kõigepealt hinnakirjast rida.": "Select a row in the price list first.",
    "Taastan kõik vaikimisi hinnad?": "Restore all default prices?", "Vigane number.": "Invalid number.",
    "Salvesta maksumus": "Save cost", "Ei õnnestunud:": "Failed:",
    "Otsin… (iga toote hind loetakse eraldi, võtab mõne sekundi)": "Searching… (each product price is read separately, takes a few seconds)",
})
PHRASES.update({
    "KOKKU": "TOTAL", "maksumus": "cost", "detaili": "parts", "jääke": "waste", "plaat": "sheet",
    "hind paksuse järgi ümber arvutatud": "price scaled by thickness", "(käsitsi)": "(manual)",
    "kõik servad": "all edges", "Melamiinplaat": "Melamine board", "MDF plaat": "MDF board",
    "Vineer okaspuu": "Softwood plywood", "Puitkiudplaat kõva": "Hardboard", "Liimpuitkilp": "Glued wood panel",
    "Servakant ABS 2 mm (jooksev meeter)": "Edge banding ABS 2 mm (running metre)", "jm": "m",
    "Minifix 15 ekstsentrik + polt (komplekt)": "Minifix 15 cam + bolt (set)", "Ristmutter": "Cross dowel",
    "lisaks poldile": "in addition to bolt", "Puidukruvid (keskmine hind)": "Wood screws (average price)",
    "Klambrid/naelad": "Staples/nails", "Sahtlisiinid kuullaagriga, lõpuni avanevad": "Ball-bearing drawer slides, full extension",
    "Sahtlisiinid rull-liuguriga": "Roller drawer slides", "Mööblinupp": "Furniture knob",
    "Nahkrihm-käepide": "Leather strap handle", "Puidust mööblijalg": "Wooden furniture leg",
    "Metallist mööblijalg kinnitusplaadiga": "Metal furniture leg with mounting plate",
    "Metallist raamjalg (U-jalg)": "Metal frame leg (U-leg)", "Muu tarvik": "Other hardware",
    "hinnanguline": "estimate", "lisa ise": "add yourself", "paar": "pair",
    "Materjalil": "Material", "pole hinnakirjas hinda": "has no price in the price list",
    "mõni detail on suurem kui plaat": "some part is larger than the sheet",
    "Leitud": "Found", "toodet. Vali sobiv ja vajuta OK.": "products. Choose one and press OK.",
    "Uuendatud": "Updated", "hinda.": "prices.", "Viga:": "Error:", "Salvestatud:": "Saved:",
})
EXACT.update({
    "💶 Maksumus": "💶 Cost", "Maksumus": "Cost",
    "Materjalide ja tarvikute nimekiri hindadega – hinnad sisestad ise": "Materials and hardware list with prices – you enter the prices",
    "Programm on täitnud vajalikud materjalid ja kogused. Kirjuta sinise taustaga lahtrisse ühikuhind koos käibemaksuga – summa arvutatakse ise. Hinnad jäävad meelde ka järgmisteks projektideks. Kollased read on veel ilma hinnata.":
        "The program has filled in the required materials and quantities. Type the unit price including VAT into the blue cells – the sum is calculated automatically. Prices are remembered for future projects. Yellow rows have no price yet.",
    "Valuuta": "Currency", "Jääkide varu": "Waste allowance", "Selgitus": "Details", "Plaadi mõõt": "Sheet size",
    "Ühikuhind (KM-ga)": "Unit price (incl. VAT)", "Summa": "Sum", "ainult kulunud osa järgi": "by used share only",
    "Tühjenda kõik hinnad": "Clear all prices", "Kustutan kõik sisestatud hinnad?": "Delete all entered prices?",
    "Plaadi ühikuhind on terve plaadi hind. Plaadi mõõtu saab muuta (nt 2800×2070) – selle järgi arvutatakse, mitu plaati on vaja.":
        "The panel unit price is the price of a whole sheet. You can change the sheet size (e.g. 2800×2070) – it is used to work out how many sheets are needed.",
    "Servakant": "Edge banding", "➕ Lisa oma rida": "➕ Add own row", "➖ Eemalda oma rida": "➖ Remove own row",
    "↺ Taasta arvutatud kogused": "↺ Restore calculated quantities", "Kruvisid jala kohta": "Screws per leg",
    "Mitu kruvi läheb ühe jala kinnitusplaadist (metalljalad)": "How many screws go through one leg's mounting plate (metal legs)", "Lisa oma rida": "Add own row",
    "Nimetus (nt Liim, Õli, Transport):": "Item (e.g. Glue, Oil, Delivery):", "Ühik:": "Unit:",
    "Vali tabelist enda lisatud rida.": "Select a row you added yourself.", "Lisatud": "Added", "Muu": "Other",
    "Plaadi ühikuhind on terve plaadi hind. Plaadi mõõtu saab muuta (nt 2800×2070) – selle järgi arvutatakse, mitu plaati on vaja. Kogust saab käsitsi muuta (oranž ✎) – see jääb selle projekti juurde; tühi lahter taastab programmi arvutuse.":
        "The panel unit price is the price of a whole sheet. You can change the sheet size (e.g. 2800×2070) – it is used to work out how many sheets are needed. Quantities can be changed by hand (orange ✎) – this stays with the project; an empty cell restores the calculated value.",
})
PHRASES.update({"Muudetud käsitsi. Programmi arvutus:": "Changed by hand. Calculated:",
                "Tühjenda lahter, et taastada.": "Clear the cell to restore.", "pakk": "pack", "h": "h"})

EXACT.update({
    "🚪 Lisa uksed…": "🚪 Add doors…", "📚 Lisa riiulid…": "📚 Add shelves…", "🧩 Mallid…": "🧩 Templates…",
    "Valmistamine": "Making", "Tööriistad:": "Tools:", "📏 Mõõda": "📏 Measure", "📐 Üldmõõdud": "📐 Overall size",
    "✂ Lõikeplaan": "✂ Cutting plan", "🔩 Puurimisjoonised": "🔩 Drilling drawings", "⚠ Kontrolli": "⚠ Check",
    "🖼 Esitlus": "🖼 Presentation", "Vali grupp": "Select group", "Vali kõik": "Select all",
    "Kliki kahte punkti – näitab kaugust. Esc lõpetab.": "Click two points – shows the distance. Esc ends.",
    "Näita mööbli laiust, sügavust ja kõrgust 3D vaates": "Show width, depth and height in the 3D view",
    "Detailide paigutus täisplaatidele": "Layout of parts on full sheets",
    "Iga detaili augud koos mõõtudega": "Holes of each part with dimensions",
    "Otsi kokkupõrkeid ja vigaseid auke": "Find collisions and faulty holes",
    "Ilus pilt või PDF koos mõõtudega": "Nice image or PDF with dimensions",
    "Vali kõik sama grupi detailid (nt terve sahtel)": "Select all parts of the same group (e.g. a whole drawer)",
    "Servakant": "Edge banding", "Pikk serv 1": "Long edge 1", "Pikk serv 2": "Long edge 2",
    "Lühike serv 1": "Short edge 1", "Lühike serv 2": "Short edge 2", "Paksus mm": "Thickness mm",
    "Kõik servad": "All edges", "Puudub": "None", "Kehtib kõigile valitud detailidele": "Applies to all selected parts",
    "Pind": "Surface", "Ühtlane värv": "Plain colour", "Saar": "Ash", "Kask": "Birch", "Valge läige": "White gloss",
    "Must matt": "Matt black", "Betoon": "Concrete",
    "MÕÕTMINE: kliki kahte punkti detailide pinnal. Esc = lõpeta.": "MEASURE: click two points on part surfaces. Esc = finish.",
    "Sellel detailil pole gruppi.": "This part has no group.",
    "Vali kaks küljeseina: kliki esimesel, siis Ctrl + klikk teisel.": "Select two side panels: click the first, then Ctrl + click the second.",
    "Uksed": "Doors", "Riiulid": "Shelves", "Lisa uksed": "Add doors", "Lisa riiulid": "Add shelves", "Mallid": "Templates",
    "Uste arv": "Number of doors", "1 uks": "1 door", "2 ust (paariuks)": "2 doors (pair)",
    "Peale (katab korpuse servad)": "Overlay (covers carcass edges)", "Sisse (korpuse sisse, tasa)": "Inset (flush in carcass)",
    "Hinged (1 uks)": "Hinges (1 door)", "Vasakul": "Left", "Paremal": "Right",
    "Klaasuks (5 mm klaas, klaasihinged)": "Glass door (5 mm glass, glass hinges)",
    "Hingede arv valitakse ukse kõrguse järgi (2–5). Kausi ava Ø35 × 12 mm, paigaldusplaadi augud 37 mm esiservast.":
        "The number of hinges follows the door height (2–5). Cup hole Ø35 × 12 mm, mounting plate holes 37 mm from the front edge.",
    "Riiulite arv": "Number of shelves", "Ala alumine serv (Z)": "Area bottom edge (Z)", "Ala ülemine serv (Z)": "Area top edge (Z)",
    "Tagasi esiservast": "Set back from front edge",
    "Puuri 32 mm süsteemi augud (reguleeritavad riiulid)": "Drill 32 mm system holes (adjustable shelves)",
    "Augud Ø5 × 10 mm, 37 mm esi- ja tagaservast, iga 32 mm järel. Iga riiul: 4 riiulikandurit.":
        "Holes Ø5 × 10 mm, 37 mm from front and back edges, every 32 mm. Each shelf: 4 shelf supports.",
    "Mööbel": "Furniture", "Laius": "Width", "Sügavus": "Depth", "Plaadi paksus": "Board thickness",
    "Riiuleid": "Shelves", "Uksi": "Doors", "Sahtleid": "Drawers", "Sokli kõrgus": "Plinth height",
    "Madratsi laius": "Mattress width", "Madratsi pikkus": "Mattress length", "Raami kõrgus": "Frame height",
    "Korpuse kinnitus": "Carcass fastener", "Korpuse värv": "Carcass colour", "Uste/esipaneelide värv": "Door/front colour",
    "Tagasein (HDF)": "Back panel (HDF)",
    "Pärast loomist saad iga detaili, kinnitust ja mõõtu muuta nagu tavaliselt.": "After creating you can change every part, fastener and size as usual.",
    "Kapp (korpus, uksed, riiulid)": "Cabinet (carcass, doors, shelves)", "Riiul (avatud)": "Shelf unit (open)",
    "Kummut (sahtlid)": "Chest of drawers", "Öökapp": "Bedside table", "Voodiraam": "Bed frame",
    "Lõikeplaan": "Cutting plan", "Arvesta süüsuunda (ära pööra detaile)": "Respect grain direction (do not rotate parts)",
    "💾 Salvesta PDF": "💾 Save PDF", "Plaate pole.": "No panels.",
    "Kontroll": "Check", "Esitluspilt": "Presentation image", "Pealkiri": "Title", "Alapealkiri": "Subtitle",
    "Praegune vaade": "Current view", "Isomeetriline": "Isometric", "Näita üldmõõte": "Show overall size",
    "Lisa materjalide kokkuvõte": "Add materials summary", "Fail": "File", "PNG pilt": "PNG image", "PDF (A4)": "PDF (A4)",
    "Puurimisjoonised": "Drilling drawings", "Ainult aukudega detailid": "Only parts with holes",
    "💾 Salvesta PDF (kõik nimekirjas)": "💾 Save PDF (all in list)", "🖼 Salvesta pilt (valitud)": "🖼 Save image (selected)",
    "Sügavus": "Depth", "Koht": "Location", "pealt": "top", "alt": "bottom", "läbi": "through", "serv": "edge",
    "Peitehing 35 mm (kausshing)": "Concealed hinge 35 mm (cup hinge)", "Lõikemõõt": "Cut size",
    "Lõikepikkus mm": "Cut length mm", "Lõikelaius mm": "Cut width mm", "Üldmõõdud": "Overall size",
    "Salvesta esitlus": "Save presentation",
})
PHRASES.update({
    "Peitehing 35 mm + paigaldusplaat": "Concealed hinge 35 mm + mounting plate", "Peitehinge kruvid": "Hinge screws",
    "Riiulikandur": "Shelf support", "Pealne": "Top", "Põhi": "Bottom", "Sokkel": "Plinth", "Tagasein": "Back panel",
    "Uks": "Door", "– uks": "– door", "Riiul": "Shelf", "Peaots": "Headboard", "Jalutsiots": "Footboard",
    "Külgpuu vasak": "Side rail left", "Külgpuu parem": "Side rail right", "Liistukandur vasak": "Slat ledger left",
    "Liistukandur parem": "Slat ledger right", "Keskpuu tugijalg": "Centre beam leg", "Keskpuu kinnitusnurk": "Centre beam bracket",
    "Keskpuu": "Centre beam", "Voodiliistud": "Bed slats", "Liist": "Slat", "(liistukandur)": "(slat ledger)",
    "(liistud)": "(slats)", "(tagasein)": "(back panel)", "lõikeplaani järgi": "from cutting plan",
    "määratud servad, +10%": "assigned edges, +10%", "kõik servad (umbkaudu), +10%": "all edges (approx.), +10%",
    "kasutus": "use", "ei mahu": "does not fit", "ei mahu plaadile": "does not fit on sheet", "samm 32": "pitch 32",
    "Detailid lähevad üksteise sisse": "Parts overlap", "on plaadist väljas": "is outside the board",
    "on serva lähedal": "is close to the edge", "jätab põhja alla 1 mm – võib läbi minna": "leaves less than 1 mm – may break through",
    "servaauk": "edge hole", "väljub plaadist": "exits the board", "on plaadi pinna lähedal": "is close to the board surface",
    "Leitud": "Found", "kohta. Topeltklikk valib detailid 3D vaates.": "issues. Double-click selects the parts in 3D.",
    "✔ Probleeme ei leitud: detailid ei lähe üksteise sisse ja augud on korras.": "✔ No problems found: parts do not overlap and holes are fine.",
    "Valitud grupp": "Selected group", "Kaugus:": "Distance:", "Mall loodud:": "Template created:",
    "ust koos hingedega.": "doors with hinges.", "ja veel": "and", "rida": "more rows",
    "X/Y nullpunkt = vasak alumine nurk (punane 0), vaade pealt. Tume ring = auk pealt, hele = alt. Roheline kriipsjoon = servaauk.":
        "X/Y origin = bottom left corner (red 0), top view. Dark circle = hole from top, light = from bottom. Green dashed = edge hole.",
    "Saelõige": "Saw kerf", "servast äralõige": "edge trim", "Plaadi mõõdu saad muuta aknas 'Maksumus'.": "Change sheet size in the 'Cost' window.",
    "Kustutan": "Delete", "valitud detaili (ja nende kinnitused)?": "selected parts (and their fasteners)?",
})
PHRASES.update({"Hind puudub": "Price missing for", "real": "rows", "kõik servad, +10%": "all edges, +10%",
                "Detail": "Part", "Valmis!": "Done!", "Samm": "Step"})
# nimed (kinnitused, jalad, käepidemed, materjalid) võivad olla ka pikemate tekstide sees
for _k, _v in EXACT.items():
    if 6 <= len(_k) <= 60 and "\n" not in _k and _k not in PHRASES and not _k.endswith((":", "…", "?", ".")):
        PHRASES[_k] = _v
_PH = sorted(PHRASES.items(), key=lambda kv: -len(kv[0]))
_PH_RX = [(re.compile(r"(?<![\w])" + re.escape(a) + r"(?![\w])"), b) for a, b in _PH]
_EXACT_ALL = dict(EXACT)


def _core(s):
    if s in _EXACT_ALL:
        return _EXACT_ALL[s]
    out = s
    for rx, rep in TEMPLATES:
        out = rx.sub(rep, out)
    for rx, rep in _PH_RX:
        out = rx.sub(rep.replace("\\", "\\\\"), out)
    # pärast malli võib osa olla täpne vaste (nt "Attach Lauaplaat to ...")
    return out


def T(s, **kw):
    if s is None:
        return s
    if lang() == "en" and isinstance(s, str) and s.strip():
        lead = s[:len(s) - len(s.lstrip())]
        trail = s[len(s.rstrip()):]
        core = s.strip()
        if core in _EXACT_ALL:
            s = lead + _EXACT_ALL[core] + trail
        else:
            # tõlgi ka nimed mallide sees
            s = lead + _core(core) + trail
    if kw:
        try:
            s = s.format(**kw)
        except Exception:
            pass
    return s


def Tx(s):
    """Tõlge ka siis, kui tekstis on andmed (detailide nimed jne)."""
    return T(s)


# ---------------------------------------------------------------- vidinate tõlkimine
def _swap(obj, key, get, setv):
    """Jätab originaali meelde ja paneb tõlke. Töötab ka keele tagasivahetamisel."""
    cur = get()
    if not isinstance(cur, str) or not cur:
        return
    src = obj.property("_i18n_src_" + key)
    shown = obj.property("_i18n_tr_" + key)
    if src is None or cur != shown:
        src = cur
    new = T(src) if lang() == "en" else src
    obj.setProperty("_i18n_src_" + key, src)
    obj.setProperty("_i18n_tr_" + key, new)
    if new != cur:
        setv(new)


def translate_tree(root):
    from PySide6.QtWidgets import (QWidget, QLabel, QAbstractButton, QGroupBox, QComboBox, QDockWidget,
                                   QTabWidget, QTableWidget, QLineEdit, QPlainTextEdit, QMenu, QListWidget)
    from PySide6.QtGui import QAction
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        try:
            if w.isWindow() or isinstance(w, QDockWidget):
                _swap(w, "title", w.windowTitle, w.setWindowTitle)
            if isinstance(w, QLabel):
                _swap(w, "text", w.text, w.setText)
            elif isinstance(w, QAbstractButton):
                _swap(w, "text", w.text, w.setText)
            elif isinstance(w, QGroupBox):
                _swap(w, "title", w.title, w.setTitle)
            elif isinstance(w, QMenu):
                _swap(w, "title", w.title, w.setTitle)
            elif isinstance(w, QComboBox):
                for i in range(w.count()):
                    key = f"item{i}"
                    _swap(w, key, lambda i=i: w.itemText(i), lambda v, i=i: w.setItemText(i, v))
            elif isinstance(w, QTabWidget):
                for i in range(w.count()):
                    _swap(w, f"tab{i}", lambda i=i: w.tabText(i), lambda v, i=i: w.setTabText(i, v))
            elif isinstance(w, QTableWidget):
                for i in range(w.columnCount()):
                    it = w.horizontalHeaderItem(i)
                    if it is not None:
                        _swap(w, f"hdr{i}", it.text, it.setText)
            if isinstance(w, (QLineEdit, QPlainTextEdit)):
                _swap(w, "ph", w.placeholderText, w.setPlaceholderText)
            if w.toolTip():
                _swap(w, "tip", w.toolTip, w.setToolTip)
        except RuntimeError:
            continue
    for a in root.findChildren(QAction):
        try:
            _swap(a, "text", a.text, a.setText)
            if a.toolTip() and a.toolTip() != a.text():
                _swap(a, "tip", a.toolTip, a.setToolTip)
            if a.statusTip():
                _swap(a, "stip", a.statusTip, a.setStatusTip)
        except RuntimeError:
            continue


class ShowTranslator:
    """Tõlgib iga akna (dialoogid, teated) selle avamisel."""

    def __init__(self):
        from PySide6.QtCore import QObject, QEvent

        class _F(QObject):
            def eventFilter(self_, obj, ev):
                if ev.type() == QEvent.Show and hasattr(obj, "isWindow") and obj.isWindow():
                    if lang() == "en":
                        try:
                            translate_tree(obj)
                        except Exception:
                            pass
                return False
        self.f = _F()

    def install(self, app):
        app.installEventFilter(self.f)


# ---------------------------------------------------------------- lipud
def flag_icon(code, w=30, h=20):
    from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QPolygonF, QIcon
    from PySide6.QtCore import Qt, QPointF, QRectF
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if code == "et":
        for i, c in enumerate(("#0072CE", "#000000", "#FFFFFF")):
            p.fillRect(QRectF(0, i * h / 3, w, h / 3 + 0.5), QColor(c))
    else:   # Ühendkuningriik
        p.fillRect(QRectF(0, 0, w, h), QColor("#012169"))
        p.setPen(QPen(QColor("#FFFFFF"), h * 0.2))
        p.drawLine(QPointF(0, 0), QPointF(w, h)); p.drawLine(QPointF(w, 0), QPointF(0, h))
        p.setPen(QPen(QColor("#C8102E"), h * 0.07))
        p.drawLine(QPointF(0, 0), QPointF(w, h)); p.drawLine(QPointF(w, 0), QPointF(0, h))
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(w / 2 - h * 0.17, 0, h * 0.34, h), QColor("#FFFFFF"))
        p.fillRect(QRectF(0, h / 2 - h * 0.17, w, h * 0.34), QColor("#FFFFFF"))
        p.fillRect(QRectF(w / 2 - h * 0.1, 0, h * 0.2, h), QColor("#C8102E"))
        p.fillRect(QRectF(0, h / 2 - h * 0.1, w, h * 0.2), QColor("#C8102E"))
    p.setPen(QPen(QColor(0, 0, 0, 90), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(0.5, 0.5, w - 1, h - 1))
    p.end()
    return QIcon(pm)
