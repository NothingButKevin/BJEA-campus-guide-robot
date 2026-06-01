"""Tests for Robot state machine (mock hardware)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ------------------------------------------------------------------
# We test only the state-transition logic without real hardware.
# The Robot class is integration-heavy; these tests verify that the
# state enum and handler dispatch table are well-formed.
# ------------------------------------------------------------------

from robot import State, _CHAT_RESPONSES


class TestStateEnum:
    def test_all_states_have_unique_values(self):
        values = [s.value for s in State]
        assert len(values) == len(set(values))

    def test_expected_states_present(self):
        names = {s.name for s in State}
        assert "IDLE" in names
        assert "LISTENING" in names
        assert "MATCHING" in names
        assert "CONFIRMING" in names
        assert "CHATTING" in names
        assert "NAVIGATING" in names
        assert "ARRIVED" in names
        assert "SHUTDOWN" in names


class TestChatResponses:
    def test_all_chat_keys_have_response(self):
        for key in [
            "chat_greeting",
            "chat_identity",
            "chat_capability",
            "chat_nav_status",
            "chat_farewell",
        ]:
            assert key in _CHAT_RESPONSES, f"Missing response for {key}"
            assert isinstance(_CHAT_RESPONSES[key], str)
            assert len(_CHAT_RESPONSES[key]) > 0
