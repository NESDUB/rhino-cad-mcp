# Universal Quickstart

1. Read `AI_ORIENTATION.md` for the stable operating model and `.bridge/orientation/manifest.json` for payload and precedence rules.
2. Decide your role: a **controller** creates/reviews structured requests remotely; an **operator** executes locally on `operator/<task-id>`; a **reviewer** independently verifies the proposed branch.
3. Read the matching guide: controller → `.bridge/orientation/controller.md`; operator → `.bridge/orientation/operator.md` and `CLAUDE.md`; reviewer → `.bridge/orientation/reviewer.md`.
4. Read `.bridge/protocol.json`, inspect available `.bridge/state/*.json`, and read the full active request before action.
5. If locally available, run `./orient.sh controller|operator|reviewer|universal` to obtain a self-contained brief with clearly labeled live facts. Do not treat unavailable local or Rhino state as known.
