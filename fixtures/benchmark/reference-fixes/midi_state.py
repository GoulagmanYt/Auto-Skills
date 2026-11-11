def apply_event(active, kind, note, velocity=64, channel=0):
    """Update the set of active (channel, note) identities and return it."""
    identity = (channel, note)
    if kind == "note_on" and velocity > 0:
        active.add(identity)
    elif kind == "note_off" or (kind == "note_on" and velocity == 0):
        active.discard(identity)
    return active
