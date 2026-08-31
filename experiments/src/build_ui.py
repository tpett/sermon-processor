#!/usr/bin/env python3
"""Assemble the waveform spike page with its data inlined."""
from pathlib import Path
import json, sys

HERE = Path(__file__).resolve().parent.parent
data = (HERE / "work" / "ui_data.json").read_text()
shell = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2])
out.write_text(shell.replace("/*__DATA__*/null", data))
print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB)")
