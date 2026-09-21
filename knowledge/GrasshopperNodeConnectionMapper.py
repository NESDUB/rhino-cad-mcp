# Grasshopper recipe report — neat layout + richer diagnostics
# Features:
# • [MISSING] flags, persistent defaults, geometry sources (sorted)
# • Inline TYPE MISMATCH tagging, error input attribution with input type labels
# • NODES — DEFINITIONS & I/O section listing every node with definition + full I/O
# • CONNECTIONS (expanded): includes real wires + any I/O with no connections or defaults
import Grasshopper
import Rhino
from Grasshopper.Kernel import IGH_Component, IGH_Param, GH_RuntimeMessageLevel, IGH_PreviewObject
from Grasshopper.Kernel.Special import GH_Relay, GH_NumberSlider, GH_Panel

# ========== toggles ==========
COMPACT = False  # True => omit fully isolated nodes (no inputs & no outputs)
SHOW_SAMPLE_VALUES = True  # include sample slider/panel values inline
MAX_SAMPLE_LIST = 3        # for previewing lists (IDs, stats etc.)


doc = ghenv.Component.OnPingDocument()
if not doc:
    print("Could not access the Grasshopper document.")
    a = ""
else:
    # ---------- helpers ----------
    def top_docobj_from_param(p):
        if p is None or p.Attributes is None:
            return None
        getter = getattr(p.Attributes, "GetTopLevel", None)
        if getter is None:
            return None
        return getattr(getter, "DocObject", None)

    def resolve_node_from_param(p):
        """Return (node, resolved_param) where node is component or floating param."""
        if p is None:
            return None, None
        d = top_docobj_from_param(p)
        if d is None:
            return None, None
        if isinstance(d, GH_Relay):
            return resolve_node_from_param(p.Sources[0] if p.SourceCount > 0 else None)
        if isinstance(d, (IGH_Component, IGH_Param)):
            return d, p
        return None, None

    def node_key(node):
        return str(node.InstanceGuid)

    def short_guid(node, n=6):
        g = node_key(node).replace("-", "")
        return g[:n].upper()

    def node_name(node):
        return (node.NickName or node.Name or type(node).__name__)

    def node_label(node):
        return f"{node_name(node)}#{short_guid(node)}"

    def port_name(param):
        return (param.NickName or param.Name or type(param).__name__)

    def port_index(param, direction):
        """Return 0-based index for component ports; None for floating params."""
        owner = top_docobj_from_param(param)
        if isinstance(owner, IGH_Component):
            lst = owner.Params.Input if direction == 'in' else owner.Params.Output
            for i, p in enumerate(lst):
                if p is param:
                    return i
        return None

    def port_tag(param, direction):
        n = port_name(param)
        idx = port_index(param, direction)
        return f"{n}[{idx}]" if idx is not None else n

    def port_type(param):
        try:
            return getattr(param, "TypeName", "") or ""
        except:
            return ""

    def sort_ports(port_tags):
        """Sort by numeric index if present in '[n]'."""
        def parse_index(tag):
            if "[" in tag and tag.endswith("]"):
                try:
                    return int(tag.split("[")[-1].rstrip("]"))
                except:
                    return 10**6
            return 10**6
        return sorted(port_tags, key=lambda t: (parse_index(t), t))

    def node_sort_key(n):
        cat = getattr(n, "Category", "") if isinstance(n, IGH_Component) else "~Param"
        sub = getattr(n, "SubCategory", "") if isinstance(n, IGH_Component) else ""
        return (cat, sub, n.Name, short_guid(n))

    # --- formatting / badges ---
    def slider_badge(sl):
        def fmt(x):
            try:
                return f"{float(x):.6g}"
            except Exception:
                return str(x)
        try:
            dp = getattr(sl.Slider, "DecimalPlaces", None)
            kind = "int" if isinstance(dp, int) and dp == 0 else "num"
            if SHOW_SAMPLE_VALUES:
                return f" ({kind}; min:{fmt(sl.Slider.Minimum)} val:{fmt(sl.CurrentValue)} max:{fmt(sl.Slider.Maximum)})"
            else:
                return f" ({kind})"
        except Exception:
            return ""

    def panel_badge(pn):
        try:
            txt = (pn.UserText or "").strip().replace("\n", " ")
            if not txt:
                return ""
            return f' ["{txt[:30]}{"…" if len(txt)>30 else ""}"]'
        except:
            return ""

    def node_badge(n):
        """Extra inline info for common param types."""
        try:
            if isinstance(n, GH_NumberSlider):
                return slider_badge(n)
            if isinstance(n, GH_Panel):
                return panel_badge(n)
            if isinstance(n, IGH_Param):
                cnt = getattr(n, "VolatileDataCount", None)
                if isinstance(cnt, int) and cnt > 0:
                    return f" [items:{cnt}]"
        except:
            pass
        return ""

    def param_items_count(p):
        try:
            c = getattr(p, "VolatileDataCount", None)
            return int(c) if isinstance(c, int) else None
        except:
            return None

    # ---------- doc context ----------
    rhdoc = Rhino.RhinoDoc.ActiveDoc
    unit_name = str(rhdoc.ModelUnitSystem) if rhdoc else "Unknown"
    abs_tol = rhdoc.ModelAbsoluteTolerance if rhdoc else 0.01
    ang_tol = rhdoc.ModelAngleToleranceDegrees if rhdoc else 1.0

    # ---------- collect nodes ----------
    nodes = []
    for obj in doc.Objects:
        if isinstance(obj, IGH_Component):
            nodes.append(obj)
        elif isinstance(obj, IGH_Param):
            attr = obj.Attributes
            if attr is not None and (attr.HasInputGrip or attr.HasOutputGrip):
                nodes.append(obj)
    nodes.sort(key=node_sort_key)
    node_by_key = {node_key(n): n for n in nodes}

    # capture positions
    node_pos = {}
    for n in nodes:
        try:
            pt = n.Attributes.Pivot  # System.Drawing.PointF
            node_pos[node_key(n)] = (int(round(pt.X)), int(round(pt.Y)))
        except:
            pass

    # ---------- build edge list + maps ----------
    # edges store keys + labels + ports; we'll enrich later with type checks
    edges = []  # (s_key, s_label, s_port, t_key, t_label, t_port)
    inputs_map, outputs_map = {}, {}
    input_param_ref, output_param_ref = {}, {}

    def add_input(tkey, tport, s_label, s_port, in_param):
        inputs_map.setdefault(tkey, {}).setdefault(tport, []).append((s_label, s_port))
        input_param_ref[(tkey, tport)] = in_param

    def add_output(skey, s_port, t_label, t_port, src_param):
        outputs_map.setdefault(skey, {}).setdefault(s_port, []).append((t_label, t_port))
        output_param_ref[(skey, s_port)] = src_param

    def iter_targets():
        for obj in doc.Objects:
            if isinstance(obj, IGH_Component):
                yield obj, list(obj.Params.Input)
            elif isinstance(obj, IGH_Param) and obj.SourceCount > 0:
                yield obj, [obj]

    for tgt_node, input_slots in iter_targets():
        for in_param in input_slots:
            if in_param.SourceCount == 0:
                continue
            for src_param in in_param.Sources:
                src_node, resolved_src = resolve_node_from_param(src_param)
                if not src_node:
                    continue
                s_key, t_key = node_key(src_node), node_key(tgt_node)
                s_label, t_label = node_label(src_node), node_label(tgt_node)
                s_port, t_port = port_tag(resolved_src, 'out'), port_tag(in_param, 'in')
                edges.append((s_key, s_label, s_port, t_key, t_label, t_port))
                add_input(t_key, t_port, s_label, s_port, in_param)
                add_output(s_key, s_port, t_label, t_port, resolved_src)

    for n in nodes:
        nk = node_key(n)
        inputs_map.setdefault(nk, {})
        outputs_map.setdefault(nk, {})

    # ---------- structural warnings (multi-sourced inputs) ----------
    structural_warnings = []
    for nkey, portmap in inputs_map.items():
        for tport, sources in portmap.items():
            if len(sources) > 1:
                nlabel = node_label(node_by_key[nkey])
                structural_warnings.append(f"Input {nlabel}.{tport} has {len(sources)} sources")

    # ---------- GH runtime messages (errors/warnings) ----------
    node_status = {}  # key -> dict(level -> [msgs])
    gh_errors = []    # list of (nk, nlabel, msg)
    gh_warnings = []  # list of (nk, nlabel, msg)

    def _add_status(nk, level_name, msg):
        d = node_status.setdefault(nk, {})
        d.setdefault(level_name, []).append(msg)

    for n in nodes:
        nk = node_key(n)
        for msg in n.RuntimeMessages(GH_RuntimeMessageLevel.Error):
            gh_errors.append((nk, node_label(n), msg))
            _add_status(nk, "ERROR", msg)
        for msg in n.RuntimeMessages(GH_RuntimeMessageLevel.Warning):
            gh_warnings.append((nk, node_label(n), msg))
            _add_status(nk, "WARNING", msg)

    # ---------- node flags (preview/locked/enabled) ----------
    def node_flags(n):
        flags = []
        try:
            if isinstance(n, IGH_PreviewObject) and n.Hidden:
                flags.append("H")  # preview hidden
        except:
            pass
        try:
            if hasattr(n, "Locked") and n.Locked:
                flags.append("L")
        except:
            pass
        try:
            if hasattr(n, "Enabled") and (not n.Enabled):
                flags.append("D")  # disabled
        except:
            pass
        return "[" + "".join(flags) + "]" if flags else "[ ]"

    # ---------- persistent values + [MISSING] ----------
    def has_persistent(param):
        pd = getattr(param, "PersistentData", None)
        try:
            return (pd is not None) and (not pd.IsEmpty)
        except:
            return False

    def first_persistent(param):
        """Return (val, label) for a param's first persistent item if any."""
        pd = getattr(param, "PersistentData", None)
        if not pd:
            return None, None
        try:
            if pd.IsEmpty:
                return None, None
            enumer = pd.AllData(True) if hasattr(pd, "AllData") else None
            item = None
            if enumer:
                for x in enumer:
                    item = x
                    break
            else:
                br = pd.get_Branch(0) if hasattr(pd, "get_Branch") else None
                if br and len(br) > 0:
                    item = br[0]
            if item is None:
                return None, None
            val = getattr(item, "Value", None)
            label = type(item).__name__
            return (val if val is not None else str(item)), label
        except:
            return None, None

    def missing_required(param):
        try:
            if getattr(param, "Optional", False):
                return False
            if param.SourceCount > 0:
                return False
            return not has_persistent(param)
        except:
            return False

    # ---------- geometry source analysis ----------
    def geom_summary_from_goo(goo):
        try:
            tn = type(goo).__name__
            is_ref = getattr(goo, "IsReferencedGeometry", False)
            rid = None
            if is_ref:
                rid = getattr(goo, "ReferenceID", None)
            val = getattr(goo, "Value", None)
            stats = ""
            if val is None:
                return tn, is_ref, rid, stats
            if isinstance(val, Rhino.Geometry.Mesh):
                stats = "V:{0} F:{1}".format(val.Vertices.Count, val.Faces.Count)
            elif isinstance(val, Rhino.Geometry.Curve):
                try:
                    length = val.GetLength(abs_tol)
                    stats = "Length:{0:.3f}".format(length)
                except:
                    stats = "Curve"
            elif isinstance(val, Rhino.Geometry.Brep):
                stats = "Faces:{0} Edges:{1}".format(val.Faces.Count, val.Edges.Count)
            elif isinstance(val, Rhino.Geometry.Surface):
                bb = val.GetBoundingBox(True)
                diag = bb.Diagonal.Length
                stats = "BBoxDiag:{0:.3f}".format(diag)
            elif isinstance(val, Rhino.Geometry.Point3d):
                stats = "({0:.3g},{1:.3g},{2:.3g})".format(val.X, val.Y, val.Z)
            return tn, is_ref, rid, stats
        except:
            return "Goo", False, None, ""

    def is_geom_param(p):
        t = (port_type(p) or "").lower()
        return any(k in t for k in ["curve", "brep", "mesh", "surface", "point", "geometry"])

    geometry_sources = []

    def add_geometry_param_info(param_owner):
        if not isinstance(param_owner, IGH_Param):
            return
        if not is_geom_param(param_owner):
            return
        entry = {
            "label": node_label(param_owner),
            "type": port_type(param_owner) or type(param_owner).__name__,
            "referenced": False,
            "internalized": False,
            "ref_ids": [],
            "count": 0,
            "stats": []
        }
        try:
            data_enumer = None
            if param_owner.VolatileDataCount and param_owner.VolatileData is not None:
                data_enumer = param_owner.VolatileData.AllData(True)
            elif has_persistent(param_owner):
                pd = param_owner.PersistentData
                data_enumer = pd.AllData(True) if hasattr(pd, "AllData") else None
            if data_enumer is not None:
                c = 0
                for goo in data_enumer:
                    c += 1
                    tn, is_ref, rid, st = geom_summary_from_goo(goo)
                    entry["referenced"] = entry["referenced"] or bool(is_ref)
                    entry["internalized"] = entry["internalized"] or (not is_ref)
                    if rid:
                        entry["ref_ids"].append(str(rid))
                    if st:
                        entry["stats"].append(st)
                entry["count"] = c
                geometry_sources.append(entry)
        except:
            pass

    for obj in doc.Objects:
        if isinstance(obj, IGH_Param):
            add_geometry_param_info(obj)

    # ---------- component capabilities (definitions) ----------
    def get_component_description(comp):
        try:
            desc = getattr(comp, "Description", "")
            if not desc:
                desc = getattr(comp, "ToolTip", "")
            return desc.strip() if desc else ""
        except:
            return ""

    # ---------- type compatibility helpers ----------
    def _norm(t):
        return (t or "").strip().lower()

    def _is_generic_data(t):
        t = _norm(t)
        return (t == "") or ("generic" in t) or ("gh_objectwrapper" in t)

    def _is_geometry_supertype(t):
        t = _norm(t)
        # Anything that says "geometry" (e.g. "Geometry", "GeometryBase") is a supertype
        return "geometry" in t and t != "quad meshing settings" and t != "quad remeshing settings"

    def _is_numeric(t):
        t = _norm(t)
        return any(k in t for k in ("number", "integer", "double", "float"))

    def _is_brep_like(t):
        t = _norm(t)
        return ("brep" in t) or ("polysurface" in t)

    def _is_surface_like(t):
        t = _norm(t)
        return ("surface" in t) and ("mesh" not in t)

    def _is_curve_like(t):
        return "curve" in _norm(t)

    def _is_mesh_like(t):
        return "mesh" in _norm(t)

    def types_compatible(src_t, dst_t):
        """Coarse but useful compatibility check to annotate obvious mismatches."""
        s, d = _norm(src_t), _norm(dst_t)
        if s == d:
            return True
        if _is_generic_data(s) or _is_generic_data(d):
            return True
        if _is_geometry_supertype(d):
            return True
        if _is_numeric(s) and _is_numeric(d):
            return True
        if _is_surface_like(s) and _is_brep_like(d):
            return True
        if _is_mesh_like(s) and (_is_curve_like(d) or _is_surface_like(d) or _is_brep_like(d)):
            return False
        if _is_curve_like(s) and (_is_mesh_like(d) or _is_surface_like(d) or _is_brep_like(d)):
            return False
        return False

    # ---------- render ----------
    out = []

    # Header
    out += ["="*78, "GRASSHOPPER RECIPE — EXECUTION REPORT", "="*78]
    out.append("Doc: {0} | Units: {1} | AbsTol: {2:g} | AngTol: {3:g}°".format(
        rhdoc.Name if rhdoc else "Untitled", unit_name, abs_tol, ang_tol))
    out.append("")

    # Summary / issues
    dangling_in = sum(1 for n in nodes if isinstance(n, IGH_Component)
                      for p in n.Params.Input if p.SourceCount == 0)
    dangling_out = sum(1 for n in nodes if isinstance(n, IGH_Component)
                       for p in n.Params.Output if p.Recipients.Count == 0)
    out.append("Nodes: {0}  |  Connections: {1}  |  Unconnected inputs: {2}  |  Unconnected outputs: {3}".format(
        len(nodes), len(edges), dangling_in, dangling_out))

    # Count missing required
    total_missing = 0
    for n in nodes:
        if isinstance(n, IGH_Component):
            for p in n.Params.Input:
                if missing_required(p):
                    total_missing += 1

    out.append("")
    out.append("ISSUES")
    issues_errors_index = len(out)
    out.append("- Warnings: {0}   Errors: {1}".format(len(gh_warnings) + len(structural_warnings), len(gh_errors)))
    out.append("")
    out.append("LEGEND")
    out.append("[DEF] persistent default value   [SET] explicit setting   [MISSING] required & unset")
    out.append("[H] hidden preview   [D] disabled   [L] locked")
    out.append("[Geometry Sources] [R] referenced • [I] internalized • [?] unknown")
    out.append("")

    # Component overview (compact map)
    out += ["-"*78, "COMPONENT OVERVIEW (State • Category > Subcategory • Canvas @x,y)", "-"*78]
    node_iter = (nodes if not COMPACT else
                 [x for x in nodes if inputs_map[node_key(x)] or outputs_map[node_key(x)]])
    for n in node_iter:
        flags = node_flags(n)
        pos = node_pos.get(node_key(n), ("?", "?"))
        if isinstance(n, IGH_Component):
            cat = getattr(n, "Category", "")
            sub = getattr(n, "SubCategory", "")
            out.append("• {0:<25} {1:<5} • {2} > {3} • @{4},{5}".format(
                node_label(n), flags, cat, sub, pos[0], pos[1]))
        else:
            out.append("• {0:<25} {1:<5} • {2} • @{3},{4}".format(
                node_label(n), flags, "Param", pos[0], pos[1]))
    out.append("")

    # Component settings: unconnected inputs with persistent values + [MISSING]
    out += ["-"*78, "COMPONENT SETTINGS (Unconnected inputs with persistent values)", "-"*78]
    for n in node_iter:
        if not isinstance(n, IGH_Component):
            continue
        lines = []
        for p in n.Params.Input:
            pname = port_name(p)
            if p.SourceCount > 0:
                continue
            if missing_required(p):
                lines.append("  • {0}: [MISSING]".format(pname))
                continue
            if has_persistent(p):
                val, _label = first_persistent(p)
                if val is None:
                    continue
                if isinstance(val, float):
                    val_str = f"{val:.6g}"
                else:
                    val_str = str(val)
                lines.append("  • {0}: {1} [DEF]".format(pname, val_str))
        if lines:
            out.append(node_label(n))
            out.extend(lines)
            out.append("")
    if out[-1] != "":
        out.append("")

    # Expanded geometry sources (sorted)
    out += ["-"*78, "GEOMETRY SOURCES", "-"*78]
    if geometry_sources:
        for g in sorted(geometry_sources, key=lambda x: (x['label'], x['type'])):
            src = ('[R]' if g["referenced"] else ('[I]' if g["internalized"] else '[?]'))
            base = "{0}  {1} {2}".format(g["label"], src, g["type"])
            out.append(base)
            out.append("  • Count: {0}".format(g["count"]))
            if g["ref_ids"]:
                preview = g["ref_ids"][:MAX_SAMPLE_LIST]
                more = "" if len(g["ref_ids"]) <= MAX_SAMPLE_LIST else " …(+{0})".format(len(g["ref_ids"]) - MAX_SAMPLE_LIST)
                out.append("  • Rhino IDs: {0}{1}".format(", ".join(preview), more))
            if g["stats"]:
                uniq = []
                for s in g["stats"]:
                    if s not in uniq:
                        uniq.append(s)
                out.append("  • Stats: {0}".format(", ".join(uniq[:MAX_SAMPLE_LIST])))
            out.append("")
    else:
        out.append("(none)")
        out.append("")

    # NODES — DEFINITIONS & I/O
    out += ["-"*78, "NODES — DEFINITIONS & I/O", "-"*78]
    for n in node_iter:
        label = node_label(n)
        if isinstance(n, IGH_Component):
            cat = getattr(n, "Category", "")
            sub = getattr(n, "SubCategory", "")
            defn = get_component_description(n)
            out.append("{0}  —  {1} > {2}  —  \"{3}\"".format(label, cat, sub, n.Name))
            if defn:
                out.append("Definition: {0}".format(defn))
        else:
            out.append("{0}  —  Param  —  \"{1}\"".format(label, n.Name))
        # Inputs
        out.append("Inputs:")
        if isinstance(n, IGH_Component):
            if not n.Params.Input or len(n.Params.Input)==0:
                out.append("  (none)")
            for p in n.Params.Input:
                pname = port_name(p)
                ptype = port_type(p) or ""
                opt = getattr(p, "Optional", False)
                rhs = []
                if p.SourceCount > 0:
                    conns = ["{0}.{1}".format(slab, sport) for slab, sport in inputs_map[node_key(n)].get(port_tag(p,'in'), [])]
                    rhs.append("<=  " + ", ".join(conns))
                else:
                    if missing_required(p):
                        rhs.append("[MISSING]")
                    elif has_persistent(p):
                        val, _ = first_persistent(p)
                        if val is not None:
                            rhs.append("=  {0} [DEF]".format(f"{val:.6g}" if isinstance(val, float) else str(val)))
                    else:
                        rhs.append("(unconnected)")
                opt_tag = " [optional]" if opt else ""
                out.append("  • {0} ({1}){2}  {3}".format(pname, ptype, opt_tag, "  ".join(rhs)))
        else:
            # floating param acts as its own input when sourced
            p = n
            pname = port_name(p)
            ptype = port_type(p) or type(p).__name__
            if p.SourceCount > 0:
                rhs = ["<=  " + ", ".join("{0}.{1}".format(*resolve_node_from_param(sp))[0:0] for sp in p.Sources)]
            else:
                if has_persistent(p):
                    val,_= first_persistent(p)
                    rhs = ["=  {0} [DEF]".format(val)]
                else:
                    rhs = ["(unconnected)"]
            out.append("  • {0} ({1})  {2}".format(pname, ptype, "  ".join(rhs)))
        # Outputs
        out.append("Outputs:")
        if isinstance(n, IGH_Component):
            if not n.Params.Output or len(n.Params.Output)==0:
                out.append("  (none)")
            for p in n.Params.Output:
                pname = port_name(p)
                ptype = port_type(p) or ""
                recips = getattr(p.Recipients, 'Count', 0)
                if recips and recips>0:
                    outs = ["{0}.{1}".format(tlab, tport) for tlab, tport in outputs_map[node_key(n)].get(port_tag(p,'out'), [])]
                    rhs = "=>  " + ", ".join(outs)
                else:
                    rhs = "(no recipients)"
                out.append("  • {0} ({1})  {2}".format(pname, ptype, rhs))
        else:
            # floating param output
            p = n
            pname = port_name(p)
            ptype = port_type(p) or type(p).__name__
            recips = getattr(p.Recipients, 'Count', 0)
            rhs = "(no recipients)" if not recips else "=>  (wired)"
            out.append("  • {0} ({1})  {2}".format(pname, ptype, rhs))
        out.append("")

    # Build CONNECTIONS and detect mismatches (capture input TYPE labels)
    def parse_index(tag):
        if "[" in tag and tag.endswith("]"):
            try:
                return int(tag.split("[")[-1].rstrip("]"))
            except:
                return 10**6
        return 10**6

    out += ["-"*78, "CONNECTIONS (expanded)", "-"*78]
    # Real connections first
    edges.sort(key=lambda e: (e[1], parse_index(e[2]), e[4], parse_index(e[5]), e[2], e[5]))

    mismatch_summary = []
    connection_lines = []
    for s_key, s_label, s_port, t_key, t_label, t_port in edges:
        sparam = output_param_ref.get((s_key, s_port))
        tparam = input_param_ref.get((t_key, t_port))
        s_t = port_type(sparam) if sparam else ""
        t_t = port_type(tparam) if tparam else ""
        line = "{0}.{1}  →  {2}.{3}".format(s_label, s_port, t_label, t_port)
        if not types_compatible(s_t, t_t):
            dtype = t_t or ""
            line += "  [TYPE MISMATCH: {0} → {1}]".format(s_t or "?", t_t or "?")
            mismatch_summary.append("{0}.{1} -> {2}.{3} [{4} → {5}]".format(s_label, s_port, t_label, t_port, s_t or "?", t_t or "?"))
        connection_lines.append(line)

    # Now add any component inputs with NO wires and NO persistent defaults (explicitly shown)
    for n in node_iter:
        if isinstance(n, IGH_Component):
            for p in n.Params.Input:
                if p.SourceCount == 0 and not has_persistent(p):
                    pname = port_name(p)
                    ptype = port_type(p) or ""
                    req = not getattr(p, 'Optional', False)
                    tag = port_tag(p, 'in')
                    mark = "[MISSING]" if req else "(unconnected)"
                    connection_lines.append("{0}.{1}  —  {2} ({3}) {4}".format(node_label(n), tag, pname, ptype, mark))
        else:
            # floating param with no source and no persistent value
            p = n
            if p.SourceCount == 0 and not has_persistent(p):
                pname = port_name(p)
                ptype = port_type(p) or type(p).__name__
                tag = port_tag(p, 'in')
                connection_lines.append("{0}.{1}  —  {2} ({3}) (unconnected)".format(node_label(n), tag, pname, ptype))

    # And any outputs with no recipients
    for n in node_iter:
        if isinstance(n, IGH_Component):
            for p in n.Params.Output:
                recips = getattr(p.Recipients, 'Count', 0)
                if not recips:
                    pname = port_name(p)
                    ptype = port_type(p) or ""
                    tag = port_tag(p, 'out')
                    connection_lines.append("{0}.{1}  —  {2} ({3}) (no recipients)".format(node_label(n), tag, pname, ptype))
        else:
            p = n
            recips = getattr(p.Recipients, 'Count', 0)
            if not recips:
                pname = port_name(p)
                ptype = port_type(p) or type(p).__name__
                tag = port_tag(p, 'out')
                connection_lines.append("{0}.{1}  —  {2} ({3}) (no recipients)".format(node_label(n), tag, pname, ptype))

    out += connection_lines

    # Append offenders to ISSUES errors line (by component label)
    try:
        offender_keys = set()
        for line in mismatch_summary:
            # parse target label before ' [' part; cheap but effective for single-run diagnostics
            offender_keys.add(line.split(" -> ")[1].split(" ")[0].split(".")[0])
        offenders = sorted(offender_keys)
        if offenders:
            out[issues_errors_index] = out[issues_errors_index] + " (" + ", ".join(offenders) + ")"
    except:
        pass

    # Errors / Warnings sections with mismatch recap
    if gh_errors or mismatch_summary or structural_warnings or gh_warnings:
        out += ["", "-"*78, "ERRORS", "-"*78]
        if mismatch_summary:
            out.append("TYPE MISMATCH CONNECTIONS")
            out.extend(mismatch_summary)
            out.append("")
        for _nk, nlabel, msg in gh_errors:
            out.append(f"[ERROR] {nlabel}: {msg}")
        if gh_warnings or structural_warnings:
            out += ["", "-"*78, "WARNINGS", "-"*78]
            for _nk, nlabel, msg in gh_warnings:
                out.append(f"[WARNING] {nlabel}: {msg}")
            out += structural_warnings
            out.append("")

    a = "\n".join(out)
    print(a)
# EOF
