import json
from rapidfuzz import process, fuzz
from xpinyin import Pinyin
import os

# 初始化拼音转换器
p = Pinyin()

# === 1. 数据加载与预处理 ===
def load_data(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def prepare_pinyin_data(data):
    pinyin_data = {}
    for key, values in data.items():
        pinyin_values = ["".join(p.get_pinyin(val, "").split("-")) for val in values]
        pinyin_data[key] = pinyin_values
    return pinyin_data

# === 2. 全量拼音词表 & 映射关系构建（用于批量匹配） ===
def build_flat_index(pinyin_data):
    flat_list = []
    key_map = []
    for key, values in pinyin_data.items():
        for val in values:
            flat_list.append(val)
            key_map.append(key)
    return flat_list, key_map

# === 3. 匹配函数（使用快速批量相似度计算） ===
def find_best_match(user_input, flat_pinyin_list, key_map, score_threshold=80, score_gap=10):
    user_pinyin = "".join(p.get_pinyin(user_input, "").split("-"))

    # 批量计算所有相似度
    scores = process.cdist([user_pinyin], flat_pinyin_list, scorer=fuzz.partial_ratio, workers=1)[0]

    # 聚合到 key 层面，保留每个 key 的最高分
    score_by_key = {}
    for i, score in enumerate(scores):
        key = key_map[i]
        if key not in score_by_key or score > score_by_key[key]:
            score_by_key[key] = score

    # 排序并筛选
    sorted_scores = sorted(score_by_key.items(), key=lambda x: x[1], reverse=True)

    if sorted_scores and sorted_scores[0][1] >= score_threshold:
        if len(sorted_scores) > 1 and sorted_scores[0][1] - sorted_scores[1][1] < score_gap:
            return "none"
        return sorted_scores[0][0]
    
    return "none"

# === 4. 主接口 ===
class KeywordMatcher:
    def __init__(self, data_file_path):
        self.data_file_path = data_file_path
        self.data = load_data(self.data_file_path)
        self.pinyin_data = prepare_pinyin_data(self.data)
        self.flat_list, self.key_map = build_flat_index(self.pinyin_data)

    def match(self, user_input, score_threshold=80, score_gap=10):
        return find_best_match(user_input, self.flat_list, self.key_map, score_threshold, score_gap)

# === 5. 命令行测试入口 ===
if __name__ == "__main__":
    matcher = KeywordMatcher("resources/locationKeywords.json")
    while True:
        user_input = input("请输入地点关键词：")
        result = matcher.match(user_input)
        if result == "none":
            print("没有匹配结果，请重新输入")
        else:
            print(f"匹配结果：{result}")