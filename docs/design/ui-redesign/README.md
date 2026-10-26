# Reviewer UI redesign — design brief

This folder is the whole design. Implementers should not need anything outside the repo.

- `README.md`: this brief. It covers tokens, layout, every screen, interactions, and the constraints that come from the tests.
- `screens/*.png`: renders of each artboard. Look at them first: `review-desktop`, `edit-desktop`, `details-drawer-desktop`, `view-only-desktop`, `list-desktop`, `review-phone`, `edit-phone`, `list-phone`. The sample data in them is illustrative.
- `source/*.dc.html`: the artboards' source from the design canvas. They are reference only. They need the canvas runtime (`support.js`) to render and are not meant to be served. Read them for exact values: colours, sizes, copy, element order.

What the owner asked for, in their own words, is recorded in `CLAUDE.md` under "The pins have moved, on purpose" (2026-10-26). The behaviour is specified in `features/`. Where this brief and a scenario disagree, **the scenario wins**.

## Principles

1. **Review first.** The page opens on what the reviewer does nearly every week. They press **Preview the cut**, listen, then press **Approve and render**. The editor stays hidden until it is asked for.
2. **Editing is a mode.** The detail waveform, zoom, nudges and removal marking appear only in Edit mode. Edit mode also has its own preview, so a change can be heard without leaving it.
3. **Metadata is a drawer.** Why this cut, the analysis stages, the transcript, the source details and the recording-level actions all live in one Details panel. It is closed by default. A warning shows as a count badge on the button that opens it.
4. **One layout for every role.** A viewer gets Review mode minus Edit, Approve, Skip and the recording actions, plus downloads. Nothing is designed separately for viewers. Their controls are simply absent.
5. **Dark, audio-tool look.** The waveform is the hero. Chrome stays quiet.

## Tokens

These replace the `:root` palette in `src/sermon/web/static/review.css`. The design is dark only. The current light tokens and the `prefers-color-scheme` / `data-theme` switching can go.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0d0f12` | page ground, sunken wells (seam cards, inputs) |
| `--panel` | `#14171b` | header, rails, cards |
| `--raised` | `#1b1f24` | selected segment-control item, small buttons |
| `--line` | `#262b31` | hairlines, card borders |
| `--line2` | `#343a42` | control borders |
| `--text` | `#e7e9ec` | primary text; the **Preview** button is filled with it (text in `--bg`) |
| `--muted` | `#9aa3ad` | secondary text; passes 4.5:1 on `--panel` |
| `--accent` | `#5cc8e0` | primary action (Approve, Review, Download), IN/OUT markers, selected segment, links (`#7fd6ea`) |
| `--accent-ink` | `#06222a` | text on accent |
| `--warn` | `#f0b450` | awaiting-review status, warnings, removed spans; tinted backgrounds use `rgba(240,180,80,0.10–0.18)` |
| `--bad` | `#ef7b78` | failures, Discard |
| playhead | `#ffffff` | 1 px line plus a downward triangle |
| waveform kept | `#d6dee6` (detail), `#c9d3dc` (overview) | audio that ships |
| waveform cut away | `#4a525c` | audio outside the cut, also dimmed by a `rgba(0,0,0,0.35)` overlay |
| waveform removed | `#6b5530` bars under a hatched warn overlay with dashed warn edges | removed spans |

**Block types** (service order, bands, segment swatches). These are the existing dark values:

| Type | Colour |
|---|---|
| sermon, lesson | `#7fb08c` |
| music | `#a796c4` |
| prayer | `#7fa3c4` |
| scripture_reading | `#d9a860` |
| communion | `#c081a0` |
| announcements | `#8a857c` |
| qa | `#6fb3ad` |
| seminar | `#b79a6a` |
| rehearsal, other | `#7c766d` |
| meeting (segment swatch) | `#c9b37a` |

**Type:**
- Inter at 400/500/600/700 for UI.
- JetBrains Mono at 400/500/600 for every time, duration, filename and timecode, with tabular figures.
- Body text is 14/1.45.
- The page title is 17/600.
- The hero label is 24/600 with −0.02em tracking.
- Section eyebrows are 11/600, uppercase, 0.08em tracking, in `--muted`.
- The transport timecode is mono 20/500.
- Fonts may be self-hosted or use the system stack (`system-ui` / `ui-monospace`). Loading from Google Fonts is optional, and the app must not depend on it.

