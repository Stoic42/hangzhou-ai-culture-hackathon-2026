"""sherpa-onnx 本地 ASR 适配器（默认针对 SenseVoice-small 模型目录）。

经 ``SERVER_ASR_PROVIDER=local`` 装配，凭证/模型只走环境变量与本地目录：

- ASR_MODEL_DIR：SenseVoice-small 模型目录（含 tokens.txt 与 model.int8.onnx
  或 model.onnx）；缺失或文件不全时装配仍成功，transcribe 抛
  GenerationUnavailable（契约 503 generation_unavailable）。
- sherpa-onnx 为可选依赖：未安装时同样装配成功，transcribe 抛
  GenerationUnavailable（提示未安装）。

识别器惰性加载（首次 transcribe 时初始化，双重检查锁），避免拖慢
启动与测试；模型本体不入库。

线程安全：sherpa-onnx 的 OfflineRecognizer 是否可多线程共享推理未见官方
明确保证，这里串行化 decode（展会并发低，正确性优先）。

单测的假 sherpa_onnx 模块形状以本适配器的调用代码为准（sys.modules 注入）；
与真实 sherpa-onnx API 的兼容性由 skipif 真机集成用例（配置 ASR_MODEL_DIR
后启用）保障。
"""

from __future__ import annotations

import io
import re
import sys
import threading
import wave
from array import array
from pathlib import Path

from ..config import Settings, get_settings
from .base import GenerationUnavailable, SpeechUnrecognized

_EXPECTED_RATE = 16000  # 契约 4.1：设备侧固定 16kHz 单声道 16bit
_NUM_THREADS = 2

# SenseVoice 输出会带元信息标签，如 "<|zh|><|HAPPY|><|withitn|>文本"
_META_TAG_RE = re.compile(r"<\|[^|]*\|>")


def _strip_meta_tags(text: str) -> str:
    """剥掉 SenseVoice 的 <|zh|> / <|withitn|> 等元信息标签。"""
    return _META_TAG_RE.sub("", text).strip()


def _resample_linear(samples: array, src_rate: int, dst_rate: int) -> array:
    """线性插值重采样（stdlib 实现，不额外引 numpy）。

    契约固定设备采样率为 16kHz，路由层只校验 WAV 合法性、未校验采样率；
    这里对非 16kHz 输入做最简重采样兜底，保证识别器始终收到 16kHz 数据。
    """
    if src_rate == dst_rate or not samples:
        return samples
    dst_len = max(1, round(len(samples) * dst_rate / src_rate))
    ratio = src_rate / dst_rate
    out = array("f")
    for i in range(dst_len):
        pos = i * ratio
        lo = int(pos)
        hi = min(lo + 1, len(samples) - 1)
        frac = pos - lo
        out.append(samples[lo] * (1.0 - frac) + samples[hi] * frac)
    return out


def _wav_to_float32(audio: bytes) -> array:
    """WAV 字节 → float32 单声道 PCM（[-1, 1]）；异常输入抛 SpeechUnrecognized。

    路由层已校验 WAV 合法性与时长，这里只处理解码本身；
    非 16bit 或非单声道的 WAV 属于未声明的客户端行为，不做静默兼容。
    """
    try:
        with wave.open(io.BytesIO(audio), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
    except wave.Error as exc:
        raise SpeechUnrecognized("音频无法按 WAV 解码") from exc
    if sampwidth != 2:
        raise SpeechUnrecognized(f"仅支持 16bit PCM，实际 {sampwidth * 8}bit")
    if channels != 1:
        raise SpeechUnrecognized(f"仅支持单声道，实际 {channels} 声道")
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        # WAV 帧按小端存放；大端平台需交换字节序还原有符号采样
        samples.byteswap()
    floats = array("f", (s / 32768.0 for s in samples))
    return _resample_linear(floats, rate, _EXPECTED_RATE)


class SherpaLocalASR:
    """sherpa-onnx 本地识别器（构造注入 Settings，模型惰性加载）。"""

    def __init__(self, settings: Settings | None = None,
                 model_dir: str | None = None) -> None:
        if settings is None:
            settings = get_settings()
        # model_dir 显式传入优先（测试便利），否则取 ASR_MODEL_DIR
        self._model_dir = (model_dir if model_dir is not None
                           else settings.asr_model_dir)
        self._recognizer = None
        self._init_lock = threading.Lock()
        self._decode_lock = threading.Lock()  # decode 串行化，见模块注释

    # ------------------------------------------------------------------
    # 惰性初始化（双重检查锁，参考 openai_llm._get_client）
    # ------------------------------------------------------------------

    def _resolve_model_files(self) -> tuple[Path, Path]:
        """校验模型目录完整性，返回 (model_onnx, tokens.txt)。"""
        if not self._model_dir:
            raise GenerationUnavailable("本地模型未配置")
        model_dir = Path(self._model_dir)
        model = model_dir / "model.int8.onnx"
        if not model.is_file():
            model = model_dir / "model.onnx"
        tokens = model_dir / "tokens.txt"
        if not tokens.is_file() or not model.is_file():
            raise GenerationUnavailable("本地模型未配置")
        return model, tokens

    def _get_recognizer(self):
        recognizer = self._recognizer
        if recognizer is None:
            with self._init_lock:
                if self._recognizer is None:
                    self._recognizer = self._build_recognizer()
                recognizer = self._recognizer
        return recognizer

    def _build_recognizer(self):
        """装配期不 import sherpa-onnx（可选依赖），首次识别时才加载。

        API 形态（sherpa-onnx 2.x）：OfflineRecognizer.from_sense_voice(
            model=..., tokens=..., num_threads=..., use_itn=True)
        """
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise GenerationUnavailable("未安装 sherpa-onnx") from exc
        model, tokens = self._resolve_model_files()
        try:
            return sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model),
                tokens=str(tokens),
                num_threads=_NUM_THREADS,
                use_itn=True,  # 中文识别保留标点，输出更自然
            )
        except Exception as exc:
            raise GenerationUnavailable(
                f"本地识别器初始化失败: {type(exc).__name__}") from exc

    # ------------------------------------------------------------------

    def transcribe(self, audio: bytes, locale: str) -> str:
        # 先取识别器：模型未配置/依赖未安装时 503 语义优先于音频解码
        recognizer = self._get_recognizer()
        samples = _wav_to_float32(audio)
        try:
            with self._decode_lock:  # 串行化推理，见模块注释
                stream = recognizer.create_stream()
                stream.accept_waveform(_EXPECTED_RATE, samples)
                recognizer.decode_stream(stream)
                text = stream.result.text
        except (GenerationUnavailable, SpeechUnrecognized):
            raise
        except Exception as exc:
            raise GenerationUnavailable(
                f"本地识别失败: {type(exc).__name__}") from exc
        text = _strip_meta_tags(text)
        if not text:
            raise SpeechUnrecognized("本地识别未获得文本")
        return text
