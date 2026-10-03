def covering_transcript(duration, *, recording_id, confidence=0.92, text="good morning"):
    utterances = []
    start = 0.0
    while start < duration:
        end = min(start + 8.0, duration)
        words = [
            {"w": part, "start": start + index * 0.3, "end": start + index * 0.3 + 0.25}
            for index, part in enumerate(text.split())
        ]
        utterances.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "confidence": confidence,
                "speaker": "Speaker 1",
                "words": words,
            }
        )
        start += 12.0
    return {
        "recording_id": recording_id,
        "duration": duration,
        "utterances": utterances,
        "silences": [],
        "likely_music": [],
    }
