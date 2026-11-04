"""Independent checks; run outside the agent's writable worktree."""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("candidate", Path(sys.argv[1]) / "midi_state.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

for channel in (0, 1, 15):
    active = {(channel, 60), ((channel + 1) % 16, 60), (channel, 61)}
    result = module.apply_event(active, "note_on", 60, velocity=0, channel=channel)
    assert result is active
    assert active == {((channel + 1) % 16, 60), (channel, 61)}, "zero velocity must release only its note"
    module.apply_event(active, "note_on", 60, velocity=127, channel=channel)
    assert (channel, 60) in active
    module.apply_event(active, "note_off", 60, velocity=64, channel=channel)
    assert (channel, 60) not in active
    before = active.copy()
    module.apply_event(active, "control_change", 60, velocity=0, channel=channel)
    assert active == before
    module.apply_event(active, "note_off", 99, channel=channel)
    assert active == before
print("MIDI state checks passed")
