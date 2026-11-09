from sermon.pipeline import segments


def test_each_seminar_session_is_seeded_and_the_introduction_is_not(monkeypatch):
    monkeypatch.setattr(segments, "speaker_edges", lambda doc: [])
    doc = {"recording_id": "recording_20261107_082943", "duration": 8000.0, "utterances": []}
    blocks = [
        {"type": "other", "start": 0.0, "end": 541.0, "confidence": 0.8},
        {"type": "seminar", "start": 541.8, "end": 2600.0, "confidence": 0.9},
        {"type": "other", "start": 2600.0, "end": 2971.0, "confidence": 0.7},
        {"type": "seminar", "start": 2971.3, "end": 6716.0, "confidence": 0.9},
        {"type": "qa", "start": 7600.0, "end": 8000.0, "confidence": 0.8},
    ]

    seeded = segments.derive(blocks, doc, refine=False)

    assert [item["classification"] for item in seeded] == ["seminar", "seminar"]
    assert seeded[0]["punch_in"] == 541.8
    assert seeded[1]["punch_in"] == 2971.3
