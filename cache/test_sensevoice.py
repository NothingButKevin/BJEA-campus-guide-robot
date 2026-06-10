"""测试 SenseVoice Small ASR"""
import sys
sys.path.insert(0, 'src')

from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
import yaml

# 加载模型
print('加载 SenseVoice Small...')
model = AutoModel(
    model='iic/SenseVoiceSmall',
    disable_update=True,
)
print('模型就绪')

# 先用现有的 cache/output.wav 测试
import os
wav_path = 'cache/output.wav'
if os.path.exists(wav_path):
    print(f'测试文件: {wav_path}')
    res = model.generate(input=wav_path, language='zh', use_itn=False)
    if res:
        text = res[0]['text']
        clean = rich_transcription_postprocess(text)
        print(f'原始: {text}')
        print(f'清理: {clean}')
else:
    print(f'{wav_path} 不存在，先录音...')
    from speech.recognizer import SpeechRecognizer
    with open('config.yaml') as f:
        cfg = yaml.safe_load(f)
    rec = SpeechRecognizer(cfg['asr'])
    rec._record_until_silence()
    print('录音完成，转写中...')
    res = model.generate(input=cfg['asr']['output_path'], language='zh', use_itn=False)
    if res:
        text = res[0]['text']
        clean = rich_transcription_postprocess(text)
        print(f'原始: {text}')
        print(f'清理: {clean}')
