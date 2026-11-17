"""Andmemudel: detailid, augud, kinnitused, monteerimissammud, projekt."""
import json
import copy
import numpy as np
import trimesh

from . import geom

MATERIALS = ["Puitlaastplaat (LMDP)", "MDF", "Vineer", "Täispuit", "Liimpuit",
             "Metall", "Klaas", "Plast", "Muu"]

PALETTE = ["#d9b98c", "#c49a6c", "#e8d3b0", "#a87b51", "#bfc7cf", "#9fb7a0",
           "#d8a7a0", "#a9b4d6", "#e6cf8a", "#b8a1c9"]


class Hole:
    def __init__(self, origin, direction, diameter, depth, fastener_id=None, label=""):
        self.origin = [float(x) for x in origin]
        self.direction = [float(x) for x in geom.unit(direction)]
        self.diameter = float(diameter)
        self.depth = float(depth)
        self.fastener_id = fastener_id
        self.label = label

    def to_dict(self):
        return dict(origin=self.origin, direction=self.direction, diameter=self.diameter,
                    depth=self.depth, fastener_id=self.fastener_id, label=self.label)

    @classmethod
    def from_dict(cls, d):
        return cls(d["origin"], d["direction"], d["diameter"], d["depth"],
                   d.get("fastener_id"), d.get("label", ""))


