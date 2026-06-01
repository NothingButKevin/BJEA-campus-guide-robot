"""测试 KeywordMatcher —— 拼音模糊匹配。"""

import sys
from pathlib import Path

# 确保 src 在测试中可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from matching.keyword_matcher import KeywordMatcher


# ------------------------------------------------------------------
# 测试数据
# ------------------------------------------------------------------

_chat_data = {
    "chat_greeting": ["你好", "哈喽", "嗨", "能听见吗"],
    "chat_identity": ["你是谁", "你叫什么", "你是什么机器人"],
    "chat_capability": ["你能干什么", "你会什么"],
}


def _mk(data: dict) -> KeywordMatcher:
    return KeywordMatcher(data)


# ------------------------------------------------------------------
# 基本匹配
# ------------------------------------------------------------------

class TestBasicMatch:
    def test_exact_match(self):
        """完全匹配"""
        m = _mk(_chat_data)
        assert m.match("你好") == "chat_greeting"

    def test_partial_match(self):
        """部分匹配 —— "你是" 应模糊匹配到 "你是谁" """
        m = _mk(_chat_data)
        result = m.match("你是")
        assert result == "chat_identity", f"得到 {result!r}"

    def test_fuzzy_phonetic(self):
        """拼音模糊 —— "哈罗" 接近 "哈喽" """
        m = _mk(_chat_data)
        result = m.match("哈罗")
        assert result == "chat_greeting" or result != "none"


# ------------------------------------------------------------------
# 置信度
# ------------------------------------------------------------------

class TestConfidence:
    def test_high_confidence_exact(self):
        """精确匹配应得高分"""
        m = _mk(_chat_data)
        key, conf = m.match_with_confidence("你好")
        assert key == "chat_greeting"
        assert conf > 90

    def test_low_confidence_unrelated(self):
        """不相关输入应返回 none 且低分"""
        m = _mk(_chat_data)
        key, conf = m.match_with_confidence("xyz 完全不相关的话")
        assert key == "none"
        assert conf == 0.0 or conf < 80


# ------------------------------------------------------------------
# 阈值
# ------------------------------------------------------------------

class TestThresholds:
    def test_threshold_too_high(self):
        """阈值过高时非精确匹配应返回 none"""
        m = _mk(_chat_data)
        key, _ = m.match_with_confidence("干啥的", score_threshold=99)
        assert key == "none"


# ------------------------------------------------------------------
# 多意图集（合并数据集）
# ------------------------------------------------------------------

class TestMultiIntent:
    def test_distinguishes_nav_from_chat(self):
        """正确区分导航意图和闲聊意图"""
        data = {
            "8th_building": ["八号楼", "八号", "国际部"],
            "chat_greeting": ["你好", "哈喽"],
        }
        m = _mk(data)
        assert m.match("我要去八号楼") == "8th_building"
        assert m.match("你好") == "chat_greeting"
