import contextlib, io, json, time, traceback
from pathlib import Path
import Rhino, scriptcontext as sc

_RESULT_PATH = Path("/tmp/gh_compat_poc_result.json")
_started = time.time()
_buf = io.StringIO()
result = None

try:
    if Rhino.RhinoDoc.ActiveDoc is not None:
        sc.doc = Rhino.RhinoDoc.ActiveDoc
    with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
        import Grasshopper as GH
        import System

        server = GH.Instances.ComponentServer

        # 1. Find specific components by name
        def find_component(name):
            """Find a component proxy by name."""
            for proxy in server.ObjectProxies:
                if proxy.Desc and proxy.Desc.Name == name:
                    return proxy
            return None

        # 2. Get two known-compatible components
        # Circle (outputs Circle/Curve) -> Loft (takes Curves)
        # And two incompatible: Addition (outputs Number) -> Brep Edges (takes Brep)

        circle_proxy = find_component("Circle")
        loft_proxy = find_component("Loft")
        addition_proxy = find_component("Addition")
        brep_edges_proxy = find_component("Brep Edges")

        found = {
            "Circle": circle_proxy is not None,
            "Loft": loft_proxy is not None,
            "Addition": addition_proxy is not None,
            "Brep Edges": brep_edges_proxy is not None,
        }

        # 3. Instantiate them and inspect their parameters
        def inspect_component(proxy, name):
            if proxy is None:
                return {"error": f"{name} not found"}

            obj = proxy.CreateInstance()
            info = {
                "name": name,
                "type": str(type(obj)),
                "guid": str(proxy.Guid),
            }

            # Get inputs
            inputs = []
            if hasattr(obj, "Params") and hasattr(obj.Params, "Input"):
                for p in obj.Params.Input:
                    param_info = {
                        "name": p.Name,
                        "type": str(type(p)),
                        "type_name": p.TypeName if hasattr(p, "TypeName") else None,
                    }

                    # Look for compatibility/casting methods
                    param_methods = [m for m in dir(p) if
                        "cast" in m.lower() or
                        "compat" in m.lower() or
                        "convert" in m.lower() or
                        "accept" in m.lower() or
                        "valid" in m.lower() or
                        "type" in m.lower()
                    ]
                    param_info["relevant_methods"] = param_methods
                    inputs.append(param_info)
            info["inputs"] = inputs

            # Get outputs
            outputs = []
            if hasattr(obj, "Params") and hasattr(obj.Params, "Output"):
                for p in obj.Params.Output:
                    param_info = {
                        "name": p.Name,
                        "type": str(type(p)),
                        "type_name": p.TypeName if hasattr(p, "TypeName") else None,
                    }
                    param_methods = [m for m in dir(p) if
                        "cast" in m.lower() or
                        "compat" in m.lower() or
                        "convert" in m.lower() or
                        "accept" in m.lower() or
                        "valid" in m.lower() or
                        "type" in m.lower()
                    ]
                    param_info["relevant_methods"] = param_methods
                    outputs.append(param_info)
            info["outputs"] = outputs

            return info

        components = {}
        for name, proxy in [("Circle", circle_proxy), ("Loft", loft_proxy),
                            ("Addition", addition_proxy), ("Brep Edges", brep_edges_proxy)]:
            components[name] = inspect_component(proxy, name)

        result = {
            "found": found,
            "components": components,
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
