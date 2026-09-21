# Grasshopper compatibility: live-runtime proof of concept

## Result

**The diagnostic indicators exist, but compatibility is not a single static Boolean.** A wire may be accepted while its payload cannot convert. Conversion can succeed while the receiving operation fails. A component with no messages may not have solved at all.

Tested on the Rhino/Grasshopper versions recorded in each `run_*.json`. Final evidence: `run_1790028542124498000.json`; **64 regression checks passed**. Five component fixtures and four parameter fixtures were each repeated in fresh isolated documents. Twelve direct Goo conversion fixtures and three native CastTo controls were also tested. The existing GH canvas document, active Rhino document, and Rhino object IDs were unchanged.

## Reproduced component results

| Fixture | Wire | Input conversion | Receiver result |
|---|---|---|---|
| Circle producing two circles → Loft.Curves | Accepted | Two valid curves | No warning/error; one valid Brep |
| Circle producing one circle → Loft.Curves | Accepted | One valid curve | Error: `Loft could not be constructed.` |
| Loft with no curves | No source | No input | Warning: `Input parameter C failed to collect data` |
| Addition.Result → Brep Edges.Brep | Accepted | Failed | Error: `Data conversion failed from Complex to Brep` |
| Circle.Circle → Brep Edges.Brep | Accepted | Valid Brep | No warning/error; one valid circular edge |

Addition's output in this installed component is declared **Complex**, not Number. Component GUIDs are recorded rather than relying on ambiguous display names.

**Orange is not a universal “supply more inputs” signal. Red is not a universal “these types are incompatible” signal.** Read actual diagnostics on both the receiver component and its input parameters.

## Runtime indicators to inspect

- `input.AddSource(output)`, followed by `SourceCount`: confirms wiring only.
- `RuntimeMessageLevel`: `Blank`, `Remark`, `Warning`, or `Error`.
- `RuntimeMessages(GH_RuntimeMessageLevel.Warning)` and `.Error`: diagnostic strings; inspect components **and** parameters.
- `VolatileData`, actual non-null items, and `IGH_Goo.IsValid`: evidence of usable values.
- `VolatileDataCount`: raw slots, not necessarily usable geometry. A failed Loft had one slot but no non-null geometry.
- `GH_Document.Enabled`, global `GH_Document.EnableSolutions`, and `SolutionState`: establish that a solve actually happened.

Do not classify arbitrary plugin failures solely by parsing these English messages; messages may vary by plugin/version/language. Preserve the original messages and distinguish conversion evidence from operation evidence.

## Conversion discoveries

### Source CastTo is not the whole conversion pipeline

For the tested circle:

| Operation | Result |
|---|---|
| `GH_Circle.CastTo<GH_Curve>` | False |
| `GH_Circle.CastTo<Rhino.Geometry.Curve>` | False |
| `GH_Circle.CastTo<Rhino.Geometry.Circle>` | True |
| `GH_Curve.CastFrom(GH_Circle)` | True |
| `GH_Brep.CastFrom(GH_Circle)` | True |
| Actual Circle → Loft / Brep Edges wires | Both solve with appropriate inputs |

Therefore, source-side `CastTo` failure does not prove that a receiver rejects the value. `CastFrom` provides useful preliminary evidence; actual parameter collection and component solving are the stronger integration tests. `IGH_QuickCast` does not cover every geometry conversion.

### Compatibility can depend on the value

The same **Curve → Circle** parameter connection:

- Succeeds for a circular NURBS curve.
- Fails for a line curve.

A universal yes/no matrix based only on declared type names cannot faithfully represent this.

### Number → Integer is not truncation here

Observed direct casts: `42.1 → 42`, `42.5 → 43`, `42.9 → 43`, `43.5 → 44`, `-42.5 → -43`. Actual Number → Integer parameter wires reproduced the two half-value cases. This contradicts the earlier suggestion that this conversion truncates. These are measured samples on this runtime, not an exhaustive numeric-range specification.

## Failed hypotheses and harness corrections

