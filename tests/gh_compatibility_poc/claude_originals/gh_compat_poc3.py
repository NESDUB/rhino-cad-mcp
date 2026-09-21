import contextlib, io, json, time, traceback
from pathlib import Path
import Rhino, scriptcontext as sc

_RESULT_PATH = Path("/tmp/gh_compat_poc3_result.json")
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

        # ============================================================
        # Part 1: Inspect IGH_QuickCast — the type conversion interface
        # ============================================================
        igh_qc = None
        gh_qc_type_enum = None
        gh_convert = None

        for asm in System.AppDomain.CurrentDomain.GetAssemblies():
            if "Grasshopper" in str(asm.GetName().Name):
                try:
                    for t in asm.GetTypes():
                        if t.FullName == "Grasshopper.Kernel.Types.IGH_QuickCast":
                            igh_qc = t
                        elif t.FullName == "Grasshopper.Kernel.Types.GH_QuickCastType":
                            gh_qc_type_enum = t
                        elif t.FullName == "Grasshopper.Kernel.GH_Convert":
                            gh_convert = t
                except:
                    pass

        # Get QuickCast enum values
        qc_enum_values = []
        if gh_qc_type_enum and gh_qc_type_enum.IsEnum:
            for name in System.Enum.GetNames(gh_qc_type_enum):
                val = System.Enum.Parse(gh_qc_type_enum, name)
                qc_enum_values.append({"name": name, "value": int(val)})

        # Get IGH_QuickCast methods
        qc_methods = []
        if igh_qc:
            for m in igh_qc.GetMethods():
                params = ", ".join(
                    f"{p.ParameterType.Name} {p.Name}" for p in m.GetParameters()
                )
                qc_methods.append(f"{m.ReturnType.Name} {m.Name}({params})")

        # Get GH_Convert static methods
        convert_methods = []
        if gh_convert:
            for m in gh_convert.GetMethods(SR.BindingFlags.Public | SR.BindingFlags.Static):
                params = ", ".join(
                    f"{p.ParameterType.Name} {p.Name}" for p in m.GetParameters()
                )
                convert_methods.append(f"{m.ReturnType.Name} {m.Name}({params})")

        # ============================================================
        # Part 2: Check CastTo/CastFrom on GH_Goo types
        # ============================================================
        # The actual type compatibility lives on IGH_Goo.CastTo<T>() and CastFrom()

        # Get GH_Circle and check what it can cast to
        gh_circle_type = None
        gh_curve_type = None
        gh_brep_type = None
        gh_number_type = None
        gh_goo_type = None

        for asm in System.AppDomain.CurrentDomain.GetAssemblies():
            if "Grasshopper" in str(asm.GetName().Name):
                try:
                    for t in asm.GetTypes():
                        if t.FullName == "Grasshopper.Kernel.Types.GH_Circle":
                            gh_circle_type = t
                        elif t.FullName == "Grasshopper.Kernel.Types.GH_Curve":
                            gh_curve_type = t
                        elif t.FullName == "Grasshopper.Kernel.Types.GH_Brep":
                            gh_brep_type = t
                        elif t.FullName == "Grasshopper.Kernel.Types.GH_Number":
                            gh_number_type = t
                        elif t.FullName == "Grasshopper.Kernel.Types.GH_Goo`1":
                            gh_goo_type = t
                except:
                    pass

        def get_cast_methods(goo_type):
            if not goo_type:
                return []
            methods = []
            for m in goo_type.GetMethods(
                SR.BindingFlags.Public | SR.BindingFlags.Instance
            ):
                if "Cast" in m.Name or "ScriptVariable" in m.Name:
                    params = ", ".join(
                        f"{p.ParameterType.Name} {p.Name}"
                        for p in m.GetParameters()
                    )
                    methods.append(f"{m.ReturnType.Name} {m.Name}({params})")
            return methods

        # ============================================================
        # Part 3: ACTUAL CASTING TEST
        # Create a GH_Circle, try to CastTo GH_Curve (should work)
        # Create a GH_Number, try to CastTo GH_Brep (should fail)
        # ============================================================

        casting_tests = {}

        # Test 1: Circle -> Curve (should succeed)
        try:
            circle_goo = GH.Kernel.Types.GH_Circle(
                Rhino.Geometry.Circle(Rhino.Geometry.Plane.WorldXY, 5.0)
            )

            # Check if it implements IGH_QuickCast
            implements_qc = igh_qc.IsInstanceOfType(circle_goo) if igh_qc else None

            # Try QC_Type property
            qc_type_val = None
            if implements_qc:
                try:
                    qc_type_val = str(circle_goo.QC_Type)
                except:
                    pass

            # CastTo<GH_Curve>
            curve_target = GH.Kernel.Types.GH_Curve()
            cast_ok = circle_goo.CastTo[GH.Kernel.Types.GH_Curve](curve_target)

            casting_tests["circle_to_curve"] = {
                "success": cast_ok,
                "implements_quickcast": implements_qc,
                "qc_type": qc_type_val,
                "result_type": str(type(curve_target)) if cast_ok else None,
            }
        except Exception as e:
            casting_tests["circle_to_curve"] = {"error": str(e)}

        # Test 2: Circle -> Brep (might fail or succeed via surface)
        try:
            circle_goo2 = GH.Kernel.Types.GH_Circle(
                Rhino.Geometry.Circle(Rhino.Geometry.Plane.WorldXY, 5.0)
            )
            brep_target = GH.Kernel.Types.GH_Brep()
            cast_ok = circle_goo2.CastTo[GH.Kernel.Types.GH_Brep](brep_target)
            casting_tests["circle_to_brep"] = {"success": cast_ok}
        except Exception as e:
            casting_tests["circle_to_brep"] = {"error": str(e)}

        # Test 3: Number -> Curve (should fail)
        try:
            num_goo = GH.Kernel.Types.GH_Number(42.0)
            curve_target2 = GH.Kernel.Types.GH_Curve()
            cast_ok = num_goo.CastTo[GH.Kernel.Types.GH_Curve](curve_target2)
            casting_tests["number_to_curve"] = {"success": cast_ok}
        except Exception as e:
            casting_tests["number_to_curve"] = {"error": str(e)}

        # Test 4: Number -> Brep (should fail)
        try:
            num_goo2 = GH.Kernel.Types.GH_Number(42.0)
            brep_target2 = GH.Kernel.Types.GH_Brep()
            cast_ok = num_goo2.CastTo[GH.Kernel.Types.GH_Brep](brep_target2)
            casting_tests["number_to_brep"] = {"success": cast_ok}
        except Exception as e:
            casting_tests["number_to_brep"] = {"error": str(e)}

        # Test 5: Number -> Integer (should succeed)
        try:
            num_goo3 = GH.Kernel.Types.GH_Number(42.0)
            int_target = GH.Kernel.Types.GH_Integer()
            cast_ok = num_goo3.CastTo[GH.Kernel.Types.GH_Integer](int_target)
            casting_tests["number_to_integer"] = {"success": cast_ok}
        except Exception as e:
            casting_tests["number_to_integer"] = {"error": str(e)}

        # Test 6: Curve -> Circle (reverse — should fail unless it IS a circle)
        try:
            line = Rhino.Geometry.LineCurve(
                Rhino.Geometry.Point3d(0, 0, 0),
                Rhino.Geometry.Point3d(10, 0, 0)
            )
            curve_goo = GH.Kernel.Types.GH_Curve(line)
            circle_target = GH.Kernel.Types.GH_Circle()
            cast_ok = curve_goo.CastTo[GH.Kernel.Types.GH_Circle](circle_target)
            casting_tests["line_to_circle"] = {"success": cast_ok}
        except Exception as e:
            casting_tests["line_to_circle"] = {"error": str(e)}

        # Test 7: Boolean -> Number (should succeed)
        try:
            bool_goo = GH.Kernel.Types.GH_Boolean(True)
            num_target = GH.Kernel.Types.GH_Number()
            cast_ok = bool_goo.CastTo[GH.Kernel.Types.GH_Number](num_target)
            casting_tests["boolean_to_number"] = {
                "success": cast_ok,
                "value": num_target.Value if cast_ok else None,
            }
        except Exception as e:
            casting_tests["boolean_to_number"] = {"error": str(e)}

        # Test 8: Point -> Curve (should fail)
        try:
            pt_goo = GH.Kernel.Types.GH_Point(Rhino.Geometry.Point3d(1, 2, 3))
            curve_target3 = GH.Kernel.Types.GH_Curve()
            cast_ok = pt_goo.CastTo[GH.Kernel.Types.GH_Curve](curve_target3)
            casting_tests["point_to_curve"] = {"success": cast_ok}
        except Exception as e:
            casting_tests["point_to_curve"] = {"error": str(e)}

        result = {
            "quickcast_enum": qc_enum_values,
            "quickcast_interface_methods": qc_methods,
            "gh_convert_methods": convert_methods,
            "gh_circle_cast_methods": get_cast_methods(gh_circle_type),
            "gh_curve_cast_methods": get_cast_methods(gh_curve_type),
            "casting_tests": casting_tests,
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
