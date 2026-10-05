# Architecture

Settled 2026-09-18. The specification came first and this follows from it; where
they disagree, `features/` wins.

## The shape, in one picture

```
              ┌──────────────────────── nas (Arch, Docker, ZFS) ───────────────────────┐
              │                                                                        │
  Garage S3 ──┼──▶ ingest ──▶ ANALYSIS ──▶ propose ──▶ [ awaiting review ] ──▶ render ─┼──▶ MP3
  (same box)  │                  │                            ▲                        │
              │                  │ HTTP                       │ HTTP + JSON            │
              │                  ▼                            ▼                        │
              │           ┌─────────────┐              ┌──────────────┐                │
              │           │   mac-m1    │              │   browser    │                │
              │           │ ollama only │              │  waveform,   │                │
              │           │ qwen3.6:35b │              │  transcript  │                │
              │           └─────────────┘              └──────────────┘                │
              └────────────────────────────────────────────────────────────────────────┘
```

Two hosts, one direction of dependency. `nas` calls mac-m1 over HTTP and holds no
credentials for it. mac-m1 never calls back.

## Layers

| Layer | What | Why this and not something else |
| --- | --- | --- |
| **Pipeline** | Python package, extracted from `experiments/src` | 4,624 lines already validated against 39 recordings. Every number in FINDINGS traces to it. Rewriting means re-validating. |
| **Speech to text** | `faster-whisper` 1.2.1 / CTranslate2 4.8.2, int8, in-container | mlx is Apple-only and the app runs on x86_64. Measured 6.2× realtime; word agreement with mlx is 98.9% and word timestamps match to 40 ms at p90. |
| **Diarization** | `sherpa-onnx` 1.13.8, pyannote segmentation 3.0 + TitaNet small, in-process | manylinux wheels for x86_64, so it ports unchanged. Evidence of *who is speaking* — the transcript panel and the waveform lane — and never a boundary source: FINDINGS measured it the worst one. Optional: without it a Proposal says `no speaker evidence` and analysis carries on. The two models (46 MB) are baked into the image against pinned sha256s rather than put on the `/models` volume, because a volume would mean an unverified first-run fetch. On a 2.8 h service on an M5 Max: 228 s at 8 threads (44× realtime), 257 s at 4, **4.6 GB peak RSS** either way. |
| **Reasoning** | `qwen3.6:35b-mlx` on mac-m1 via ollama HTTP | No GPU on `nas`. `format: json` is still sent when thinking is off; 0.34.0 refuses it with 501 for MLX models and the classifier retries unconstrained, which is the answer used — and measurably *better* anyway (median punch-in 3.76 s → 2.20 s). |
| **Render** | ffmpeg, two-pass loudnorm, LAME `-q:a 3` mono | −17 LUFS / −1.5 dBTP; week-to-week spread 4.6 LU → 0.6 LU with no compressor. |
| **Web** | Flask — JSON API plus a few Jinja views, served by **waitress in development as well as production** | The work is blocking and CPU-bound with one user; async buys nothing. `send_file(conditional=True)` gives the HTTP range requests the seekable preview needs. One process, four threads: the scrubbed playhead lives in a dict inside `creates_app`, and "set the boundary from the playhead" reads it back on a **later** request — under a multi-process server that read hits a different worker's empty dict and silently sets the boundary to zero. Running the same server in both places is the point; a production-only server is a production-only class of bug. |
| **Queue** | A `Job` table and one worker process. No Redis, no broker. | `job_queue.feature` demands survive-restart, no-double-run, backoff, budget exhaustion, manual retry — 24 scenarios of real behaviour. A table the suite can assert against directly beats a library it has to reach inside. At one job a week a broker is pure operational cost. |
| **Store** | SQLite + files on a ZFS dataset | 39 recordings, ~1/week. The entities are in `features/DOMAIN.md`. |
| **Client** | Vanilla ES modules + Canvas 2D, no bundler | The editor is two linked canvases, an `<audio>` element and a transcript panel. No build step keeps the Dockerfile single-stage. Revisit if the client outgrows it. |
| **Tests** | `pytest-bdd` 8.1.0 over `features/`, `playwright` 1.63.0 for the browser | One runner for all 487 scenarios; the whole spec collects as 638 tests. |

## Why the web framework is the least interesting choice

The spec divides cleanly by where it executes, and almost none of it is the
server:

| | scenarios | executes in |
| --- | --- | --- |
| analysis | 199 | the pipeline |
| processing | 51 | the pipeline |
| ingestion | 29 | the pipeline |
| operations | 24 | the queue |
| notifications | 19 | the pipeline |
| interface | 138 | the browser |

322 scenarios are Python whatever the server is; 138 are the browser whatever the
server is. Flask is chosen for being thin, not for being asserted.

## Repository layout

```
sermon-processor/
├── ARCHITECTURE.md          this file
├── STATE.md                 handoff
├── Dockerfile               single stage, python + ffmpeg
├── pyproject.toml
├── features/                THE SPEC — primary, language-agnostic
│   ├── README.md            vocabulary, lifecycle, tag conventions
│   ├── DOMAIN.md            entities and fields
│   └── validate_spec.py     portability guardrail
├── src/sermon/
│   ├── pipeline/            extracted from experiments/src
│   ├── web/                 Flask: API + views
│   ├── jobs/                the Job table and the worker
│   └── store/               entities, the data-root layout, artifact paths
├── src/sermon/web/static/  ES modules, Canvas, no build
├── tests/
│   ├── steps/               step definitions — THIN
│   └── conftest.py
└── experiments/             frozen. The record of how the numbers were made.
```

