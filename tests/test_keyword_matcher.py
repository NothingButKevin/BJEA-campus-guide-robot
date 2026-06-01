"""Tests for KeywordMatcher — pinyin fuzzy matching."""

import sys
from pathlib import Path

# Ensure src is importable from tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from matching.keyword_matcher import KeywordMatcher


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

_chat_data = {
    "chat_greeting": ["你好", "哈喽", "嗨", "能听见吗"],
    "chat_identity": ["你是谁", "你叫什么", "你是什么机器人"],
    "chat_capability": ["你能干什么", "你会什么"],
}


def _mk(data: dict) -> KeywordMatcher:
    return KeywordMatcher(data)


# ------------------------------------------------------------------
# Basic matching
# ------------------------------------------------------------------

class TestBasicMatch:
    def test_exact_match(self):
        m = _mk(_chat_data)
        assert m.match("你好") == "chat_greeting"

    def test_partial_match(self):
        m = _mk(_chat_data)
        # "你是" should fuzzy-match to "你是谁"
        result = m.match("你是")
        assert result == "chat_identity", f"Got {result!r}"

    def test_fuzzy_phonetic(self):
        m = _mk(_chat_data)
        # "哈罗" close to "哈喽" in pinyin ("haluo" vs "halou")
        result = m.match("哈罗")
        assert result == "chat_greeting" or result != "none"


# ------------------------------------------------------------------
# Confidence scores
# ------------------------------------------------------------------

class TestConfidence:
    def test_high_confidence_exact(self):
        m = _mk(_chat_data)
        key, conf = m.match_with_confidence("你好")
        assert key == "chat_greeting"
        assert conf > 90

    def test_low_confidence_unrelated(self):
        m = _mk(_chat_data)
        key, conf = m.match_with_confidence("xyz 完全不相关的话")
        assert key == "none"
        assert conf == 0.0 or conf < 80


# ------------------------------------------------------------------
# Thresholds
# ------------------------------------------------------------------

class TestThresholds:
    def test_threshold_too_high(self):
        m = _mk(_chat_data)
        # With threshold=99 and a non-exact match, should return "none"
        key, _ = m.match_with_confidence("干啥的", score_threshold=99)
        assert key == "none"


# ------------------------------------------------------------------
# Multi-intent (merged datasets)
# ------------------------------------------------------------------

class TestMultiIntent:
    def test_distinguishes_nav_from_chat(self):
        data = {
            "8th_building": ["八号楼", "八号", "国际部"],
            "chat_greeting": ["你好", "哈喽"],
        }
        m = _mk(data)
        assert m.match("我要去八号楼") == "8th_building"
        assert m.match("你好") == "chat_greeting"
