# Controller-authored payload — _example
# Non-mutating fixture: reads document metadata only, no geometry changes.
# Safe for dry-run and negative-test validation.
import scriptcontext as sc

doc = sc.doc
result = {
    "example": True,
    "doc_name": doc.Name,
    "object_count": doc.Objects.Count,
    "created_by": "bridge-phase18-001",
    "note": "Non-mutating fixture — reads document metadata only, no mutations."
}