## The data root

One module, `src/sermon/store/layout.py`, decides where every file goes. Before
it, each writer picked its own path: sources landed beside their own directories,
rendered MP3s were loose at the top level, and the pipeline's scratch sat there
too, reading as a peer of the recordings.

```
<data root>/
├── sermon.sqlite3
├── recordings/<recording_id>/       everything belonging to one Recording
│   ├── source.flac                  the container the object key named
│   ├── preview.mp3
│   ├── transcript.json              one document per artifact kind
│   ├── waveform_peaks.json
│   ├── envelope.json
│   ├── analysis_progress.json       written through resolves_path; no row owns it
│   └── model_segments.json          the reasoning's own cuts; no row owns it either
├── published/<date> - <label>.mp3   what a human collects, rsyncs or points a browser at
├── corpus/diarization/              pipeline.segments.DATA_ROOT, pipeline.classify.DATA
└── models/                          HF_HOME; its own container mount
```

`corpus/` exists because the pipeline requires a `diarization` directory directly
beneath whatever those two roots are bound to, and treats a root without one as a
misconfiguration rather than an empty result. Binding them to `<data root>/corpus`
keeps that guard intact without a corpus-shaped directory pretending to be a peer
of the recordings.

The stored path is still the only record of where a file is: `Store.resolves`
reads it, `ResolvesStoredPath` refuses anything climbing out of the root, and
`layout` narrows what the writers put there. So moving files means rewriting rows.
`sermon-organize` does both, file first and row second, which leaves an
interruption repairable: a row naming a missing file whose destination already
holds it, which the next run recognises and writes. It is idempotent.

Links handed out before the move still resolve. `/api/artifacts/<path>` falls back
to the one Artifact whose stored path *ends* with the path asked for, so
`2026-09-13 - Hebrews 12.25-29.mp3` finds `published/2026-09-13 - …mp3`. Only a
unique match counts, or `preview.mp3` would resolve to whichever Recording came
first. The fallback is on the row, not on the old directory, so nothing has to be
left behind on disk.

A Recording's source that is not on disk is streamed from the bucket, never
fetched into the data root. `/api/artifacts/<path>` asks the object store for
that one named object and passes its body through in bounded chunks, with the
object's own length, type and entity tag; nothing is written and no row changes.
A single byte range is forwarded so a browser can resume. Fetching to disk stays
with `sermon-fetch` and the download job, which are asked for deliberately: a
click on a link must not commit the server to holding a 0.4–1.4 GB copy.

## Two rules that keep the spec primary

**Step definitions carry no logic.** A step translates English into a call and
asserts on the result. Anything else belongs in `src/sermon/`, or a rewrite in
another language loses it — which is the whole reason the spec is the primary
artifact.

**The features name what the system talks to, never what it is built with.**
HTTP, S3, ffmpeg, ollama, a tailnet: fine, they are the contract. Flask, SQLite,
Python, a job library: not in a scenario. `validate_spec.py` enforces this and
allows technology names inside comments, where they cite measurements.

## The one migration with real risk

`experiments/src` mixes library code with argparse CLI drivers. The product wants
the library half — `audio`, `blocks`, `cues`, `segments`, `rules`, `features`,
`acoustic`, the render chain, the ollama client.

**That extraction must be provably behaviour-preserving**, because every claim in
FINDINGS rests on the current code. The check already exists: re-run scoring after
the move and compare against `data/results.jsonl`. Identical output or the
extraction is wrong. Do not refactor and extract in the same commit.

## Deployment

`bin/nas app-deploy sermon-processor` in the homelab repo — verified
language-agnostic, it needs only a `Dockerfile` at the source root. It rsyncs the
config stack, `git archive HEAD` into `src/` on the server, then
`docker compose up -d --build`.

- Config stack: `stacks/sermon-processor/` in the homelab repo, following the
  `workouts` precedent.
- Network: join `proxy`, publish no ports, add a Caddy route. A container on
  `proxy` reaches mac-m1's ollama — verified, no extra configuration.
- Storage: a dedicated ZFS dataset for recordings and renders. `zfs create` needs
  sudo, so propose the command rather than running it.
- Secrets: Garage credentials via `bin/nas secrets push`; `.env` is never
  committed.
- **Known trap:** the macOS firewall rule allowing ollama is pinned to
  `/opt/homebrew/Cellar/ollama/0.34.0/libexec/ollama`. A `brew upgrade` changes
  that path and connections start hanging rather than refusing.

## What is still unmeasured

- **Nothing has run on `nas`.** Every timing is a laptop. Transcription should be
  faster there (Zen 5 has AVX-512, which CTranslate2 uses) but that is an
  expectation.
- **Word edges and the tail guard.** Both currently key off utterance boundaries,
  the one thing ASR engines disagree about. Word edges halve the gap between
  engines at the oracle — but the oracle is the ceiling, not what snapping picks.
- **No second opinion in v1**, so a confidently wrong boundary looks like a
  confidently right one. The one measured instance was 19.6 s off.