**Shape:**
- Radii: cards 10–12 px, controls 8 px, pills 999 px.
- Segmented controls: a 3 px padded well on `--bg` with a 1 px `--line` border. The selected item is `--raised` with `--text`, the others are `--muted`.

**Targets:** every control on a phone is at least 44 px tall. On desktop, small controls are 32 px and primary ones are 44–52 px.

## Screens

The screen names match the files in `source/`.

### Review mode, desktop (`Main.dc.html`, the default)

The header bar is `--panel` with a bottom hairline. From left to right:
- a "‹ Recordings" link;
- a divider;
- the title, with the date, start time and duration under it in mono;
- the status pill (warn tint for awaiting review);
- the **Review | Edit** segmented switch (reviewers only);
- the **Details** button, with a warn count badge when there are warnings;
- the signed-in avatar button.

The body has three columns and wraps on narrow screens.

**Left rail (about 264 px): Service order.**
- One row per Block: a 4 px colour bar, the start time in mono, the Block name, and a one-line note.
- The Segment's Block is highlighted with an accent left edge and an accent tint, and its note reads "Segment · proposed".
- Clicking a row starts playback there. The existing Block preview and "start here" behaviour moves here.

**Centre.**
1. **Whole-recording strip.**
   - An hour ruler and a 72 px waveform. Kept audio is light and everything else dim.
   - The Segment is outlined with accent edges.
   - A 6 px band underneath shows the Blocks in their type colours.
2. **"The cut" hero card.**
   - On the left: the classification swatch and name, then the label at 24/600, then `in → out · length · N s removed` in mono.
   - On the right: the cut-light lamp with a short status line, and **Preview the cut**. That is a 52 px pill filled with `--text`, with a play/pause icon.
   - Below them, a grid of **seam cards**: Opening, one per removed span ("Removal · 0.8 s"), and Ending. Each card has:
     - its name and its time;
     - a 56 px waveform of 5 s either side, with the cut line in the centre (accent for a punch point, warn for a removal join);
     - the words either side, the words before the cut right-aligned and muted;
     - a small "Hear the opening / the join / the ending" button.
   - A card whose seam carries a warning (for example "check the opening") gets a warn-tinted border.
   - The card's footer reads "Something off? Adjust the punch points or remove a span." with an **Edit the cut** button. That button is the same action as the header switch.

**Right column (320–360 px): this Segment.**
- The warning callout: warn tint, an icon, a bold lead such as "Check the opening.", then one line.
- The publication label input.
- The Publish | Archive segmented control.
- The output filename in mono, muted.
- A spacer.
- **Approve and render**: full width, 52 px, accent, with a check icon.
- **Skip this segment**: a ghost button.

### Edit mode, desktop (`Edit.dc.html`)

The header and the left rail are the same as in Review mode. In the header switch, **Edit** is selected.

**Centre.**
1. The whole-recording strip shrinks to 56 px and gains the detail-window marker.
2. **Detail editor card.**
   - A tick ruler.
   - A 240 px detail waveform. On it:
     - the region before the punch-in is dimmed;
     - the IN marker is an accent line with an "IN 1:02:14.50" tag;
     - removed spans are hatched, each with a small "0.8 s removed · Put back" pill along the bottom;
     - the current **selection** has an accent tint and accent edges, with a floating toolbar above it. The toolbar holds the selection length in mono, a play button, **Remove** (warn-filled) and a clear button.
   - A transcript lane: phrases sit as chips at their times, and each chip is a button that sets the focused boundary.
   - The transport: a play/pause circle, the mono timecode, the zoom segmented control (Whole / Minutes / 30 s / 3 s, the existing steps) and a spacer. After the spacer come small muted underlined links: "At playhead: set in · set out". These are the old Punch in / Punch out buttons, deliberately de-emphasised.
