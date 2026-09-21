# GUI Document Creation in Rhino via rhinocode

## The Problem

Creating a visible Rhino document window from rhinocode is not straightforward. The obvious RhinoCommon APIs for document creation produce in-memory objects that never get a GUI window or tab.

## Old Method (Broken)

```python
# RhinoDoc.Create() — creates an in-memory doc with NO visible window
d = Rhino.RhinoDoc.Create(None)
d.ModelUnitSystem = Rhino.UnitSystem.Millimeters

# RhinoDoc.Open() — returns a doc object but may not create a window
r = Rhino.RhinoDoc.Open(path)
d = r[0] if isinstance(r, tuple) else r

# Setting ActiveDoc does NOT make an invisible doc visible
Rhino.RhinoDoc.ActiveDoc = d
```

**What happens:** The document exists in Rhino's process and can be scripted against (add objects, capture viewports, save to file), but the user sees nothing in the Rhino GUI. `ActiveDoc` remains `None` from Rhino's perspective because there's no window backing the document.

This also applied to `RhinoDoc.Create(None)` for "non-headless" documents — despite not passing `CreateHeadless`, the result is functionally the same: no window.

## New Method (Working)

```python
# RhinoDoc.OpenFile(path) — opens a VISIBLE window/tab
ok = Rhino.RhinoDoc.OpenFile("/path/to/file.3dm")  # returns bool
d = Rhino.RhinoDoc.ActiveDoc  # now set correctly
Rhino.RhinoApp.SetFocusToMainWindow()  # bring Rhino to front
```

**What happens:** `OpenFile` is the same code path as File > Open in the GUI. It creates a real window, tab, and viewport set. `ActiveDoc` is set automatically. The user sees the document.

## New Document Workflow

Since `OpenFile` needs a file on disk, creating a *new empty* GUI document requires a two-step approach:

```python
# 1. Build a temp .3dm with desired settings
f3dm = Rhino.FileIO.File3dm()
f3dm.Settings.ModelUnitSystem = Rhino.UnitSystem.Millimeters
f3dm.Settings.ModelAbsoluteTolerance = 0.01
tmp_path = "/tmp/rhino-new-<uuid>.3dm"
f3dm.Write(tmp_path, 8)

# 2. Open it as a visible GUI document
Rhino.RhinoDoc.OpenFile(tmp_path)
d = Rhino.RhinoDoc.ActiveDoc
d.ModelUnitSystem = Rhino.UnitSystem.Millimeters  # re-apply (File3dm settings are file metadata)
d.ModelAbsoluteTolerance = 0.01
sc.doc = d
Rhino.RhinoApp.SetFocusToMainWindow()
```

## Open Existing Document Workflow

```python
path = "/path/to/model.3dm"
if not Rhino.RhinoDoc.OpenFile(path):
    raise RuntimeError("OpenFile failed")
d = Rhino.RhinoDoc.ActiveDoc
sc.doc = d
Rhino.RhinoApp.SetFocusToMainWindow()
```

**Note:** `OpenFile` returns `False` if the file is already open in Rhino.

## Headless Documents (Unchanged)

Headless documents work fine with the original APIs since they intentionally have no GUI:

```python
# Headless — no window needed
d = Rhino.RhinoDoc.CreateHeadless(None)  # new empty
d = Rhino.RhinoDoc.OpenHeadless(path)     # open existing
```

## API Summary

| Method | Visible Window | ActiveDoc Set | Use Case |
|--------|---------------|---------------|----------|
| `RhinoDoc.Create(None)` | No | No | Unusable for GUI |
| `RhinoDoc.Open(path)` | Unreliable | Unreliable | Unusable for GUI |
| `RhinoDoc.OpenFile(path)` | Yes | Yes | GUI documents |
| `RhinoDoc.CreateHeadless(None)` | No | No | Background processing |
| `RhinoDoc.OpenHeadless(path)` | No | No | Background processing |

## Activation and Focus

```python
# Switch active tab to a specific document
Rhino.RhinoDoc.ActiveDoc = d

# Bring Rhino window to front (macOS)
Rhino.RhinoApp.SetFocusToMainWindow()
```

Both should be called together when switching documents. `SetFocusToMainWindow()` alone doesn't switch tabs; `ActiveDoc` alone doesn't bring the app to front.

## Running External Scripts

To run a standalone `.py` script (like `bike_frame_skeleton.py`) in a clean visible document:

1. Create a new GUI document (temp .3dm + `OpenFile`)
2. Read the script file
3. Append a `result = {...}` block to capture output
4. Pass the code to `bridge.execute()` with the new `document_id`
5. Zoom extents after execution

```python
# Pseudocode
doc = runtime_call("new_document", headless=False)
doc_id = doc['result']['document_id']

code = open("script.py").read() + "\nresult = {'done': True}"
execute(code, document_id=doc_id)
```
