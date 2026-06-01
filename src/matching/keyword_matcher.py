"""Fuzzy Chinese keyword matching via pinyin normalisation + RapidFuzz.

Supports multiple intent sets (navigation, chat, control) merged into one
matcher instance.  Returns the matched key and a confidence score so
callers can decide whether to use LLM fallback.
"""

import json
import logging
from typing import Optional

from rapidfuzz import fuzz, process
from xpinyin import Pinyin

logger = logging.getLogger(__name__)

_pinyin = Pinyin()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_pinyin(text: str) -> str:
    """Strip tones and separators, keep only pinyin letters."""
    return "".join(_pinyin.get_pinyin(text, "").split("-"))


def _prepare_pinyin_index(data: dict) -> tuple[list[str], list[str]]:
    """Flatten {intent: [variants]} into (flat_pinyin_list, key_map)."""
    flat_list: list[str] = []
    key_map: list[str] = []
    for key, values in data.items():
        for val in values:
            flat_list.append(_to_pinyin(val))
            key_map.append(key)
    return flat_list, key_map


# ------------------------------------------------------------------
# Matcher
# ------------------------------------------------------------------

class KeywordMatcher:
    """Fuzzy-match Chinese user input against keyword intent sets.

    Typical usage::

        matcher = KeywordMatcher({**location_data, **chat_data})
        result, confidence = matcher.match_with_confidence("我要去八号楼")
        # ("8th_building", 96)
    """

    def __init__(self, data: dict):
        """
        Args:
            data: {intent_key: [variant_str, ...]} dictionary.
        """
        self._data = data
        self._flat_list, self._key_map = _prepare_pinyin_index(data)

    # -- factory -------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict) -> "KeywordMatcher":
        """Build a matcher by loading JSON files listed in *config*."""
        data: dict = {}
        data.update(load_json(config["actions_file"]))
        data.update(load_json(config["locations_file"]))
        chat_path = config.get("chat_intents_file", "")
        if chat_path:
            data.update(load_json(chat_path))
        return cls(data)

    # -- matching ------------------------------------------------------

    def match(self, user_input: str, score_threshold: int = 80, score_gap: int = 10) -> str:
        """Return the best-match key or ``"none"``."""
        result, _ = self.match_with_confidence(user_input, score_threshold, score_gap)
        return result

    def match_with_confidence(
        self,
        user_input: str,
        score_threshold: int = 80,
        score_gap: int = 10,
    ) -> tuple[str, float]:
        """Return ``(key | "none", confidence_score)``."""
        if not user_input.strip():
            return "none", 0.0

        user_pinyin = _to_pinyin(user_input)

        # batch-compare against every pinyin variant
        scores = process.cdist(
            [user_pinyin], self._flat_list, scorer=fuzz.partial_ratio, workers=1
        )[0]

        # aggregate to key-level (keep the best score per key)
        score_by_key: dict[str, float] = {}
        for i, score in enumerate(scores):
            key = self._key_map[i]
            if key not in score_by_key or score > score_by_key[key]:
                score_by_key[key] = score

        sorted_scores = sorted(score_by_key.items(), key=lambda x: x[1], reverse=True)

        if not sorted_scores or sorted_scores[0][1] < score_threshold:
            return "none", 0.0

        # ambiguous match?
        if len(sorted_scores) > 1 and sorted_scores[0][1] - sorted_scores[1][1] < score_gap:
            return "none", sorted_scores[0][1]

        logger.debug("Matched '%s' -> %s (%.1f)", user_input, sorted_scores[0][0], sorted_scores[0][1])
        return sorted_scores[0][0], sorted_scores[0][1]


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    matcher = KeywordMatcher.from_config(
        {
            "actions_file": "resources/demoActions.json",
            "locations_file": "resources/locationKeywords.json",
            "chat_intents_file": "resources/chatIntents.json",
        }
    )
    while True:
        try:
            user_input = input("请输入关键词（Ctrl+C 退出）: ")
        except (KeyboardInterrupt, EOFError):
            break
        key, conf = matcher.match_with_confidence(user_input)
        if key == "none":
            print(f"  无明确匹配（最高置信度 {conf:.0f}）")
        else:
            print(f"  匹配: {key} ({conf:.0f})")