3. **Preview bar.** It holds **Preview the cut** (a 40 px `--text` pill), the cut lamp and its status, a spacer, then "Hear one:" followed by a pill per seam. The preview always plays the current cut, removed spans included.
4. A one-line key help: drag to select, space, `=`/`−` zoom, `\` fit, `,`/`.` scrub, `←`/`→` nudge. The existing server-provided key text stays authoritative.

**Right column: "Editing the sermon".**
- The classification select (this is the reclassify control).
- Two punch-point tiles. Each has its name, its time in mono at 17 px, and −0.1 / +0.1 / "go to" buttons. The focused tile has an accent border.
- The note "Machine proposal unchanged · Revert".
- "Removed from inside · total", then a list of spans. Each row has "Hear join" and "Put back". With no spans, the empty text invites dragging across the waveform.
- "Changes save as you make them, and the preview always plays the current cut."
- **Done editing**: full width, filled with `--text`. It returns to Review mode.

The fuller boundary controls stay available in Edit mode, but not prominently, for example in a collapsed group under the tiles:
- timecode entry, "Set the … from the playhead", and the nudge step set (`details.nudges`);
- the span reach controls;
- the other punch-in candidates.

### Details drawer (`Drawer.dc.html`)

- A right-hand overlay, 440 px wide, over a dim scrim. On a phone it is full width.
- The header reads "Details" with a close button.
- The recording warning callout comes first, for example "Source clipping detected. This comes from the recorder and can't be repaired here."
- Then accordion sections. Each has a title and a one-line summary, and only one is open at a time:
  1. **Why this cut**: grade tiles (classification, boundaries, punch-in, punch-out), the evidence list (time links that seek, plus the finding), and the other punch-in candidates.
  2. **Analysis**: the stages with how long each took, plus failure detail when there is any.
  3. **Transcript**: this segment's transcript and "Show the whole recording's transcript".
  4. **Source**: recorded at, duration, size, format and object key, plus "Download the original".
  5. **Recording actions**: Re-run analysis, Create a segment, Split, Merge, Archive whole recording, and Discard recording (in `--bad`). Viewers do not get this section.
- The drawer may be a closed `<details>`/dialog that is always in the DOM. That is what keeps the regex-read tests working (see "Test constraints").

### View only (`Viewer.dc.html`)

- This is Review mode for a viewer. There is no Review | Edit switch. A "View only" pill sits in its place.
- The hero card has no Edit footer.
- The right column becomes **Published**: the label, the filename, Length and Size tiles, a **Download MP3** primary button, and a "Download the original recording" link.
- For a segment not yet published, the column says so and offers only the original.

### Recordings list (`List.dc.html`)

- **Header:** "Recordings", then **Scan the bucket**, then a notifications button with an unread count badge, then the avatar.
- **Body:** at most 1080 px wide.
  1. **Needs your review.** One card per recording awaiting review. Each shows the title at 18/600, the date, time and duration in mono, the Block band (the segment at full opacity, the others at 45%), and the line "Sermon proposed · in – out · length". A **Review** accent button opens the recording.
  2. **Filters:** a kind segmented control (All / Services / Classes / Meetings / Rehearsals), plus a small search box on the right. Search is `@deferred` in the spec, so keep it small or leave it out.
  3. **Week groups**, newest first. A week runs Monday to Sunday and is labelled by its Sunday (the step definitions read `data-week-heading` / `data-week-ending`). Each group is one card of rows:
     - Each row has the day and time in mono, the title (with its kind tag or series acronym such as TEC or CT), the segment chips (swatch plus label), the duration in mono, and the status as a coloured dot plus a word: awaiting review (warn), analysing with progress (accent), published, archived and nothing to publish (muted), ingest failed (bad).
     - An untitled recording shows "Untitled recording" in muted text.
     - Silence-or-noise rows are a single thin muted line: time, then "Silence or noise", then duration.
  4. Paging: "Page 1 of 4 · Older recordings".

### Phone (`PhoneReview.dc.html`, `Phone.dc.html`, `PhoneList.dc.html`)

At 390 px wide:
- **Review:**
  - The header has back, the title and date, **Edit**, and Details with a warn dot.
  - Below it come the Block band, then the hero card (label, length, a full-width **Preview the cut**, and the seams as rows with 44 px play buttons), then the warning, the label input and Publish | Archive.
  - A bottom bar is pinned: Skip, then **Approve and render**.
- **Edit:**
  - A 150 px detail waveform, then a transport with play, timecode, and − / + zoom.
  - Then "Drag to select a span · At playhead: set in · set out".
  - Then the preview row (Preview the cut, Opening, Join, Ending), the punch tiles with 44 px nudges, and the removed list.
  - A bottom bar is pinned: **Done editing**.
- **List:** a needs-review card with a full-width "Review the sermon", then compact two-line rows.

## Interactions to keep

All of these exist today in `review.js` and `playback.js`. Keep them working, and keep them working while focus is anywhere that is not a text field:
- **Space** plays and pauses.
- **Zoom in:** `=` / `+` / `1` / Cmd-1. **Zoom out:** `-` / `_` / `3` / Cmd-3. **Fit:** `\` or Shift-Z.
- **Scrub:** `,` and `.`, with Shift and Alt as step modifiers.
- **Nudge the focused boundary:** ArrowLeft and ArrowRight.
- Click the ruler to seek. Drag the IN/OUT handles and the scrub handle.
- The cut light keeps frame accuracy (`cutlight.js`).

## New interactions

- **Drag to select (Edit mode).**
  - On the detail pane, pointerdown, then pointermove beyond a few pixels, makes a selection. A click without movement still seeks and plays as today.
  - The selection is clamped to the cut range.
  - **Remove** submits the existing removal form (`do=remove`, `from`, `to` as timecodes). The server already accepts both ends.
  - **Put back** is the existing restore.
  - The canvas shows a Delete-key shortcut for removing a selection. No scenario asks for it, so do not build it.
- **Review | Edit.**
  - Both modes are rendered by the server every time. The mode is a class on a wrapper that CSS and JS toggle, so a mode switch never reloads.
  - Edit opens when the address carries `mode=edit` (the step definitions use exactly that), and when the punch-in is graded hard. Every redirect after an edit must carry `mode=edit` back.
  - Each edit still POSTs and redirects, and that redirect must land back in Edit mode.
- **Preview the cut** plays the current cut: the opening window, then each removal join, then the ending window, with removed spans left out. Per-seam "hear" buttons play one seam. The joins already come from `GET /api/segments/<id>/join`. The whole preview needs the equivalent for both boundary windows, or a sequence of joins.

## Test constraints

The step definitions read the raw HTML with regular expressions (`tests/steps/_markup.py`). A redesign that ignores the rules below breaks most of the suite.

- **Markup rules:**
  - `data-field="x"` must be the last attribute before `>`, and the value is the text directly inside the element, read up to the next `<`.
  - Rows are `<li data-row=…>` with no nested `<li>` inside.
  - `data-role` and `data-field` lookups are dicts, so if one is rendered twice, both copies must carry the same value.
- **Literal markers that must survive, in this order:**
  - `<section class="waveform"`, then the punch-point rows, then `<div class="supporting">`.
  - The Approve `action-control` comes before `<h3>Boundaries</h3>`.
  - `class="spans"` comes before `class="bands"`.
  - `data-role="detail"` comes before `detail-ticks`.
- **Playwright** runs at a 1400×1000 desktop and a 390×844 phone:
  - no horizontal scroll;
  - titles are not clipped;
  - the phone editor checks must enter Edit first, since the scenario now says so.
- **Keep the copy.** On-screen strings that scenarios assert, such as button labels and empty states, stay unless a scenario changes them.

## Decisions the spec settled

- **Approve is offered only in Review mode.** Edit mode offers the previews and **Done editing**. The edit-mode screenshot is right not to show Approve.
- **Promote command.** It is `sermon-user promote <email>`, and it replies "<email> is now a reviewer". Every new person, and every existing `User` row when roles ship, starts as a viewer. With sign-in not configured, the person at the browser is a reviewer, as today.
- **Theme.** Dark is not in the spec, because a scenario cannot observe it. Build it anyway, since it is the design.
- **Markup contract.** The new step definitions pin these hooks:
  - `data-role="cut-view" data-mode`
  - the `edit-the-cut` / `done-editing` links
  - `data-row="seam"` cards
  - `preview-cut data-seams="before:after,..."`
  - `recording-details`, `open-details data-warnings` and `data-details-section`
  - `data-row="awaiting"`
  - `data-week-heading` / `data-week-ending`
  - `data-field="access"` reading "View only"
  - `data-emphasis` on the punch rows and on the preview

  See `STATE.md` (2026-10-26) and `tests/steps/` for the exact shape. Where a hook and this brief disagree, the hook wins.