1. **Claude's third probe**: every attempted generic `CastTo` invocation raised a Python/.NET overload error. That is an interop failure, not incompatible geometry. Originals and outputs are preserved under `claude_originals/`.
2. **Initial graph probe**: new `GH_Document()` instances had `Enabled=False`. `NewSolution(False)` returned without data or diagnostics. That initial run must not be interpreted as compatibility success. Preserved as `probe_unsolved_v1.py` and `run_1790028328829521000.json`.
3. **Solver fix**: explicitly enable only the disposable document. Do not modify the user's global solver setting. If global solutions are disabled, fail the harness clearly.
4. **Native Curve control assumption**: assuming Circle.CastTo(native Curve) would succeed was disproven. Failed regression retained in `run_1790028495601441000.json`. Added exact native Circle and Double positive controls; retained the broader Curve failure as a measured negative case.

## Reproducible method

1. Obtain a current Rhino document ID through the MCP; never reuse a stale PID/runtime serial.
2. Execute `probe.py` inside Rhino with `rhino_run`, using that explicit ID and a 120-second timeout. The script writes timestamped raw JSON and returns a regression summary.
3. The probe creates each GH document privately, enables it, instantiates exact component GUIDs, supplies deterministic persistent data, connects sources, solves, collects evidence, and disposes the document in `finally`.
4. For a host-side check of the saved final evidence:

```bash
cd ~/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc
python3 assert_report.py run_1790028542124498000.json
python3 -m unittest test_regression_guardrails.py
```

Rhino-executed code is Python 3.9 compatible. It launches no subprocesses, issues no interactive commands, and adds no test geometry to the user's Rhino document.

## Implications for the component atlas

Keep the JSON-authoritative / SQLite-compiled architecture, but compile **evidence-backed directional conversion records**, not a guessed inheritance hierarchy.

A minimal empirical record needs source/target component GUID and pin index (or parameter classes), declared types, representative payload, runtime/plugin versions, wire acceptance, conversion outcome, diagnostics, usable output counts, and the evidence path. Distinguish untested, observed success, observed rejection, conditional conversion, operation failure, missing data, and harness failure. Sample success must not be promoted to “all values accepted.”

The existing compact component/pin addresses can remain a convenience. If their IDs are assigned by enumeration, preserve a GUID-to-address registry before calling them stable across re-extractions. No extraction/address assignment implementation was audited in this POC.

## Limits

This is a tested POC, not a complete compatibility database. It does not cover every plugin, null/invalid payload, access mode, tree topology, tolerance, geometry degeneracy, or runtime version. No production MCP or atlas implementation was changed. A sensible next step is to capture these same evidence fields during a bounded native-parameter extraction/probe pass, retaining conditional and unknown results rather than forcing Boolean entries.

## Follow-up: how informative are operation errors?

### Evidence and scope

`operation_errors_probe.py` tests **20 scenarios twice in private GH documents (40 cases), plus two same-component repair sequences**. Final raw evidence: `operation_errors_1790029324894962000.json`. The 182 assertions in `operation_regression.json` passed. Six new host guardrail tests passed alongside the six original guardrails. Earlier bounded runs and the initial script are retained. No user canvas or Rhino geometry was modified.

Public diagnostic API inventory: `diagnostic_api_inventory.json`, generated by `discover_diagnostics.py`. Runtime and component assembly versions, GUIDs, concrete types, obsolete status and exposure are recorded in the final evidence.

### Answer: some messages are specific, some are vague, and some failures are silent

| Supplied condition | Severity/message | Additional measured evidence |
|---|---|---|
| One interpolation point | Error: `Insufficient interpolation points for a curve` | Null outputs; all input types accepted |
| Negative Divide Curve count | Warning: `The division count must be at least 0.` | Empty outputs |
| List Item index 99 into a one-item list, wrapping disabled | Warning: `Supplied index too high.` | Null output |
| Current generic Division, 1 / 0 | Error: `Division by zero` | Null output |
| One curve into Loft | Error: `Loft could not be constructed.` | One valid input curve, null Brep |
| Boundary Surfaces given an open line | Warning: `Planar surface routine returned no results` | Curve valid and planar, but open |
| Boundary Surfaces given a nonplanar closed polyline | Same warning | Curve valid and closed, but nonplanar at tolerance 0.01 |
| Boundary Surfaces given a coincident-endpoint line | Same warning | Invalid input; native validation log identifies coincident points |
| Circle radius 0 | **No message** | Invalid Goo; `IsValidWhyNot`: `Circle radius is too small.` |
| Line with coincident endpoints | **No message** | Invalid Goo; `IsValidWhyNot`: `Line is too short.` |
| Interpolate degree 0 | Warning: `Curve degree must be higher than zero` | Still returns a valid polyline curve |
| Circle radius -5 | No message | Returns valid radius +5 in this implementation |
| Divide Curve count 0 | No message | Empty output trees |
| Two disjoint circles into Curve–Curve intersection | No message | Empty results are appropriate for these inputs |

