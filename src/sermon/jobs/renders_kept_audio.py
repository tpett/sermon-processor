from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from sermon.pipeline.render import FADE_S, LAME_Q, TARGET_I, TARGET_LRA, TARGET_TP, render
from sermon.removes_span import kept_pieces

JOIN_MEDIA_TYPE = "audio/mpeg"


class JoinProducedNothing(RuntimeError):
    pass


def _runs(arguments):
    return subprocess.run(arguments, capture_output=True)


def _lasting(start, end):
    return float(f"{end - start:.3f}")


def _inputs(source, pieces):
    arguments = []
    for start, end in pieces:
        arguments += ["-ss", f"{start:.3f}", "-t", f"{_lasting(start, end):.3f}", "-i", str(source)]
    return arguments


def _joins(pieces, channel, fades):
    chains = []
    for index, (start, end) in enumerate(pieces):
        steps = [f"pan=mono|c0=c{channel}"]
        if fades:
            length = _lasting(start, end)
            fade = min(FADE_S, length / 2)
            steps.append(f"afade=t=in:st=0:d={fade:.4f}")
            steps.append(f"afade=t=out:st={max(length - fade, 0):.4f}:d={fade:.4f}")
        chains.append(f"[{index}:a]{','.join(steps)}[p{index}]")
    joined = "".join(f"[p{index}]" for index in range(len(pieces)))
    return ";".join(chains) + f";{joined}concat=n={len(pieces)}:v=0:a=1"


def _loudnorm(measured=None):
    asked = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
    if measured is None:
        return f"{asked}:print_format=json"
    return (
        f"{asked}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )


def _encodes():
    return ["-c:a", "libmp3lame", "-q:a", str(LAME_Q), "-ar", "44100", "-ac", "1"]


def measures_kept(source, pieces, channel=0):
    """Pass 1 over exactly the audio that ships: the kept pieces, joined."""
    report = _runs(
        ["ffmpeg", "-v", "info", "-nostats", *_inputs(source, pieces),
         "-filter_complex", f"{_joins(pieces, channel, True)},{_loudnorm()}",
         "-f", "null", "-"]
    ).stderr.decode(errors="replace")
    opened, closed = report.rfind("{"), report.rfind("}")
    if opened < 0 or closed < opened:
        raise RuntimeError("loudnorm measurement pass produced no JSON")
    return json.loads(report[opened:closed + 1])


def renders_kept_audio(
    source, start, end, destination, *, removed=(), channel=0, loudness=True, fades=True
):
    if not removed:
        return render(source, start, end, destination, loudness=loudness, fades=fades, channel=channel)
    pieces = kept_pieces(start, end, removed)
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    measured = measures_kept(source, pieces, channel) if loudness else {}
    graph = _joins(pieces, channel, fades)
    if loudness:
        graph += f",{_loudnorm(measured)}"
    _runs(
        ["ffmpeg", "-v", "error", "-nostats", *_inputs(source, pieces),
         "-filter_complex", graph, *_encodes(), "-y", str(destination)]
    )
    return measured


def encodes_join(source, pieces, channel=0):
    """The kept pieces either side of a join, as they will sound, without the loudness pass."""
    with tempfile.TemporaryDirectory() as scratch:
        heard = Path(scratch) / "join.mp3"
        produced = _runs(
            ["ffmpeg", "-v", "error", "-nostats", *_inputs(source, pieces),
             "-filter_complex", _joins(pieces, channel, True), *_encodes(), "-y", str(heard)]
        )
        if produced.returncode != 0 or not heard.is_file() or not heard.stat().st_size:
            raise JoinProducedNothing(produced.stderr.decode(errors="replace")[-500:])
        return heard.read_bytes()
