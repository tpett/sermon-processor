from sermon.store import Artifact, Block, Recording, Segment


def holds(store, recording):
    return {
        "state": store.loads(Recording, recording.recording_id).state,
        "artifacts": {
            item.path: store.resolves(item).read_bytes()
            for item in store.lists(Artifact, recording_id=recording.recording_id)
        },
        "blocks": store.lists(Block, recording_id=recording.recording_id),
        "segments": store.lists(Segment, recording_id=recording.recording_id),
    }