These are exact observations for the recorded components and runtime, not universal rules for all components. In particular, “empty output” needs an operation-specific expectation: no intersections can be correct, while no surface may violate the requested construction.

### Deeper diagnostics that should be retained

1. **`IGH_Goo.IsValidWhyNot`** provides value-level explanations that can be absent from all component and parameter message lists. It must be read alongside `IsValid`, not substituted for it.
2. **`GeometryBase.IsValidWithLog(out string)`**, where available, exposes native geometry validation detail. In the invalid Boundary Surfaces fixture, the component's generic warning was supplemented by `Curve: Line points are coincident.` at Goo level and `Line points are coincident.` at native level. Not every Goo contains a GeometryBase, and null results have no geometry to interrogate.
3. **Branch paths and per-item states** distinguish no item, null item, invalid value and valid value. Keep `{path, item index, type, validity, reason}` rather than only a total count.
4. **Component `RunCount`, object `Phase`, and `ProcessorTime`** provide execution context. RunCount measured solve iterations in these fixtures; it is not an error count. Phase `Computed` is not proof of valid output.
5. **Full upstream diagnostics and connectivity** are needed to locate the first failure, not merely the last empty output.
6. **Operation-specific measurements** such as closure, planarity with an explicit tolerance, length and radius help discriminate causes. A derived diagnosis must be labeled as inference, not represented as an SDK error message.
7. **Native numeric value and domain checks** matter even when Goo is valid; finite does not necessarily mean meaningful for the operation.

The inspected standard public `RuntimeMessages(level)` API returns a list of strings, not structured exceptions with universal error codes, stack traces or branch IDs. Reflection found no richer standard exception property on the inspected components. That does not establish that no plugin-specific diagnostic API exists. Component `Message` was null in these fixtures and provided no additional error detail; it is not a replacement for runtime diagnostics.

### Tree layout can cause the same vague operation error

The two same circles at Z=0 and Z=10:

- In a **single branch**, Loft produces one valid Brep.
- In **two one-item branches**, Loft runs twice and produces two null Breps with the single text `Loft could not be constructed.`

The types and total curve count are identical. The different branch layout changes the operation. This is evidence for a data-tree/list-cardinality check, **not** a reason to flatten every input automatically: flattening can destroy intended grouping.

### Partial success and diagnostic aggregation

A Loft fixture contained three branches: `{0}` had two circles; `{1}` and `{2}` each had one. It recorded:

- `RunCount = 3`.
- Component severity `Error`.
- One error string, despite two failing branches.
- One valid Brep on `{0}` and null results on `{1}` and `{2}`.

Thus a red component can retain useful results. The error list is not an occurrence counter, nor does this standard message identify a failing branch. Per-branch output evidence located the failures in this controlled fixture; branch mapping is not assumed to be one-to-one for arbitrary components.

### Upstream failures may not propagate as downstream errors

A failing one-curve Loft was connected to Brep Edges. Loft reported its error and produced a null Brep. Brep Edges collected one null slot, executed, produced empty outputs, and reported **no warning or error**. Looking only at the downstream component would conceal the cause.

### Same display name, different implementation and error behavior

Three installed components named Division behaved differently for numeric 1 / 0:

| Component GUID | Status/type | Observation |
|---|---|---|
| `9c85271f-89fa-4e9f-9f4a-d75802120ccc` | Current, generic operator | Explicit `Division by zero` error, null output |
| `ec875825-61e4-4c1c-a343-0e0cee0b321b` | Obsolete, hidden numeric component | No error; valid GH_Number equal to `Double.MaxValue` (finite) |
| `cb4ec4a1-f48e-4685-b58c-72ed27b53681` | Obsolete, hidden complex component | No error; invalid infinite complex output with a detailed validity reason |