class Part:
    def __init__(self, pid, name="Detail", kind="plate"):
        self.id = pid
        self.name = name
        self.kind = kind              # 'plate' (kontuur + paksus) või 'mesh'
        self.source = "rect"          # rect / image / ai / file
        self.outline = geom.rect_outline(600, 400)
        self.inner = []               # sisemised augud kontuuris (2D)
        self.thickness = 18.0
        self.rect = [600.0, 400.0, 0.0]   # laius, kõrgus, nurgaraadius (kui source == rect)
        self.mesh_v = None
        self.mesh_f = None
        self.material = MATERIALS[0]
        self.color = PALETTE[0]
        self.description = ""
        self.position = [0.0, 0.0, 0.0]
        self.rotation = np.eye(3).ravel().tolist()
        self.holes = []
        self.qty_note = ""
        self.role = None        # None / 'slide' / 'handle' / 'leg'
        self.group = ""         # nt "Sahtel 1" – monteerimisjuhendis üks samm
        self.hw = []            # lisakinnitused: [[nimi, kogus], ...]
        self.handle = None      # käepideme seaded
        self.leg = None
        self.slide = None
        self.pull = None        # sahtli väljatõmbe suund (juhendi piltideks)
        self.edges = {}         # servakant: {"L1","L2" (pikad servad), "W1","W2" (lühikesed servad): paksus mm}
        self.finish = ""        # pinna välimus (tekstuur): "", "tamm", "pähkel", ...
        self._cache = {}

    # --------------------------------------------------------- teisendused
    @property
    def R(self):
        return np.asarray(self.rotation, float).reshape(3, 3)

    @R.setter
    def R(self, value):
        self.rotation = geom.clean_rotation(value).ravel().tolist()

    def transform(self):
        return geom.make_transform(self.R, self.position)

    def to_local_point(self, p):
        return self.R.T @ (np.asarray(p, float) - np.asarray(self.position))

    def to_local_dir(self, d):
        return self.R.T @ np.asarray(d, float)

    # --------------------------------------------------------- geomeetria
    def _geo_key(self):
        if self.kind == "plate":
            return json.dumps([self.outline, self.inner, self.thickness])
        return json.dumps([len(self.mesh_v or []), len(self.mesh_f or []),
                           (self.mesh_v or [[0]])[0]])

    def body_mesh(self):
        key = ("body", self._geo_key())
        if key not in self._cache:
            self._cache = {k: v for k, v in self._cache.items() if k[1] == key[1]}
            if self.kind == "plate":
                m = geom.plate_mesh(self.outline, self.inner, self.thickness)
            else:
                m = trimesh.Trimesh(np.asarray(self.mesh_v, float), np.asarray(self.mesh_f, np.int64),
                                    process=True)
            self._cache[key] = m
        return self._cache[key]

    def display_mesh(self):
        """Mesh koos puuritud aukudega. Tagastab (mesh, augud_lõigatud)."""
        hk = json.dumps([h.to_dict() for h in self.holes])
        key = ("disp", self._geo_key(), hk)
        if key not in self._cache:
            body = self.body_mesh()
            holes = [(h.origin, h.direction, h.diameter, h.depth) for h in self.holes]
            m, ok = geom.subtract_holes(body, holes)
            self._cache = {k: v for k, v in self._cache.items() if k[0] == "body"}
            self._cache[key] = (m, ok)
        return self._cache[key]

    def world_body_mesh(self):
        m = self.body_mesh().copy()
        m.apply_transform(self.transform())
        return m

    def world_bounds(self):
        v = np.asarray(self.body_mesh().vertices)
        w = v @ self.R.T + np.asarray(self.position)
        return w.min(axis=0), w.max(axis=0)

    def dims(self):
        """Lõikemõõdud (pikkus, laius, paksus) mm."""
        if self.kind == "plate":
            o = np.asarray(self.outline)
            w, h = o[:, 0].max() - o[:, 0].min(), o[:, 1].max() - o[:, 1].min()
            a, b = max(w, h), min(w, h)
            return [round(a, 1), round(b, 1), round(self.thickness, 1)]
        e = sorted(self.body_mesh().extents, reverse=True)
        return [round(float(x), 1) for x in e]

    def edge_t(self, k):
        try:
            return float((self.edges or {}).get(k, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def cut_dims(self):
        """Lõikemõõdud enne kantimist: valmis mõõdust lahutatakse kandi paksus."""
        L, W, T = self.dims()
        if self.kind != "plate":
            return [L, W, T]
        return [round(L - self.edge_t("W1") - self.edge_t("W2"), 1),
                round(W - self.edge_t("L1") - self.edge_t("L2"), 1), T]

    def edge_lengths(self):
        """{kandi paksus: pikkus m}"""
        L, W, _ = self.dims()
        out = {}
        for k, ln in (("L1", L), ("L2", L), ("W1", W), ("W2", W)):
            t = self.edge_t(k)
            if t > 0:
                out[t] = out.get(t, 0.0) + ln / 1000.0
        return out

    def edge_code(self):
        """Lühike tähis nimekirja jaoks, nt 'L1 L2 W1 (2 mm)'."""
        ks = [k for k in ("L1", "L2", "W1", "W2") if self.edge_t(k) > 0]
        if not ks:
            return ""
        ts = sorted({self.edge_t(k) for k in ks})
        return " ".join(ks) + " (" + "/".join(f"{t:g}" for t in ts) + " mm)"

    def set_rect(self, w, h, r=0.0):
        self.rect = [float(w), float(h), float(r)]
        self.outline = geom.rect_outline(w, h, r)
        self.inner = []

    def thickness_axis_world(self):
        return self.R @ np.array([0, 0, 1.0])

    # --------------------------------------------------------- serialiseerimine
    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items() if not k.startswith("_") and k != "holes"}
        d["holes"] = [h.to_dict() for h in self.holes]
        return d

    @classmethod
    def from_dict(cls, d):
        p = cls(d["id"], d.get("name", "Detail"), d.get("kind", "plate"))
        for k, v in d.items():
            if k == "holes":
                continue
            setattr(p, k, v)
        p.holes = [Hole.from_dict(h) for h in d.get("holes", [])]
        p._cache = {}
        return p


class Fastener:
    def __init__(self, fid, ftype, params, a_id, b_id):
        self.id = fid
        self.ftype = ftype
        self.params = dict(params)
        self.a_id = a_id
        self.b_id = b_id
        self.hardware = []     # A detaili lokaalsetes koordinaatides: dict(origin,direction,diameter,length,color)
        self.axis = None       # [P_local, d_local] A koordinaatides

    def to_dict(self):
        return dict(id=self.id, ftype=self.ftype, params=self.params, a_id=self.a_id,
                    b_id=self.b_id, hardware=self.hardware, axis=self.axis)

    @classmethod
    def from_dict(cls, d):
        f = cls(d["id"], d["ftype"], d.get("params", {}), d["a_id"], d.get("b_id"))
        f.hardware = d.get("hardware", [])
        f.axis = d.get("axis")
        return f


class Step:
    def __init__(self, title="", part_ids=None, fastener_ids=None, note=""):
        self.title = title
        self.part_ids = list(part_ids or [])
        self.fastener_ids = list(fastener_ids or [])
        self.note = note

    def to_dict(self):
        return dict(title=self.title, part_ids=self.part_ids, fastener_ids=self.fastener_ids,
                    note=self.note)

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("title", ""), d.get("part_ids"), d.get("fastener_ids"), d.get("note", ""))


