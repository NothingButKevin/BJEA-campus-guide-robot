# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指南。

## 项目概览

北京中学国际部（BJEA）校园导览机器人，运行在 **树莓派 5 + Pi OS** 上。全中文语音交互，全本地运行（零 API 依赖）。

## 常用命令

```bash
pip install -r requirements.txt          # 安装依赖
pip install -e ".[test]"                 # 安装测试依赖

python main.py                           # 完整导航工作流
python main.py --demo                    # 语音控制行进 demo
python main.py --config config.yaml      # 指定配置文件

pytest tests/ -v                         # 运行全部测试

# 单独测试各模块
python src/speech/recognizer.py          # 语音识别
python src/speech/synthesizer.py         # TTS 合成
python src/matching/keyword_matcher.py   # 关键词匹配
python src/hardware/audio_player.py      # 预录音频播放
```

## 架构

```
main.py ──▶ robot.py（状态机 + 模型生命周期管理）
               │
     ┌─────────┼──────────┬──────────────┐
     ▼         ▼          ▼              ▼
  speech/   matching/  navigation/   hardware/
  ├─recognizer  ├─keyword_matcher  ├─navigator  ├─motor (抽象接口+RPi+Mock)
  └─synthesizer └─(RapidFuzz+拼音)  └─(定距/定角) ├─sensors (MPU6050+编码器)
                              │                   └─audio_player
                         llm/fallback
                    (Qwen2.5-0.5B 兜底)
```

- **关键字匹配是主路径**（<10ms），LLM 仅在匹配置信度低于阈值时兜底
- **导航期间卸载语音/LLM 模型**释放内存，到站后重新加载
- 桌面端自动使用 Mock 硬件（不依赖 RPi.GPIO）

## 模块职责

| 模块 | 功能 |
|------|------|
| `speech/recognizer.py` | 静音检测录音 + Whisper.cpp 转写中文 |
| `speech/synthesizer.py` | Piper ONNX 中文 TTS，在内存中生成 WAV 并播放 |
| `matching/keyword_matcher.py` | 拼音归一化 + RapidFuzz 模糊匹配，支持多意图集，返回置信度 |
| `llm/fallback.py` | Qwen2.5-0.5B GGUF，llama-cpp-python 推理，`release()`/`reload()` 支持动态生命周期 |
| `hardware/motor.py` | `MotorController` 抽象接口 + `RPiMotorController`（PWM）+ `MockMotorController`（日志），工厂自动选 |
| `hardware/sensors.py` | MPU6050 航向 + 编码器里程计，桌面端返回零值自动降级 |
| `hardware/audio_player.py` | 播放预录制 WAV（playsound），greeting / confirm / final 流程 |
| `navigation/navigator.py` | `go_straight(距离)` `turn(角度)` 闭环运动原语 + `follow_route()` 路径执行 |
| `robot.py` | 8 状态的状态机：IDLE → LISTENING → MATCHING → CONFIRMING/CHATTING → NAVIGATING → ARRIVED |

## 配置文件

- `config.yaml` — 所有可调参数（模型路径、GPIO 引脚、传感器标定、匹配阈值）
- `resources/demoActions.json` — 移动指令关键词
- `resources/locationKeywords.json` — 地点关键词 + 确认短语
- `resources/chatIntents.json` — 闲聊意图（你是谁/你能干什么/再见…）
- `resources/routes.yaml` — 导航路径定义（距离+转角序列）
- `pyproject.toml` — 项目元数据 + pytest 配置

## 平台注意事项

- `RPi.GPIO` 仅在树莓派上可用，桌面端自动降级为 Mock 实现
- 所有语音输入输出为中文（普通话）
- 关键词匹配使用拼音归一化处理口音和识别误差