The initial numeric test selected the legacy GUID. Its result was preserved and then compared against the other implementations rather than generalized to “Division.” **Add `Obsolete`, `Exposure`, concrete type, assembly version and exact GUID to extraction and diagnostic records.** Prefer current exposed components for new graph generation unless a legacy implementation is explicitly needed. Do not call every finite extreme value an error globally; use operation context.

### Repair and stale-message lifecycle

Two independent tests reused the same Loft component, changed one curve to two curves in the same branch, called `source.ExpireSolution(False)`, and solved again. The old error cleared, severity became Blank, and valid output appeared. Capture diagnostics with a solve/run identity; do not combine old errors with new outputs. `ClearRuntimeMessages()` alone would hide symptoms, not repair inputs, and was not used as a fix.

### Recommended diagnostic record additions

Retain the existing compatibility evidence and add:

- Solve identity; solver state; component GUID/type/assembly; obsolete/exposure; parameter index and instance ID.
- Component and parameter messages at each severity, plus phase, run count and timings.
- Input/output paths, access modes, item indices, null/invalid/valid counts, Goo validity reasons and native validation logs when available.
- Connected upstream IDs and their current diagnostics; preserve successful branches when others fail.
- Explicit operation expectations and measured preconditions; separate SDK observations from inferred diagnoses and candidate repairs.

Prefer multiple evidence fields over one verdict. For example, this POC observed conversion success + operation error + partial valid output simultaneously. For vague messages, investigate the specific failed branch and inputs with a disposable repair test; do not invent missing error detail.

### Re-run and regression

Run `operation_errors_probe.py` inside Rhino using the MCP with a fresh document ID. It produces a new timestamped JSON report; run the host assertions against that path. A changed Rhino/plugin version may legitimately change behavior, so preserve changed observations before revising expectations.

```bash
cd ~/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc
python3 assert_operation_report.py operation_errors_1790029324894962000.json
python3 -m unittest test_operation_guardrails.py test_regression_guardrails.py
```

Remaining scope: no exhaustive plugin scan, deliberate crashing component, arbitrary exception stack tracing, universal branch-to-error mapping, or proven automatic repair engine is claimed. This follow-up establishes a richer, reproducible observation layer without changing the production MCP.

## Probe 1: tracing values across collection and computation

### Reproduction and validation

Run `value_trace_probe.py` inside Rhino through the MCP with a fresh document ID. It reuses the serializer/helper definitions from `operation_errors_probe.py` without executing that script's test suite; retain both files together. Final evidence: `value_trace_1790030057004713000.json`. Earlier trace: `value_trace_1790030026227469000.json`.

Four fixtures × two modes (staged and normal) × two repetitions = **16 private-document runs**. The final report passed **108 assertions**, including measured geometry and equivalence of staged/normal final observations. Five negative-control/guardrail tests verify that missing conversion errors, wrong error timing, wrong geometry and staged/normal mismatches are detected.

```bash
cd ~/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc
python3 assert_value_trace.py value_trace_1790030057004713000.json
python3 -m unittest test_value_trace_guardrails.py
```

### Experimental method

Each fresh fixture is wired with deterministic persistent inputs. Staged mode snapshots these boundaries:

1. Wired, unsolved.
2. `source.CollectData()`.
3. `source.ComputeData()`.
4. `receiver.CollectData()`.
5. `receiver.ComputeData()`.

A separate fresh graph with identical inputs uses normal `document.NewSolution(False)`. Final observable states are compared after excluding instance IDs and processor timing. Types, values, measurements, messages, phases, run counts and tree structure remain in the comparison. This is observational equivalence for these fixtures, **not** proof of bitwise-identical geometry or universal scheduling equivalence. Direct staged calls do not constitute a normal document-level solution; stage receipts are labeled accordingly.

### Findings: where changes actually become visible

| Fixture | Source output after computation | Receiver input after collection | Receiver output after computation |
|---|---|---|---|
| Two circles → Loft | Two valid GH_Circle values, radius 5, Z=0 and Z=10 | Two valid GH_Curve values; no error | Valid Brep spanning Z=0…10; area approximately 100π |
| One circle → Loft | Valid GH_Circle | Valid GH_Curve; no error yet | Null Brep; `Loft could not be constructed.` appears now |
| Circle → Brep Edges | Valid GH_Circle, radius 5 | Valid GH_Brep: one planar face, area approximately 25π | Circular boundary curve with length approximately 10π |
| Addition → Brep Edges | Valid Complex value `{5, 0}` | Null slot and `Data conversion failed from Complex to Brep` already present | Empty curve outputs; conversion error remains |

