"""pytest 共享夹具：独立临时库、stub Provider、静音 WAV 与端到端造数助手。"""

from __future__ import annotations

import io
import time
import wave

import pytest
from fastapi.testclient import TestClient

from server.app import config, db as db_module


def _make_client(monkeypatch, tmp_path, **env) -> TestClient:
    """按 env 覆盖环境变量后重建应用，返回包裹好的 TestClient。

    yield 前由 fixture 负责设置；连接与配置缓存的清理在各 fixture 收尾统一做。
    """
    monkeypatch.setenv("SERVER_DB_PATH", str(tmp_path / "server.db"))
    monkeypatch.setenv("SERVER_PROVIDER", "stub")
    monkeypatch.setenv("SERVER_ADMIN_TOKEN", "test-token")
    monkeypatch.delenv("SERVER_RATE_LIMIT_PER_MIN", raising=False)
    monkeypatch.delenv("SERVER_BASE_URL", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.reset_settings_cache()

    from server.app.main import create_app

    return TestClient(create_app())


def make_wav(seconds: float = 1.0, *, seed: int | None = None) -> bytes:
    """生成 16kHz 单声道 16bit WAV 字节；seed 非 None 时填充确定性噪声以改变识别内容。"""
    rate = 16000
    n_frames = int(rate * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        if seed is None:
            frames = b"\x00\x00" * n_frames
        else:
            # 简单线性同余噪声，保证不同 seed 产出不同音频字节
            frames = bytearray()
            state = seed & 0xFFFF
            for _ in range(n_frames):
                state = (state * 1103515245 + 12345) & 0x7FFFFFFF
                sample = (state % 2001) - 1000  # 小幅噪声，避免直流
                frames += sample.to_bytes(2, "little", signed=True)
            frames = bytes(frames)
        wf.writeframes(frames)
    return buf.getvalue()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """默认配置下的测试客户端：stub Provider、独立库、后台口令 test-token。"""
    with _make_client(monkeypatch, tmp_path) as test_client:
        yield test_client
    db_module.close_thread_conn()
    config.reset_settings_cache()


@pytest.fixture()
def limited_client(monkeypatch, tmp_path):
    """限流阈值压到 3 次/分钟的客户端。"""
    with _make_client(monkeypatch, tmp_path,
                      SERVER_RATE_LIMIT_PER_MIN="3") as test_client:
        yield test_client
    db_module.close_thread_conn()
    config.reset_settings_cache()


@pytest.fixture()
def no_token_client(monkeypatch, tmp_path):
    """后台口令为空串（未配置）的客户端。"""
    with _make_client(monkeypatch, tmp_path,
                      SERVER_ADMIN_TOKEN="") as test_client:
        yield test_client
    db_module.close_thread_conn()
    config.reset_settings_cache()


def upload_candidate(client: TestClient, wav: bytes, *, request_id: str = "req-test"):
    """上传候选的薄封装，返回响应对象。"""
    return client.post(
        "/api/v1/buddy-candidates",
        data={"request_id": request_id, "locale": "zh-CN"},
        files={"audio": ("voice.wav", wav, "audio/wav")},
    )


def create_candidate(client: TestClient, wav: bytes | None = None) -> dict:
    """上传候选并断言成功，返回响应 JSON。"""
    if wav is None:
        wav = make_wav()
    resp = upload_candidate(client, wav)
    assert resp.status_code == 201, resp.text
    return resp.json()


def submit_generation(client: TestClient, candidate_id: str,
                      *, request_id: str = "req-gen") -> dict:
    """提交生成任务并断言 202，返回响应 JSON。"""
    resp = client.post(
        "/api/v1/buddy-generations",
        json={"request_id": request_id, "candidate_id": candidate_id},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


def wait_generation(client: TestClient, generation_id: str,
                    *, timeout: float = 10.0, interval: float = 0.05) -> dict:
    """轮询任务直至终态；异步任务在独立线程执行，超时保护防悬挂。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/buddy-generations/{generation_id}")
        assert resp.status_code == 200, resp.text
        task = resp.json()
        if task["status"] in ("succeeded", "failed"):
            return task
        time.sleep(interval)
    raise AssertionError(f"任务 {generation_id} 在 {timeout}s 内未到达终态")


def create_buddy(client: TestClient, wav: bytes | None = None) -> str:
    """走通 上传→提交→轮询 全链路，返回发布成功的 buddy_id。"""
    candidate = create_candidate(client, wav)
    task = submit_generation(client, candidate["candidate_id"])
    done = wait_generation(client, task["generation_id"])
    assert done["status"] == "succeeded", done
    return done["buddy_id"]
