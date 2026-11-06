"""sherpa-onnx 本地 ASR 适配器的测试。

不打真实模型：向 sys.modules 注入假 sherpa_onnx 模块验证适配器行为；
真机集成用例经 ASR_MODEL_DIR 指向真实 SenseVoice-small 目录时才启用。
"""

from __future__ import annotations

import io
import os
import sys
import types
import wave
from pathlib import Path

import pytest

from server.app.providers import base
from server.app.providers.local_asr import SherpaLocalASR

from .conftest import make_wav


# ---------------------------------------------------------------------------
# 假 sherpa_onnx 模块
# ---------------------------------------------------------------------------

class _FakeStream:
    def __init__(self) -> None:
        self.rate: int | None = None
        self.samples: list[float] | None = None
        self.result = types.SimpleNamespace(text="")

    def accept_waveform(self, rate: int, samples) -> None:
        self.rate = rate
        self.samples = list(samples)


class _FakeRecognizer:
    """记录构造参数与收到的音频；next_text 控制识别结果。"""

    next_text = "<|zh|><|withitn|>你好，世界"
    instances: list[_FakeRecognizer] = []
    kwargs: dict | None = None

    def __init__(self, **kwargs) -> None:
        type(self).kwargs = kwargs
        type(self).instances.append(self)
        self.stream: _FakeStream | None = None

    @classmethod
    def from_sense_voice(cls, **kwargs):
        return cls(**kwargs)

    def create_stream(self) -> _FakeStream:
        self.stream = _FakeStream()
        return self.stream

    def decode_stream(self, stream: _FakeStream) -> None:
        stream.result.text = type(self).next_text


@pytest.fixture()
def fake_sherpa(monkeypatch):
    """注入假 sherpa_onnx 模块，返回可操控的假识别器类。"""
    module = types.ModuleType("sherpa_onnx")
    module.OfflineRecognizer = _FakeRecognizer
    monkeypatch.setitem(sys.modules, "sherpa_onnx", module)
    _FakeRecognizer.instances.clear()
    _FakeRecognizer.kwargs = None
    _FakeRecognizer.next_text = "<|zh|><|withitn|>你好，世界"
    return _FakeRecognizer


@pytest.fixture()
def model_dir(tmp_path):
    """完整模型目录：model.int8.onnx + tokens.txt。"""
    d = tmp_path / "sense-voice"
    d.mkdir()
    (d / "model.int8.onnx").write_bytes(b"int8")
    (d / "tokens.txt").write_text("<blk>\n", encoding="utf-8")
    return d


