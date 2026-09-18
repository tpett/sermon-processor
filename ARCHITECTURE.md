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
| **Diarization** | `sherpa-onnx` 1.13.8 | manylinux wheels for x86_64, so it ports unchanged. |
| **Reasoning** | `qwen3.6:35b-mlx` on mac-m1 via ollama HTTP | No GPU on `nas`. **Send no `format: json`** — 0.34.0 returns 501 for MLX models, and unconstrained is measurably *better* anyway (median punch-in 3.76 s → 2.20 s). |
| **Render** | ffmpeg, two-pass loudnorm, LAME `-q:a 3` mono | −17 LUFS / −1.5 dBTP; week-to-week spread 4.6 LU → 0.6 LU with no compressor. |
| **Web** | Flask — JSON API plus a few Jinja views | The work is blocking and CPU-bound with one user; async buys nothing. `send_file(conditional=True)` gives the HTTP range requests the seekable preview needs. |
| **Queue** | A `Job` table and one worker process. No Redis, no broker. | `job_queue.feature` demands survive-restart, no-double-run, backoff, budget exhaustion, manual retry — 24 scenarios of real behaviour. A table the suite can assert against directly beats a library it has to reach inside. At one job a week a broker is pure operational cost. |
| **Store** | SQLite + files on a ZFS dataset | 39 recordings, ~1/week. The entities are in `features/DOMAIN.md`. |
| **Client** | Vanilla ES modules + Canvas 2D, no bundler | The editor is two linked canvases, an `<audio>` element and a transcript panel. No build step keeps the Dockerfile single-stage. Revisit if the client outgrows it. |
| **Tests** | `pytest-bdd` 8.1.0 over `features/`, `playwright` 1.63.0 for the browser | One runner for all 460 scenarios. Verified: the whole spec collects as 604 tests. |

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
│   └── store/               entities, artifact paths
├── client/                  ES modules, Canvas, no build
├── tests/
│   ├── steps/               step definitions — THIN
│   └── conftest.py
└── experiments/             frozen. The record of how the numbers were made.
```

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
