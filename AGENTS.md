# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指南。

## 项目概览

北京中学国际部（BJEA）校园导览机器人，运行在 **树莓派 5 + Pi OS** 上。全中文语音交互。TTS 使用微软 Edge-TTS 免费接口，其余模块全本地运行。

## 开发工作流

本项目采用 **"Mac 开发，树莓派测试"** 模式。

MacBook 是主要开发环境，负责代码编写、架构设计、文档维护、Git 管理和 AI 辅助开发。树莓派是实际运行环境，负责验证代码在真实硬件上的表现，包括电机、MPU6050、麦克风、扬声器、GPIO、PWM、I2C 等硬件功能。

### 标准流程

1. 在 MacBook 上使用 VS Code 编写代码。
2. 使用 Claude Code 进行代码实现、重构和问题分析。
3. 完成功能后提交到 Git 仓库并推送到 GitHub。
4. SSH 登录树莓派。
5. 从 GitHub 拉取最新代码。
6. 在树莓派上运行程序并进行实际测试。
7. 记录测试结果、日志和发现的问题。
8. 回到 MacBook 修改代码并继续迭代。

### 连接树莓派

```bash
ssh bjea@10.103.12.222      # 密码见实际配置（DHCP 动态 IP，以实际为准）
```

树莓派使用 DHCP 获取 IP（非静态），如 IP 变化可通过以下方式重新定位：

```bash
nmap -p 22 --open 10.103.0.0/20 -T5 | grep -E '^Nmap scan|22/tcp open'
# 然后逐台尝试 SSH，确认 hostname 为 BJEA-CampusGuide-Robot
```

### 原则

- **树莓派不是主要开发机**。树莓派用于运行和验证，MacBook 用于开发和设计。
- 不要把 Claude Code 或其他重型开发工具装在树莓派上。
- 硬件相关代码（GPIO、PWM、I2C）只能在树莓派上测试，桌面端使用 Mock 实现。

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
  ├─recognizer  ├─keyword_matcher  ├─navigator  ├─motor (抽象接口+lgpio+Mock)
  └─synthesizer └─(RapidFuzz+拼音)  └─(定距/定角) ├─sensors (MPU6050+编码器)
                              │                   └─audio_player
                         llm/fallback
                    (Qwen2.5-0.5B 兜底)
```

- **关键字匹配是主路径**（<10ms），LLM 仅在匹配置信度低于阈值时兜底
- **导航期间卸载语音/LLM 模型**释放内存，到站后重新加载
- 桌面端自动使用 Mock 硬件（不依赖 gpiozero）

## 模块职责

| 模块 | 功能 |
|------|------|
| `speech/recognizer.py` | 静音检测录音 + FunASR SenseVoice Small 转写中文 |
| `speech/synthesizer.py` | Edge-TTS 微软免费中文 TTS（subprocess 调 CLI）|
| `matching/keyword_matcher.py` | 拼音归一化 + RapidFuzz 模糊匹配，支持多意图集，返回置信度 |
| `llm/fallback.py` | Qwen2.5-0.5B GGUF，llama-cpp-python 推理，`release()`/`reload()` 支持动态生命周期 |
| `hardware/motor.py` | `MotorController` 抽象接口 + `RPiMotorController`（lgpio 直驱 50Hz PWM）+ `MockMotorController`（日志），工厂自动选，需 `sudo` |
| `hardware/sensors.py` | MPU6050 航向 + 编码器里程计，桌面端返回零值自动降级 |
| `hardware/audio_player.py` | TTS 合成播报，greeting / confirm / arrived 语音流程 |
| `navigation/navigator.py` | `go_straight(距离)` `turn(角度)` 闭环运动原语 + `follow_route()` 路径执行 |
| `robot.py` | 8 状态的状态机：IDLE → LISTENING → MATCHING → CONFIRMING/CHATTING → NAVIGATING → ARRIVED |

## 配置文件

- `config.yaml` — 所有可调参数（模型路径、GPIO 引脚、传感器标定、匹配阈值）
- `resources/demoActions.json` — 移动指令关键词
- `resources/locationKeywords.json` — 地点关键词 + 确认短语
- `resources/chatIntents.json` — 闲聊意图（你是谁/你能干什么/再见…）
- `resources/routes.yaml` — 导航路径定义（距离+转角序列）
- `pyproject.toml` — 项目元数据 + pytest 配置

## 硬件接线

底盘采用差分混控驱动板，两个 GPIO 引脚通过 50Hz PWM 舵机信号控制：

| GPIO（BCM） | 功能 | 7.5% 占空比 | >7.5% | <7.5% |
|------------|------|------------|-------|-------|
| 27 | 油门 | 停止 | 双轮前进 | 双轮后退 |
| 17 | 转向 | 直行 | 右转（左前右后） | 左转（左后右前） |

驱动板内置混控：**左轮 = 油门 + 转向，右轮 = 油门 - 转向**。

- 必须连接 GND（物理脚 9 或 14）到驱动板 GND，否则信号无参考电压
- 驱动板需电池供电，GPIO 信号仅提供控制逻辑
- Pi 5 使用 `lgpio` 库直驱，见下方「GPIO 技术选型」。

## GPIO 技术选型

本项目**不使用 gpiozero**。选择 lgpio 直驱的原因是经完整工程排查得出的。

### 排查过程

1. **现象**：gpiozero `Servo` 类输出后左轮反转、右轮不动，多次复现。

2. **排除电池**：电池重新上电后 lgpio 直调工作正常，排除供电问题。

3. **排除 Pi 5 兼容性**：确认 `GPIOZERO_PIN_FACTORY=lgpio` 生效，`Device.pin_factory` 确认为 `LGPIOFactory`。

4. **定位根因**：阅读 `/usr/lib/python3/dist-packages/gpiozero/pins/lgpio.py` 源码第 162 行：

   ```python
   self._pwm = (freq, int(value * 100))
   ```

   `int()` 截断了占空比的小数部分。50Hz 舵机中位 7.5% → `int(7.5)` = 7.0%（信号偏移 0.5%），导致中立位变为倒车信号。**只有整数值占空比（5%、8%、10% 等）不受影响**，但舵机中位必须是 7.5%，无法绕过。

5. **交叉验证**：lgpio.tx_pwm 接受 float 占空比，直接传入 7.5 / 10.0 / 5.0 完全正常，双轮前后左右全部正确。

### 结论

gpiozero 的 lgpio 后端封装层存在 `int()` 截断 bug（截至 2026-06-04 未修复），导致 50Hz 舵机信号无法精确输出非整数占空比。项目直接用 lgpio，经实车验证稳定可靠。

### lgpio 使用要点

- 导入：`import lgpio`
- 打开芯片：`h = lgpio.gpiochip_open(0)`（Pi 5 40pin 排针走 chip 0）
- 占板输出：`lgpio.gpio_claim_output(h, pin)`
- 发送 PWM：`lgpio.tx_pwm(h, pin, freq_hz, duty_pct)` — duty 为 float，0–100
- 释放：`lgpio.gpiochip_close(h)`
- 需要 root 权限

## 平台注意事项

- `lgpio` 是项目唯一的 GPIO 底层库。桌面端（Mac）因无 `/dev/gpiochip*` 设备，`create_motor()` 工厂函数自动降级为 `MockMotorController`。程序需 `sudo` 运行才能访问 GPIO 硬件。
- 所有语音输入输出为中文（普通话）
- 关键词匹配使用拼音归一化处理口音和识别误差