def _make_wav_rate(rate: int, seconds: float = 1.0) -> bytes:
    """任意采样率的静音 WAV。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 单测（假模块）
# ---------------------------------------------------------------------------

def test_transcribe_strips_meta_tags(fake_sherpa, model_dir):
    asr = SherpaLocalASR(model_dir=str(model_dir))
    assert asr.transcribe(make_wav(1.0), "zh-CN") == "你好，世界"
    assert fake_sherpa.kwargs["num_threads"] == 2
    assert fake_sherpa.kwargs["model"].endswith("model.int8.onnx")
    assert fake_sherpa.kwargs["tokens"].endswith("tokens.txt")
    # 识别器惰性加载且只建一次
    asr.transcribe(make_wav(0.5), "zh-CN")
    assert len(fake_sherpa.instances) == 1


def test_transcribe_model_onnx_fallback(fake_sherpa, model_dir):
    """无 model.int8.onnx 时退回 model.onnx。"""
    (model_dir / "model.int8.onnx").unlink()
    (model_dir / "model.onnx").write_bytes(b"fp32")
    asr = SherpaLocalASR(model_dir=str(model_dir))
    assert asr.transcribe(make_wav(0.2), "zh-CN") == "你好，世界"
    assert fake_sherpa.kwargs["model"].endswith("model.onnx")


def test_transcribe_empty_result_raises_unrecognized(fake_sherpa, model_dir):
    """空识别结果（如纯静音）映射 422 speech_unrecognized。"""
    fake_sherpa.next_text = "<|zh|><|withitn|>"  # 剥标签后为空
    asr = SherpaLocalASR(model_dir=str(model_dir))
    with pytest.raises(base.SpeechUnrecognized):
        asr.transcribe(make_wav(1.0), "zh-CN")


def test_transcribe_model_dir_missing(fake_sherpa):
    """未配置模型目录：装配成功，transcribe 抛 GenerationUnavailable。"""
    asr = SherpaLocalASR(model_dir="")
    with pytest.raises(base.GenerationUnavailable, match="本地模型未配置"):
        asr.transcribe(make_wav(0.1), "zh-CN")
    assert fake_sherpa.instances == []


def test_transcribe_model_files_incomplete(fake_sherpa, tmp_path):
    """目录存在但缺 tokens.txt：同样 503。"""
    d = tmp_path / "broken"
    d.mkdir()
    (d / "model.int8.onnx").write_bytes(b"int8")
    asr = SherpaLocalASR(model_dir=str(d))
    with pytest.raises(base.GenerationUnavailable, match="本地模型未配置"):
        asr.transcribe(make_wav(0.1), "zh-CN")


def test_transcribe_sherpa_not_installed(monkeypatch, model_dir):
    """未安装 sherpa-onnx：import 失败映射 GenerationUnavailable。"""
    # sys.modules 中置 None 会让 import 抛 ImportError
    monkeypatch.setitem(sys.modules, "sherpa_onnx", None)
    asr = SherpaLocalASR(model_dir=str(model_dir))
    with pytest.raises(base.GenerationUnavailable, match="未安装 sherpa-onnx"):
        asr.transcribe(make_wav(0.1), "zh-CN")


def test_transcribe_resamples_non_16k(fake_sherpa, model_dir):
    """8kHz WAV 走线性插值重采样，识别器收到 16kHz 等效长度。"""
    asr = SherpaLocalASR(model_dir=str(model_dir))
    asr.transcribe(_make_wav_rate(8000, seconds=1.0), "zh-CN")
    stream = fake_sherpa.instances[0].stream
    assert stream.rate == 16000
    assert len(stream.samples) == 16000


def test_transcribe_decode_error_raises_unavailable(monkeypatch, fake_sherpa,
                                                    model_dir):
    """识别过程异常映射 503 generation_unavailable。"""

    def boom(self, stream):
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(fake_sherpa, "decode_stream", boom)
    asr = SherpaLocalASR(model_dir=str(model_dir))
    with pytest.raises(base.GenerationUnavailable, match="本地识别失败"):
        asr.transcribe(make_wav(0.1), "zh-CN")


# ---------------------------------------------------------------------------
# 真机集成（仅当 ASR_MODEL_DIR 指向完整模型目录时启用）
# ---------------------------------------------------------------------------

def _real_model_ready() -> bool:
    d = os.environ.get("ASR_MODEL_DIR", "")
    return bool(d) and (Path(d) / "tokens.txt").is_file() and (
        (Path(d) / "model.int8.onnx").is_file()
        or (Path(d) / "model.onnx").is_file())


@pytest.mark.skipif(not _real_model_ready(),
                    reason="未设置 ASR_MODEL_DIR 或模型目录不完整")
def test_transcribe_real_model():
    """真实 SenseVoice-small 识别 1s 静音。

    静音可能识别为空文本（SpeechUnrecognized，契约 422），也可能返回
    零星文字；两者都是合法结果，但服务不可用（GenerationUnavailable）
    说明装配/依赖有问题，必须失败。
    """
    asr = SherpaLocalASR()
    try:
        asr.transcribe(make_wav(1.0), "zh-CN")
    except base.GenerationUnavailable as exc:  # 装配/依赖问题，不允许
        pytest.fail(f"真实模型识别不可用: {exc}")
    except base.SpeechUnrecognized:
        pass  # 静音无文本，合法
