#!/usr/bin/env python3
"""Speech-to-text over HTTP.

STATUS (2026-09-17): **not deployed, and not deployable as written.** The model
host serves ollama and nothing else, and production reaches it over HTTP with no
shell access, so there is nowhere to run an mlx service. Kept because the
in-container transcriber will have this exact shape with a different engine
behind `transcribe()`, and because this version is the reference that was
verified byte-identical to the validated pipeline -- 1,055 utterances and 9,171
words on 2026-09-06, 32 on 2026-09-13, zero differences. Any replacement has to
clear that same bar.

Ollama has an OpenAI-shaped `/v1/audio/transcriptions` endpoint but no speech
model to put behind it (checked on 0.32.15 and 0.34.0; every `whisper` tag in the
library registry 404s). So transcription needs its own service, and this is it:
the same call `experiments/src/transcribe.py` makes, behind a socket.

**The point is that it is the same call.** Every boundary figure in
experiments/FINDINGS.md was measured with mlx-whisper at these exact settings.
faster-whisper or whisper.cpp would be easier to deploy and would silently
invalidate all of it, so this wraps rather than replaces.

The response is *not* OpenAI-shaped. That schema drops `avg_logprob`,
`no_speech_prob` and `compression_ratio`, which the blocking stage uses as its
music-versus-speech signal. The shape here matches `transcribe_one()` instead.

    POST /transcribe?word_timestamps=1     body: the audio file, any ffmpeg format
    GET  /health

No authentication, by design — see features/interface/authentication.feature.
Bind it to a trusted interface or do not run it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_MODEL = os.environ.get(
    "WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
HOST = os.environ.get("WHISPER_HOST", "0.0.0.0")
PORT = int(os.environ.get("WHISPER_PORT", "11435"))
MAX_BYTES = int(os.environ.get("WHISPER_MAX_BYTES", str(8 * 1024 ** 3)))


def decode_16k_mono(src: Path, dst: Path) -> None:
    """Identical to the decode in transcribe.py — first channel, 16 kHz, mono."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src),
         "-af", "pan=mono|c0=c0", "-ar", "16000", "-ac", "1", "-y", str(dst)],
        check=True)


def transcribe(wav: Path, model: str, word_timestamps: bool) -> dict:
    import mlx_whisper

    t0 = time.time()
    # condition_on_previous_text=False: long-form Whisper loops over music and
    # silence, and twenty minutes of singing is exactly that condition.
    r = mlx_whisper.transcribe(
        str(wav), path_or_hf_repo=model, language="en",
        word_timestamps=word_timestamps, condition_on_previous_text=False,
        verbose=False)
    elapsed = time.time() - t0

    utterances = []
    for s in r["segments"]:
        u = {
            "start": round(float(s["start"]), 3),
            "end": round(float(s["end"]), 3),
            "speaker": None,
            "text": s["text"].strip(),
            "avg_logprob": round(float(s.get("avg_logprob", 0.0)), 4),
            "no_speech_prob": round(float(s.get("no_speech_prob", 0.0)), 4),
            "compression_ratio": round(float(s.get("compression_ratio", 0.0)), 3),
        }
        if word_timestamps and s.get("words"):
            u["words"] = [{"w": w["word"].strip(),
                           "start": round(float(w["start"]), 3),
                           "end": round(float(w["end"]), 3)} for w in s["words"]]
        utterances.append(u)
    return {"utterances": utterances, "elapsed_s": round(elapsed, 1)}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            self._send(200, {"ok": True, "model": DEFAULT_MODEL})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parts = urlparse(self.path)
        if parts.path != "/transcribe":
            self._send(404, {"error": "not found"})
            return

        q = parse_qs(parts.query)
        model = q.get("model", [DEFAULT_MODEL])[0]
        word_ts = q.get("word_timestamps", ["1"])[0] not in ("0", "false", "no")

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._send(400, {"error": "empty body; POST the audio file as the body"})
            return
        if length > MAX_BYTES:
            self._send(413, {"error": f"body exceeds WHISPER_MAX_BYTES ({MAX_BYTES})"})
            return

        tmp = Path(tempfile.mkdtemp(prefix="whisper-svc-"))
        try:
            src = tmp / "upload"
            # Stream to disk. A three-hour FLAC is well over a gigabyte and does
            # not belong in memory.
            with src.open("wb") as f:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            if remaining > 0:
                self._send(400, {"error": "client disconnected before body was sent"})
                return

            wav = tmp / "audio.16k.wav"
            try:
                decode_16k_mono(src, wav)
            except subprocess.CalledProcessError as e:
                self._send(415, {"error": f"ffmpeg could not decode the upload: {e}"})
                return

            res = transcribe(wav, model, word_ts)
            res |= {"model": model, "word_timestamps": word_ts}
            self._send(200, res)
        except Exception as e:  # noqa: BLE001 - surface it to the caller, keep serving
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    # One model, one GPU. Concurrent transcriptions would contend for the same
    # unified memory and finish no sooner, so requests queue at the socket.
    srv.daemon_threads = True
    print(f"whisper-service on {HOST}:{PORT}  model={DEFAULT_MODEL}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
