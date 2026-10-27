# ui-convergence config — sermon-processor

## Design source
- No Figma. The ground truth is `docs/design/ui-redesign/`:
  - `README.md`: tokens, layout and per-screen spec.
  - `screens/*.png`: renders of each artboard.
  - `source/*.dc.html`: exact values.
- The canvas is https://claude.ai/artifact/19v53rP7yb4NAcGsNHxUV5 and needs a claude.ai sign-in. Agents use the repo copy.
- Screen map:

  | screen | desktop render | phone render | dev path |
  |---|---|---|---|
  | Review mode | review-desktop.png | review-phone.png | `/recordings/<id>?segment=<sid>` |
  | Edit mode | edit-desktop.png | edit-phone.png | `/recordings/<id>?segment=<sid>&mode=edit` |
  | Details panel | details-drawer-desktop.png | — | Review mode, Details opened |
  | View only | view-only-desktop.png | — | Review mode as a viewer (sign-in on, role viewer) |
  | Recordings list | list-desktop.png | list-phone.png | `/` |

- Viewports: desktop 1440×960 (the tests use 1400×1000), phone 390×844.

## Running the app
- Run in the worktree:

  ```
  SERMON_DATA_ROOT=~/Source/open/sermon-tools/devdata-ui SERMON_BIND_HOST=127.0.0.1 SERMON_PORT=8811 .venv/bin/sermon-serve
  ```

  - Copy `.env` from the main checkout first.
  - With no Access variables set, sign-in is off and the person at the browser is a reviewer.
- Restart the server after changing Python or a template. Static CSS and JS reload on a browser refresh.
- Dev data: `~/Source/open/sermon-tools/devdata-ui`, a snapshot of production's store plus transcripts, peaks and preview MP3s. It has no source FLACs, so seams and joins fall back to the preview MP3. To get a Segment to review, use Re-cut on a completed one in the local copy.

## Scoping rule
- There is no feature flag. The redesign *is* the live UI, so edit in place.
- The guard is the test suite plus the spec's markup contract (`docs/design/ui-redesign/README.md` → "Test constraints" and "Decisions the spec settled"):
  - Keep `data-field` last before `>`.
  - Keep rows as `<li data-row>` with no nested `<li>`.
  - Keep the markers `<section class="waveform"` → punch rows → `<div class="supporting">`.
  - Never change feature files or pins.
- Never touch: `experiments/`, `features/*.feature`, `tests/test_spec_harness.py` pins.

## Design tokens
- Source: the `:root` custom properties in `src/sermon/web/static/review.css`, which follow the brief's token table. Use tokens (`var(--…)`), never raw hex, except where the brief gives a one-off value.

## Quality gates
- `SERMON_SPIKE_DATA=<main checkout>/experiments/data .venv/bin/python -m pytest -m "not slow" -q`. No test that passes on master may fail. Master's baseline is 177 failures.
- `.venv/bin/python features/validate_spec.py`.
- Commit policy: one commit per screen on `tpett/ai/ui-convergence`, subject ending " [AI]". Never commit to master directly.

## Convergence state (per run)
- allowlist and resolved/deferred: kept in the session scratchpad. Owner questions go in the PR description.
