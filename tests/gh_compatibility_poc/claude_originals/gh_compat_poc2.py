import contextlib, io, json, time, traceback
from pathlib import Path
import Rhino, scriptcontext as sc

_RESULT_PATH = Path("/tmp/gh_compat_poc2_result.json")
_started = time.time()
_buf = io.StringIO()
result = None

try:
    if Rhino.RhinoDoc.ActiveDoc is not None:
        sc.doc = Rhino.RhinoDoc.ActiveDoc
    with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
        import Grasshopper as GH
        import System
        import System.Reflection as SR

        server = GH.Instances.ComponentServer

        def find_component(name):
            for proxy in server.ObjectProxies:
                if proxy.Desc and proxy.Desc.Name == name:
                    return proxy
            return None

        # Instantiate components
        circle = find_component("Circle").CreateInstance()
        loft = find_component("Loft").CreateInstance()
        addition = find_component("Addition").CreateInstance()
        brep_edges = find_component("Brep Edges").CreateInstance()

        # Get concrete param types via reflection
        def get_param_details(obj, side):
            params = obj.Params.Input if side == "input" else obj.Params.Output
            details = []
            for p in params:
                # Get the actual .NET type
                real_type = p.GetType()

                # Get all methods on the concrete type
                all_methods = real_type.GetMethods(
                    SR.BindingFlags.Public | SR.BindingFlags.Instance
                )

                # Filter for casting/conversion/compatibility
                interesting = []
                for m in all_methods:
                    name_lower = m.Name.lower()
                    if any(kw in name_lower for kw in [
                        "cast", "convert", "compat", "accept",
                        "canreceive", "match", "coerce"
                    ]):
                        params_str = ", ".join(
                            f"{pp.ParameterType.Name} {pp.Name}"
                            for pp in m.GetParameters()
                        )
                        interesting.append(
                            f"{m.ReturnType.Name} {m.Name}({params_str})"
                        )

                # Also check properties
                all_props = real_type.GetProperties(
                    SR.BindingFlags.Public | SR.BindingFlags.Instance
                )
                interesting_props = []
                for prop in all_props:
                    name_lower = prop.Name.lower()
                    if any(kw in name_lower for kw in [
                        "type", "cast", "convert", "compat"
                    ]):
                        interesting_props.append(
                            f"{prop.PropertyType.Name} {prop.Name}"
                        )

                details.append({
                    "name": p.Name,
                    "type_name": p.TypeName,
                    "concrete_type": real_type.FullName,
                    "base_type": real_type.BaseType.FullName if real_type.BaseType else None,
                    "casting_methods": interesting,
                    "type_properties": interesting_props,
                })
            return details

        # Also check what IGH_Param interface defines
        igh_param_type = System.Type.GetType(
            "Grasshopper.Kernel.IGH_Param, Grasshopper"
        )
        igh_methods = []
        if igh_param_type:
            for m in igh_param_type.GetMethods():
                igh_methods.append(m.Name)

        # Check GH_ParamAccess and related enums
        # Check if there's a GH_Conversion or similar type
        conversion_types = []
        for asm in System.AppDomain.CurrentDomain.GetAssemblies():
            if "Grasshopper" in str(asm.GetName().Name):
                try:
                    for t in asm.GetTypes():
                        name = t.Name.lower()
                        if any(kw in name for kw in [
                            "convert", "cast", "compat", "coerce"
                        ]):
                            conversion_types.append(t.FullName)
                except:
                    pass

        result = {
            "circle_outputs": get_param_details(circle, "output"),
            "loft_inputs": get_param_details(loft, "input"),
            "addition_outputs": get_param_details(addition, "output"),
            "brep_edges_inputs": get_param_details(brep_edges, "input"),
            "igh_param_methods": sorted(set(igh_methods)),
            "conversion_types_in_gh": conversion_types,
        }

    _payload = {"ok": True, "result": result}
except Exception as exc:
    _payload = {"ok": False, "kind": "python_exception", "error": str(exc), "traceback": traceback.format_exc()}
finally:
    _payload["console"] = _buf.getvalue()
    _payload["elapsed_ms"] = round((time.time() - _started) * 1000, 1)
    _tmp = Path(str(_RESULT_PATH) + ".tmp")
    _tmp.write_text(json.dumps(_payload, default=str))
    _tmp.replace(_RESULT_PATH)
