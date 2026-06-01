"""测试 Robot 状态机（Mock 硬件）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ------------------------------------------------------------------
# 不依赖真硬件的纯逻辑测试：
# 验证状态枚举定义和闲聊回复表是否完整。
# ------------------------------------------------------------------

from robot import State, _CHAT_RESPONSES


class TestStateEnum:
    def test_all_states_have_unique_values(self):
        """所有状态值唯一"""
        values = [s.value for s in State]
        assert len(values) == len(set(values))

    def test_expected_states_present(self):
        """预期状态全部存在"""
        names = {s.name for s in State}
        for expected in [
            "IDLE", "LISTENING", "MATCHING", "CONFIRMING",
            "CHATTING", "NAVIGATING", "ARRIVED", "SHUTDOWN",
        ]:
            assert expected in names


class TestChatResponses:
    def test_all_chat_keys_have_response(self):
        """每个闲聊意图都有对应的 TTS 回复文本"""
        for key in [
            "chat_greeting",
            "chat_identity",
            "chat_capability",
            "chat_nav_status",
            "chat_farewell",
        ]:
            assert key in _CHAT_RESPONSES, f"缺少回复: {key}"
            assert isinstance(_CHAT_RESPONSES[key], str)
            assert len(_CHAT_RESPONSES[key]) > 0