class Project:
    VERSION = 1

    def __init__(self):
        self.name = "Uus mööbel"
        self.parts = []
        self.fasteners = []
        self.steps = []
        self.assembly_order = []   # detailide id-d selles järjekorras, nagu neid kokku liideti
        self.qty_override = {}     # maksumuse aknas käsitsi muudetud kogused {rea võti: kogus}
        self.extra_rows = []       # kasutaja lisatud read [{name, unit, qty}]
        self.next_id = 1

    def new_id(self):
        i = self.next_id
        self.next_id += 1
        return i

    def part(self, pid):
        for p in self.parts:
            if p.id == pid:
                return p
        return None

    def fastener(self, fid):
        for f in self.fasteners:
            if f.id == fid:
                return f
        return None

    def add_part(self, part):
        self.parts.append(part)
        return part

    def remove_part(self, pid):
        for f in [f for f in self.fasteners if pid in (f.a_id, f.b_id)]:
            self.remove_fastener(f.id)
        self.parts = [p for p in self.parts if p.id != pid]
        self.assembly_order = [i for i in self.assembly_order if i != pid]
        for s in self.steps:
            s.part_ids = [i for i in s.part_ids if i != pid]

    def remove_fastener(self, fid):
        for p in self.parts:
            p.holes = [h for h in p.holes if h.fastener_id != fid]
        self.fasteners = [f for f in self.fasteners if f.id != fid]
        for s in self.steps:
            s.fastener_ids = [i for i in s.fastener_ids if i != fid]

    def note_assembled(self, *pids):
        for pid in pids:
            if pid not in self.assembly_order:
                self.assembly_order.append(pid)

    def centroid(self):
        if not self.parts:
            return np.zeros(3)
        pts = []
        for p in self.parts:
            lo, hi = p.world_bounds()
            pts.append((lo + hi) / 2)
        return np.mean(pts, axis=0)

    def bounds(self):
        if not self.parts:
            return np.zeros(3), np.ones(3) * 100
        los, his = zip(*[p.world_bounds() for p in self.parts])
        return np.min(los, axis=0), np.max(his, axis=0)

    # --------------------------------------------------------- sammud
    def auto_steps(self):
        order = [i for i in self.assembly_order if self.part(i)]
        for f in self.fasteners:
            for pid in (f.a_id, f.b_id):
                if pid is not None and pid not in order and self.part(pid):
                    order.append(pid)
        for p in self.parts:
            if p.id not in order:
                order.append(p.id)
        # sama grupi detailid (nt üks sahtel) ühte sammu, grupi esimese liikme kohale
        units = []
        gidx = {}
        for pid in order:
            g = getattr(self.part(pid), "group", "") or ""
            if g:
                if g in gidx:
                    units[gidx[g]][1].append(pid)
                    continue
                gidx[g] = len(units)
            units.append((g, [pid]))
        pos = {}
        for i, (_, pids) in enumerate(units):
            for pid in pids:
                pos[pid] = i
        steps = []
        for i, (g, pids) in enumerate(units):
            p = self.part(pids[0])
            fs = [f for f in self.fasteners
                  if max(pos.get(f.a_id, 0), pos.get(f.b_id, 0) if f.b_id else 0) == i]
            if g:
                title = f"Pane kokku ja paigalda: {g}"
            elif i == 0:
                title = f"Aseta {p.name} tööpinnale"
            else:
                others = sorted({self.part(x).name for f in fs for x in (f.a_id, f.b_id)
                                 if x is not None and x not in pids and self.part(x)})
                title = f"Kinnita {p.name}" + (f" detaili {', '.join(others)} külge" if others else "")
            note = ""
            if g:
                hw = {}
                for pid in pids:
                    for nm, q in (getattr(self.part(pid), "hw", None) or []):
                        hw[nm] = hw.get(nm, 0) + q
                if hw:
                    note = "Vaja: " + ", ".join(f"{q}× {nm}" for nm, q in hw.items())
            steps.append(Step(title, pids, [f.id for f in fs], note))
        self.steps = steps
        return steps

    # --------------------------------------------------------- salvestus
    def to_dict(self):
        return dict(version=self.VERSION, name=self.name, next_id=self.next_id,
                    parts=[p.to_dict() for p in self.parts],
                    fasteners=[f.to_dict() for f in self.fasteners],
                    steps=[s.to_dict() for s in self.steps],
                    assembly_order=self.assembly_order, qty_override=self.qty_override,
                    extra_rows=self.extra_rows)

    @classmethod
    def from_dict(cls, d):
        pr = cls()
        pr.name = d.get("name", "Mööbel")
        pr.next_id = d.get("next_id", 1)
        pr.parts = [Part.from_dict(x) for x in d.get("parts", [])]
        pr.fasteners = [Fastener.from_dict(x) for x in d.get("fasteners", [])]
        pr.steps = [Step.from_dict(x) for x in d.get("steps", [])]
        pr.assembly_order = d.get("assembly_order", [])
        pr.qty_override = d.get("qty_override", {})
        pr.extra_rows = d.get("extra_rows", [])
        return pr

    def save(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=1)

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def snapshot(self):
        return copy.deepcopy(self.to_dict())
