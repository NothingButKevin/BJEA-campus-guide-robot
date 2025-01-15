import json
from rapidfuzz import process, fuzz
from xpinyin import Pinyin

# 创建拼音转换器
p = Pinyin()

# 从 JSON 文件读取数据
def load_data(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

# 将 JSON 数据中的每个值都转换为拼音
def prepare_data(data):
    pinyin_data = {}
    for key, values in data.items():
        # 将每个地点的所有别名转换为拼音
        pinyin_values = ["".join(p.get_pinyin(val, "").split("-")) for val in values]
        pinyin_data[key] = pinyin_values
    return pinyin_data

# 核心匹配逻辑
def find_location(user_input, pinyin_data, score_threshold=80, score_gap=10):
    # 将用户输入转换为拼音
    user_pinyin = "".join(p.get_pinyin(user_input, "").split("-"))
    # 存储每个地点的最高匹配分数
    scores = []
    
    for key, pinyin_values in pinyin_data.items():
        # 获取用户输入与当前地点拼音别名的最高相似度
        best_match = process.extractOne(user_pinyin, pinyin_values, scorer=fuzz.partial_ratio)
        if best_match:  # 确保有匹配结果
            scores.append((key, best_match[1]))
    
    # 按分数降序排序
    scores.sort(key=lambda x: x[1], reverse=True)
    
    if scores and scores[0][1] >= score_threshold:
        # 检查最高分与次高分的差距是否足够大
        if len(scores) > 1 and scores[0][1] - scores[1][1] < score_gap:
            return "none"
        return scores[0][0]
    
    return "none"

# 主程序入口
def keywords_mapping(user_input, data_file_path="resources/locationKeywords.json", score_threshold=80, score_gap=10):
    # 加载数据
    data = load_data(data_file_path)
    # 准备数据
    pinyin_data = prepare_data(data)
    # 匹配地点
    location = find_location(user_input, pinyin_data, score_threshold, score_gap)
    return location

if __name__ == "__main__":
    # 测试用例
    print(keywords_mapping(input(), "resources/locationKeywords.json"))