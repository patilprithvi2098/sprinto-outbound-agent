This project uses the MESA framework.
Plan: docs/mesa/ (execution-prompt.md, phases.md, brief.md).
Look: DESIGN.md (follow exactly).
Say "build phase N" to build; every phase runs current docs (context7), DESIGN.md and playwright-qa before it counts as done.
Runs on localhost only; secrets stay in .env and are never committed; emails go only to the operator's own address.
