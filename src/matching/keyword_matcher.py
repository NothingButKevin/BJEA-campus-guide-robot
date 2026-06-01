"""中文关键词模糊匹配 —— 通过拼音归一化 + RapidFuzz 实现。

支持多意图集（导航、闲聊、控制）合并到一个匹配器实例中。
返回匹配键值和置信度，供调用方决定是否启用 LLM 兜底。
"""

import json
import logging
from typing import Optional

from rapidfuzz import fuzz, process
from xpinyin import Pinyin

logger = logging.getLogger(__name__)

_pinyin = Pinyin()


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

def load_json(path: str) -> dict:
    """从文件加载 JSON 数据。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_pinyin(text: str) -> str:
    """去除音调和分隔符，只保留拼音字母。"""
    return "".join(_pinyin.get_pinyin(text, "").split("-"))


def _prepare_pinyin_index(data: dict) -> tuple[list[str], list[str]]:
    """将 {意图: [变体列表]} 展平为 (拼音列表, 键映射表)。"""
    flat_list: list[str] = []
    key_map: list[str] = []
    for key, values in data.items():
        for val in values:
            flat_list.append(_to_pinyin(val))
            key_map.append(key)
    return flat_list, key_map


# ------------------------------------------------------------------
# 匹配器
# ------------------------------------------------------------------

class KeywordMatcher:
    """将中文用户输入与关键词意图集进行模糊匹配。

    用法示例::

        matcher = KeywordMatcher({**location_data, **chat_data})
        result, confidence = matcher.match_with_confidence("我要去八号楼")
        # ("8th_building", 96)
    """

    def __init__(self, data: dict):
        """
        参数:
            data: {意图键: [变体字符串列表]} 字典。
        """
        self._data = data
        self._flat_list, self._key_map = _prepare_pinyin_index(data)

    # -- 工厂方法 -------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict) -> "KeywordMatcher":
        """根据配置文件加载 JSON 并构造匹配器。"""
        data: dict = {}
        data.update(load_json(config["actions_file"]))
        data.update(load_json(config["locations_file"]))
        chat_path = config.get("chat_intents_file", "")
        if chat_path:
            data.update(load_json(chat_path))
        return cls(data)

    # -- 匹配 ------------------------------------------------------------

    def match(self, user_input: str, score_threshold: int = 80, score_gap: int = 10) -> str:
        """返回最佳匹配的键名，无匹配时返回 ``"none"``。"""
        result, _ = self.match_with_confidence(user_input, score_threshold, score_gap)
        return result

    def match_with_confidence(
        self,
        user_input: str,
        score_threshold: int = 80,
        score_gap: int = 10,
    ) -> tuple[str, float]:
        """返回 ``(key | "none", 置信度分数)``。"""
        if not user_input.strip():
            return "none", 0.0

        user_pinyin = _to_pinyin(user_input)

        # 与所有拼音变体批量比对
        scores = process.cdist(
            [user_pinyin], self._flat_list, scorer=fuzz.partial_ratio, workers=1
        )[0]

        # 按意图键聚合，每个键保留最高分
        score_by_key: dict[str, float] = {}
        for i, score in enumerate(scores):
            key = self._key_map[i]
            if key not in score_by_key or score > score_by_key[key]:
                score_by_key[key] = score

        sorted_scores = sorted(score_by_key.items(), key=lambda x: x[1], reverse=True)

        if not sorted_scores or sorted_scores[0][1] < score_threshold:
            return "none", 0.0

        # 结果是否模糊（第一名和第二名差距太小）
        if len(sorted_scores) > 1 and sorted_scores[0][1] - sorted_scores[1][1] < score_gap:
            return "none", sorted_scores[0][1]

        logger.debug("匹配 '%s' -> %s (%.1f)", user_input, sorted_scores[0][0], sorted_scores[0][1])
        return sorted_scores[0][0], sorted_scores[0][1]


# ------------------------------------------------------------------
# 独立测试入口
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