- **The conversion outcome is observable during receiver collection**, before receiver computation. This distinguishes the incompatible Complex→Brep case from the compatible Circle→Curve case whose Loft operation subsequently fails.
- **Conversion may construct geometry.** Circle→Brep produces a planar face, not merely another wrapper around the same geometric category. Radius/area/bounds/circumference measurements verify its meaning in this fixture.
- **Source values are not consumed by collection.** Source outputs remained observably unchanged after receiver computation in all tested cases, including the failed conversion.
- **Wiring is not delivery.** Receiver input data remained empty after source computation until receiver collection occurred in the staged fixtures.
- **Source collection is not source computation.** Source inputs were collected while outputs remained empty; outputs appeared after computation.
- **Computed/RunCount is not successful execution.** Brep Edges reached phase Computed and RunCount 1 after a failed conversion but produced no usable geometry. A fresh component's RunCount was -1 in these fixtures, so do not assume an unsolved component always reports zero.

### Resolution and limitations

Snapshots retain component/pin instance IDs, exact GUIDs, source/target pin indices, branch paths, item order, actual Goo types, validity/reasons, diagnostics and geometric measurements. These controlled fixtures support value correspondence through known inputs, paths and measured geometry. No persistent per-item identity or universal lineage tracking is claimed: operations such as Loft deliberately combine several inputs into one output.

The probe observes before/after conversion boundaries. It **does not intercept Grasshopper's internal CastFrom/CastTo calls or prove their call order**, and does not see inside each native SolveInstance operation. It also does not demonstrate that manually stepping arbitrary plugins, asynchronous components or scheduled graphs is safe. Keep staged probes private and require a normal-solve control before trusting their conclusions.

For future validation, record conversion-stage evidence separately from operation-stage evidence. Do not label a null result simply “incompatible”: in this probe a null input marked conversion failure, whereas a valid collected curve followed by a null output marked operation failure. Always retain the diagnostics and graph context supporting that distinction.

## Probe 2: mixed valid, invalid, null and incompatible items

### Scope and reproducibility

`mixed_items_probe.py` reuses helper definitions from `operation_errors_probe.py`; retain both files. Execute inside Rhino with `rhino_run` and a fresh document ID. Evidence: `mixed_items_1790030245480306000.json`; **24 isolated runs, 351 passing fixture assertions**, plus five host guardrail tests. All cases repeated twice. No working document changes.

The graph is: persistent **Generic Data source → Curve parameter relay → Divide Curve or Loft**. Branch `{0}` contains the experimental list; branch `{7}` always has two valid circular curves as an independent control. Divide Curve has item access; Loft has list access. Cases: valid only; inserted null; inserted incompatible text; inserted invalid curve; all kinds mixed; reversed mixed order.

Valid circles have radius 5, at Z=0 and Z=10 in the experimental branch and Z=30 and Z=40 in the control. Invalid geometry is a coincident-endpoint line represented as GH_Curve. Incompatible text is `NOT_A_CURVE`. Literal null is `None`; the trace verifies that it survives persistent storage and source collection rather than assuming its presence.

```bash
cd ~/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc
python3 assert_mixed_items.py mixed_items_1790030245480306000.json
python3 -m unittest test_mixed_guardrails.py
```

### Conversion does not reject the whole branch

For `[valid circle, null, incompatible text, invalid curve, valid circle]`, the collected Curve relay contains `[valid curve, null, null, invalid curve, valid curve]` at the same five positions. The source retains its original text. Relay reports `Data conversion failed from Text to Curve`, but valid items and the control branch survive.

**Type acceptance and geometric validity remain separate.** The invalid GH_Curve passes through the Curve relay without a conversion error. Its `IsValid=False` and validity explanation must be inspected independently.

### Downstream handling is operation-specific

