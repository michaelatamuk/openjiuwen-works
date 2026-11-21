# Feature map

A feature map is the product's promise in a file: what a person does, what they should observe, and
which proof scenarios exercise it. `works ui` compares the map with the run's verdict, so an
engineer sees which promised features the proof actually covered.

## Format

`features/<product>.yaml`:

```yaml
schema_version: 1
product: blender
features:
  - id: material-preview
    name: Material preview
    user_path: A person switches to material preview
    expected: The preview does not flicker
    scenario_ids: [render-preview-material]
  - id: export-pdf
    name: PDF export
    user_path: A person exports a table to PDF
    expected: The last column is present
    selector: "[data-export=pdf]"   # or command: "python scripts/check_pdf.py"
```

A feature needs at least one of `scenario_ids`, `selector` or `command`. `scenario_ids` are how the
current proof measures coverage; a selector or command is reserved for the preview node.

## Coverage

The Evidence panel shows every feature as covered, failed or not covered:

- **covered** — at least one declared scenario appears in the proof's verdict;
- **failed** — a scenario ran and did not pass;
- **not covered** — no declared scenario ran in this proof.

The map cannot make a claim on its own. A green feature is only a scenario that actually passed.

## Readiness

`works readiness` requires a feature map and at least one declared feature. An invalid map fails the
gate instead of silently disappearing.

## Open

Preview artifacts (screenshot, video, log, trace) are not attached yet; T2.19 remains open for that
part and for checking selectors/commands at run time.
