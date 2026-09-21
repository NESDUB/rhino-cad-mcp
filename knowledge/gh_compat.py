#!/usr/bin/env python3
import json, argparse, re
from pathlib import Path

# ---- Type rules -------------------------------------------------------------
GENERIC_TYPES = {"Generic Data","Goo"}
GEOMETRY_TYPES = {
    "Geometry","Curve","Brep","Surface","SubD","Mesh","Point","Line","Arc","Circle","Polyline","PolyCurve","Ellipse","NurbsCurve","Rectangle","Box"
}
CURVE_SUPERTYPE = "Curve"
CURVE_SUBTYPES = {"Line","Arc","Circle","Polyline","PolyCurve","Ellipse","NurbsCurve","Rectangle"}  # rectangle often travels as curve

ALIASES = {
    "Goo":"Generic Data",
    "Text Pattern":"Text",
    "Integer":"Number",
    "Nurbs Curve":"NurbsCurve",
    "Polyline Curve":"Polyline",
    "Mesh Face":"Mesh",   # conservative
}

def norm(t: str) -> str:
    t = (t or "").strip()
    t = ALIASES.get(t, t)
    t = re.sub(r"\s+", " ", t)
    return t

def is_safe_compatible(out_t: str, in_t: str) -> bool:
    o, i = norm(out_t), norm(in_t)
    if i in GENERIC_TYPES: return True
    if i == o: return True
    if i == "Geometry" and o in GEOMETRY_TYPES: return True
    if i == CURVE_SUPERTYPE and o in CURVE_SUBTYPES: return True
    # Circle → Curve, Line → Curve, etc, already covered above.
    return False

def is_maybe_convertible(out_t: str, in_t: str) -> bool:
    # Things GH can sometimes coerce but may fail at runtime (supertype→subtype).
    o, i = norm(out_t), norm(in_t)
    if o == CURVE_SUPERTYPE and i in {"Circle","Arc","Line","Ellipse","Polyline"}:
        return True  # requires circle-fit/arc-fit/etc.
    # geometry→specific geometry (e.g., Geometry → Curve) might work if the value actually is that kind
    if o in GEOMETRY_TYPES and i in GEOMETRY_TYPES and i != o:
        return True
    return False

# ---- Data model -------------------------------------------------------------
def load_nodes(path: Path):
    data = json.loads(path.read_text())
    # keep only items that have I/O metadata
    nodes = []
    for it in data:
        inputs = it.get("inputs") or []
        outputs = it.get("outputs") or []
        nodes.append({
            "name": it.get("name"),
            "nick": it.get("nickName"),
            "guid": it.get("guid"),
            "kind": it.get("kind"),
            "category": it.get("category"),
            "subCategory": it.get("subCategory"),
            "library": it.get("libraryName"),
            "inputs": [{"name":p.get("name"),"nick":p.get("nickName"),"type":norm(p.get("typeName"))} for p in inputs],
            "outputs":[{"name":p.get("name"),"nick":p.get("nickName"),"type":norm(p.get("typeName"))} for p in outputs],
        })
    return nodes

def find_by_output_type(nodes, out_type: str):
    out_type = norm(out_type)
    safe, maybe = [], []
    for n in nodes:
        for inp in n["inputs"]:
            t = inp["type"]
            if is_safe_compatible(out_type, t):
                safe.append((n, inp))
            elif is_maybe_convertible(out_type, t):
                maybe.append((n, inp))
    return safe, maybe

def find_output_type_of(nodes, name_contains: str, out_nick: str):
    # helper if you want to target a specific component + port, e.g., Radial grid 'C'
    name_contains = name_contains.lower()
    matches = [n for n in nodes if name_contains in (n["name"] or "").lower()]
    for n in matches:
        for o in n["outputs"]:
            if (o["nick"] or "").lower() == out_nick.lower():
                return o["type"], n
    return None, None

# ---- CLI --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="List components with inputs compatible with an output type.")
    ap.add_argument("json_path")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out-type", help="Explicit output type, e.g. Curve")
    g.add_argument("--from-component", help="Fuzzy component name to read output type from, e.g. Radial")
    ap.add_argument("--out-port", help="Output nickname to read from the component (e.g. C, P)")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    nodes = load_nodes(Path(args.json_path))

    out_type = args.out_type
    if not out_type and args.from_component and args.out_port:
        out_type, src = find_output_type_of(nodes, args.from_component, args.out_port)
        if not out_type:
            raise SystemExit("Could not resolve output type from component+port; double-check names.")
        print(f"# Source: {src['name']} • port {args.out_port} → type {out_type}")

    if not out_type:
        raise SystemExit("--out-type or (--from-component + --out-port) is required")

    safe, maybe = find_by_output_type(nodes, out_type)

    def fmt(items, title):
        print(f"\n## {title} ({len(items)})")
        for (n, inp) in items[:args.limit]:
            print(f"- {n['name']} [{n['category']} > {n['subCategory']} • {n['kind']}]"
                  f" — input {inp['nick'] or inp['name']} : {inp['type']}")

    fmt(safe, f"Safe matches for {out_type}")
    fmt(maybe, f"Maybe/convertible matches for {out_type} (could need a fit/cast)")

if __name__ == "__main__":
    main()