| Mixed item | Divide Curve (item input) | Loft (list input) |
|---|---|---|
| Null | Empty output branch for that index; other items work; no component warning | Warns `Null profile curve was removed`; valid surrounding circles still loft |
| Incompatible text converted to null at relay | Same local behavior as an original null; conversion error remains upstream | Same null-removal behavior; creates valid surface despite upstream relay error |
| Invalid coincident-endpoint curve | Returns three coincident origin points, each individually valid, without warnings | Warns `Invalid profile curve in loft, this may cause problems.` and errors `Loft only works if all curves are open, or all curves are closed.` for this particular mix |

The Loft error here is observed for invalid/open line plus valid closed circles; it does not establish that all invalid curves fail for that same reason. Null removal is supported by the explicit component warning and resulting valid surface; collected input still retains the null slot, so do not claim the parameter tree itself was edited.

### Position and branch evidence

- Divide Curve generated output paths `{0;i}` corresponding to input positions in these fixtures. Null slots produced empty branches rather than compacting subsequent results. Reversing the mixed list moved the empty/degenerate branches accordingly; the identifiable Z=0 and Z=10 circle results reversed positions.
- The invalid curve produced three identical, individually valid points. This is a concrete counterexample to “all outputs have IsValid=True, therefore the operation succeeded meaningfully.” Input validity, duplicates and operation intent matter.
- Divide Curve `RunCount` included null positions: seven iterations for five experimental slots plus two controls. Loft ran twice, once per branch.
- Loft with only null/incompatible additions returned valid surfaces on both branches. With the invalid line included, `{0}` returned null while `{7}` still returned a valid surface.
- Original null and failed conversion become indistinguishable at the relay's payload level. Preserve source snapshots and conversion diagnostics to distinguish their origins.
- In the reversed Loft fixture, the ordering of warning strings changed. Treat severity/message presence separately from incidental message ordering; do not assume message position identifies item position.

### Implications for validation

Preserve **source item state → converted item state → operation result** with paths and indices where observable. Do not compact nulls in diagnostic reports, globally discard all results from a component with an upstream error, or assume invalid geometry is automatically rejected. Store distinct states for explicit null, conversion-produced null (when proven by the trace), invalid typed geometry, empty output branch and individually valid but degenerate output.

These are measured semantics of the tested Generic→Curve relay, Divide Curve and Loft GUIDs, with default tree settings and deterministic small inputs. They are not universal guarantees for every parameter, operation or plugin. Multi-source merging, alternate null-removal policies, arbitrary tree transformations and other invalid-geometry families remain untested here.

## Probe 3: data matching, tree structure, multiple sources and access modes

### Evidence and reproduction

`tree_matching_probe.py` uses the helpers in `operation_errors_probe.py`. Final evidence: `tree_matching_1790030526715230000.json`; initial 40-case evidence: `tree_matching_1790030495923567000.json`. Final run: **23 fixtures repeated twice = 46 isolated solves; 305 regression checks passed**, plus six host guardrail tests. Working Rhino/canvas documents were preserved.

`discover_tree_api.py` and `tree_api_inventory.json` retain the runtime discovery. This probe deliberately uses the **current generic Addition**, GUID `a0d62394-a118-422d-abb3-6af115c75b25`, not the obsolete Complex Addition from the original POC. The discovery confirmed that the original Complex Addition GUID is obsolete; its earlier results remain valid for that exact legacy implementation, not a description of the current Addition component.

```bash
cd ~/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc
python3 assert_tree_matching.py tree_matching_1790030526715230000.json
python3 -m unittest test_tree_guardrails.py
```

Execute the probe itself via Rhino MCP with a current document ID to reproduce live results. The host commands above validate saved evidence. Script, helper, assertions, inventory and JSON belong together.

### Unequal item lists: longest-list behavior in the tested current Addition

- `[1,2,3] + [10,20]` → `[11,22,23]`: the final 20 is reused, not cycled back to 10 and not truncated away.
- Swapping inputs yields the same three sums in this commutative fixture.
- `[1,2,3] + [10]` → `[11,12,13]`.
- Collected parameter trees retain their original list lengths. The repeated pairing is reflected in operation results and RunCount, not an expanded collected input tree.

This is measured item-access matching for these fixtures, not a claim that every component uses identical matching or that all operations are commutative.

### Branch matching is not an exact-path dictionary join

Input A: `{0}:[1,2]`, `{7}:[3,4]`. Input B: `{2}:[10]`, `{9}:[100]`.

