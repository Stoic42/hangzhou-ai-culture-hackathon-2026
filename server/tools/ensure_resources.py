"""部署资源自动补全引导脚本（幂等，可重复执行）。

用途：部署到服务器后检查并补全运行所需资源，就绪退出码 0，有缺失 1。
脚本只做检查与补全，不启动服务；凭证绝不入库、绝不打印。

    py -3.12 server/tools/ensure_resources.py

检查项：
1. 基础依赖（fastapi/uvicorn/jinja2/httpx），缺失则提示安装 requirements.txt；
2. SERVER_ASR_PROVIDER=local 时：sherpa-onnx 可 import、ASR_MODEL_DIR 下
   model.int8.onnx 或 model.onnx + tokens.txt 齐全，缺失则自动下载解压
   SenseVoice 模型（约 1GB，stdlib urllib + tarfile）；
3. SERVER_LLM_PROVIDER=remote 时：OPENAI_BASE_URL / OPENAI_API_KEY /
   OPENAI_MODEL 已设置（只报缺失项，不打印任何值）；
4. 最后打印配置摘要。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENTS = _REPO_ROOT / "server" / "requirements.txt"
_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
)


def _pip_install(*args: str) -> bool:
    print(f"  执行: py -3.12 -m pip install {' '.join(args)}")
    code = subprocess.call(
        [sys.executable, "-m", "pip", "install", *args],
        cwd=str(_REPO_ROOT),
    )
    return code == 0


def _check_base_deps() -> list[str]:
    """返回缺失项列表。"""
    missing = []
    for mod, pkg in (
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("jinja2", "jinja2"),
        ("httpx", "httpx"),
    ):
        if _importable(mod):
            print(f"  [OK] {pkg}")
        else:
            print(f"  [缺失] {pkg}")
            missing.append(pkg)
    if missing:
        print("  尝试自动安装 server/requirements.txt ...")
        if _pip_install("-r", str(_REQUIREMENTS)):
            missing = [p for p in missing if not _importable(p)]
    return missing


def _importable(mod: str) -> bool:
    import importlib

    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


def _model_files_ok(model_dir: Path) -> bool:
    has_model = (model_dir / "model.int8.onnx").is_file() or (
        model_dir / "model.onnx"
    ).is_file()
    return has_model and (model_dir / "tokens.txt").is_file()


def _download_with_progress(url: str, dest: Path) -> None:
    """stdlib urllib 下载，带进度提示（每 64MB 打一行）。"""
    print(f"  下载模型: {url}")
    print("  （约 1GB，依网络情况可能需要较长时间）")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        got, next_mark = 0, 64 * 1024 * 1024
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if got >= next_mark:
                if total:
                    pct = got * 100 // total
                    print(f"    已下载 {got // (1024 * 1024)}MB / {total // (1024 * 1024)}MB ({pct}%)")
                else:
                    print(f"    已下载 {got // (1024 * 1024)}MB")
                next_mark += 64 * 1024 * 1024
    print(f"  下载完成: {got // (1024 * 1024)}MB -> {dest}")


def _ensure_model(model_dir: Path) -> bool:
    """确保模型目录齐全；必要时下载解压。返回是否就绪。"""
    if _model_files_ok(model_dir):
        print(f"  [OK] 模型目录已就绪: {model_dir}")
        return True

    model_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(model_dir.parent)) as tmp:
        tmp = Path(tmp)
        archive = tmp / "model.tar.bz2"
        try:
            _download_with_progress(_MODEL_URL, archive)
        except Exception as exc:  # noqa: BLE001 - 给明确手动步骤
            print(f"  [失败] 模型下载失败: {exc!r}")
            _print_manual_steps(model_dir)
            return False
        try:
            print("  解压模型 ...")
            with tarfile.open(archive, "r:bz2") as tf:
                tf.extractall(tmp, filter="data")
        except Exception as exc:  # noqa: BLE001
            print(f"  [失败] 模型解压失败: {exc!r}")
            _print_manual_steps(model_dir)
            return False
        # release 包内是 sherpa-onnx-sense-voice-.../ 单层目录，取其内容
        inner = [p for p in tmp.iterdir() if p.is_dir()]
        if len(inner) != 1 or not _model_files_ok(inner[0]):
            print("  [失败] 解压结果不符合预期（未找到唯一模型目录或文件不全）")
            _print_manual_steps(model_dir)
            return False
        if model_dir.exists():
            shutil.rmtree(model_dir)
        shutil.move(str(inner[0]), str(model_dir))

    ok = _model_files_ok(model_dir)
    if ok:
        print(f"  [OK] 模型已补全: {model_dir}")
    else:
        _print_manual_steps(model_dir)
    return ok


def _print_manual_steps(model_dir: Path) -> None:
    print(
        "  请手动完成：\n"
        f"    1. 浏览器下载 {_MODEL_URL}\n"
        f"    2. 解压后将 sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\n"
        f"       重命名为 sense-voice，放到 {model_dir.parent}\n"
        "    3. 确认目录内含 model.int8.onnx（或 model.onnx）与 tokens.txt\n"
        f"    4. 设置环境变量 ASR_MODEL_DIR={model_dir} 后重新运行本脚本"
    )


def main() -> int:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    asr_provider = os.environ.get(
        "SERVER_ASR_PROVIDER", os.environ.get("SERVER_PROVIDER", "stub")
    )
    llm_provider = os.environ.get(
        "SERVER_LLM_PROVIDER", os.environ.get("SERVER_PROVIDER", "stub")
    )
    model_dir = Path(
        os.environ.get("ASR_MODEL_DIR", str(_REPO_ROOT / "server" / "models" / "sense-voice"))
    )

    problems: list[str] = []

    print("== 1. 基础依赖 ==")
    problems += _check_base_deps()

    if asr_provider == "local":
        print("== 2. local ASR（sherpa-onnx） ==")
        if not _importable("sherpa_onnx"):
            print("  [缺失] sherpa-onnx")
            _pip_install("sherpa-onnx")
        if not _importable("sherpa_onnx"):
            problems.append("sherpa-onnx（pip install sherpa-onnx 失败）")
        if not _ensure_model(model_dir):
            problems.append(f"ASR 模型目录未就绪: {model_dir}")
    else:
        print(f"== 2. ASR provider = {asr_provider}（非 local，跳过模型检查） ==")

    if llm_provider == "remote":
        print("== 3. remote LLM 环境变量 ==")
        for var in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
            if os.environ.get(var):
                print(f"  [OK] {var} 已设置")
            else:
                print(f"  [缺失] {var}")
                problems.append(var)
    else:
        print(f"== 3. LLM provider = {llm_provider}（非 remote，跳过凭证检查） ==")

    print("== 配置摘要 ==")
    print(f"  SERVER_ASR_PROVIDER   = {asr_provider}")
    print(f"  SERVER_LLM_PROVIDER   = {llm_provider}")
    print(f"  ASR_MODEL_DIR         = {model_dir}")
    print(f"  SERVER_RATE_LIMIT_PER_MIN = {os.environ.get('SERVER_RATE_LIMIT_PER_MIN', '10')}")
    print(f"  SERVER_ADMIN_TOKEN    = {'已设置' if os.environ.get('SERVER_ADMIN_TOKEN') else '未设置（/admin 将拒绝访问）'}")
    print(f"  SERVER_BASE_URL       = {os.environ.get('SERVER_BASE_URL', 'http://127.0.0.1:8000')}")

    if problems:
        print(f"\n[未就绪] {len(problems)} 项缺失：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\n[就绪] 全部检查通过，可启动服务：")
    print("  py -3.12 -m uvicorn server.app.main:app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