The current Addition pairs the branches to produce `{0}:[11,12]`, `{7}:[103,104]`, despite no shared path labels. Giving B a third branch `{12}:[1000]` produces a third result branch **`{8}:[1003,1004]`**. `{8}` exists in neither input. Reversing these inputs produces the same numeric groups under `{2}`, `{9}`, `{12}` instead.

These paired tests demonstrate that value pairing and output path selection are distinct, and input ordering can affect result paths. They do not establish a universal algorithm for arbitrary path depths or master-parameter selection. **Never infer output lineage solely by matching path labels.** Retain actual source trees, collected trees, pin order, output trees and component identity.

### Flattening and grafting change the computation, not merely display

Using A `[1,2,3]`, B `[10,20]`:

| Mapping | Collected structure / result |
|---|---|
| Neither grafted | One branch; three sums `[11,22,23]` |
| Graft A only | A becomes three singleton branches; six sums: `{0;0}:[11,21]`, `{0;1}:[12,22]`, `{0;2}:[13,23]` |
| Graft both | Singleton branches on both inputs; three sums `{0;0}:[11]`, `{0;1}:[22]`, `{0;2}:[23]` |

With A containing two two-item branches and B containing two scalar branches, flattening A alone produced eight sums: the entire flattened A list paired with each B branch. Source trees were not rewritten; mapping changes are visible in collected inputs.

Loft supplied two branches of two valid circles:

- Unmodified: two valid surfaces, two iterations.
- Flattened: one list of four circles, one valid surface, one iteration—**a changed grouping with no warning**.
- Grafted: four lists of one circle each, four null outputs and `Loft could not be constructed.`

Do not automatically flatten or graft to remove an error without verifying the intended grouping and resulting geometry.

### Multiple sources and connection order

Two sources sharing `{0}`, containing `[1,2]` and `[100,200]`, merge into `[1,2,100,200]` in connection order. Reversing connection order produces `[100,200,1,2]`. With a scalar second input of 10, output ordering changes accordingly.

Sources on different paths retain separate branches in the tested fixture. Applying `Reverse=True` to the receiving input after connecting both same-path sources yielded `[200,100,2,1]`, consistent with reversing the merged branch rather than independently reversing each source. Source IDs and order are recorded in `settings.source_ids`.

A separate multi-branch reverse control reversed items **within each branch**, not the branch order. `Simplify=True` removed the shared `{5;...}` prefix from input paths `{5;0}` and `{5;7}`, yielding collected `{0}` and `{7}`; original source paths remained unchanged. Only this simplifiable-prefix case was tested; do not extrapolate to every topology.

### Item, list and tree access are operationally different

- Current Addition uses item access; its RunCount follows the matched item iterations.
- Loft uses list access; its RunCount follows the lists supplied by tree matching in these fixtures.
- Tree Statistics uses tree access, consumes the whole two-branch tree in one run, reports the two paths, per-branch lengths `[2,2]`, and branch count 2.
- Flip Matrix also consumes a tree in one run. `{0}:[1,2]`, `{7}:[10,20]` becomes `{0}:[1,10]`, `{1}:[2,20]`: original branch labels are not preserved as output labels.
- A ragged matrix `{0}:[1,2]`, `{7}:[10]` becomes `{0}:[1,10]`, `{1}:[2,null]` **without a warning**. An output null can therefore be algorithmic padding, not supplied missing data, conversion failure or a failed geometry operation.

### Validation additions

Record declared access mode, input pin ordering, ordered source IDs, mapping/reverse/simplify flags, and source/collected/output trees. Validate expected grouping and cardinality in addition to types and geometry validity. Successful, warning-free output can represent unintended duplicated pairings, merged groups, new paths or padded values.

The output-null origin taxonomy now includes **algorithmic padding**, demonstrated by ragged Flip Matrix. Keep this distinct from Probe 2's explicit null and failed-conversion placeholder and the Loft operation-failure null. These origins require operation context and evidence, not classification from the null alone.

No universal Grasshopper data-matching engine was reconstructed here. Cross-reference matching modes, path-depth edge cases, empty-branch matching, mixed access across complex components, and arbitrary plugin implementations remain outside this bounded probe. The results are reproducible examples and regression expectations for the exact recorded runtime/components.
