#!/usr/bin/env python3
"""路径与 LLM 密钥的薄封装。不改变收集 / 判断 / 执行的职责。

文件状态机保持不变：collected.json → judged.json → produced.json。

EXTENSION（定制流水线）：
- 品类种子词、禁词：改 collect_config.yaml。profiles/*.yaml 只是客户简报，不会自动加载。
- 密钥与路径：复制 .env.example 为 .env。不要把 .env 或登录态提交进仓库。
- 扩词提示词、评分权重、三轨成稿：分别在 expand_keywords.py、judge.py、execute.py，
  搜索标记 EXTENSION。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_project_dotenv() -> None:
    """读取项目根 .env。进程里已有的环境变量优先；空值视为未设置。"""
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not key or value == "" or key in os.environ:
            continue
        os.environ[key] = value


def _project_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def data_dir() -> Path:
    load_project_dotenv()
    raw = os.environ.get("DATA_DIR", "").strip()
    path = _project_path(raw) if raw else ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def collect_config_path() -> Path:
    load_project_dotenv()
    raw = os.environ.get("COLLECT_CONFIG_PATH", "").strip()
    return _project_path(raw) if raw else ROOT / "collect_config.yaml"


def xhs_state_path() -> Path:
    """小红书登录态。默认 data/xhs_state.json，且被 gitignore。"""
    load_project_dotenv()
    raw = os.environ.get("XHS_STATE_PATH", "").strip()
    if raw:
        return _project_path(raw)
    return data_dir() / "xhs_state.json"


def openclaw_config_path() -> Path:
    load_project_dotenv()
    raw = os.environ.get("OPENCLAW_CONFIG_PATH", "").strip()
    if raw:
        return _project_path(raw)
    return Path.home() / ".openclaw" / "openclaw.json"


def bl_bin() -> str:
    """文生图 CLI。未安装时 execute.py 会跳过配图，不中断成稿。"""
    load_project_dotenv()
    return os.environ.get("BL_BIN", "").strip() or "bl"


def _yaml_llm_names() -> tuple[str | None, str | None]:
    path = collect_config_path()
    if not path.is_file():
        return None, None
    try:
        import yaml
    except ImportError:
        return None, None
    with path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    llm = cfg.get("llm") or {}
    return llm.get("provider") or None, llm.get("model") or None


def _openclaw_providers() -> dict:
    path = openclaw_config_path()
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    providers = payload.get("models", {}).get("providers", {})
    return providers if isinstance(providers, dict) else {}


def resolve_llm() -> tuple[dict, str, str]:
    """返回 (providers, provider_name, model)。

    名称：LLM_PROVIDER / LLM_MODEL，否则 collect_config.yaml 的 llm.*，
    再否则 zhipu / GLM-5.3-Flash。
    密钥：LLM_API_KEY + LLM_BASE_URL 覆盖该 provider；否则读 openclaw.json。
    """
    load_project_dotenv()
    yaml_provider, yaml_model = _yaml_llm_names()
    provider_name = os.environ.get("LLM_PROVIDER", "").strip() or yaml_provider or "zhipu"
    model = os.environ.get("LLM_MODEL", "").strip() or yaml_model or "GLM-5.3-Flash"

    providers = dict(_openclaw_providers())
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    explicit_api_type = os.environ.get("LLM_API_TYPE", "").strip()

    if api_key or base_url:
        current = dict(providers.get(provider_name) or {})
        if api_key:
            current["apiKey"] = api_key
        if base_url:
            current["baseUrl"] = base_url
        if explicit_api_type:
            current["api"] = explicit_api_type
        elif "api" not in current:
            current["api"] = "openai"
        providers[provider_name] = current

    block = providers.get(provider_name) or {}
    if not block.get("apiKey") or not block.get("baseUrl"):
        raise RuntimeError(
            "未配置 LLM 密钥。复制 .env.example 为 .env，填写 LLM_API_KEY 与 LLM_BASE_URL；"
            "或把密钥放在 ~/.openclaw/openclaw.json（可用 OPENCLAW_CONFIG_PATH 改路径）。"
            "查看样板看板不需要密钥：php -S 127.0.0.1:8080 后打开 index.html。"
        )
    return providers, provider_name, model


def require_llm() -> tuple[dict, str, str]:
    """给三个智能体脚本用。缺密钥时打印原因并以状态码 1 退出。"""
    try:
        return resolve_llm()
    except RuntimeError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def llm_status() -> dict:
    """给冒烟检查用。失败不抛异常，返回值里不含密钥。"""
    try:
        _providers, name, model = resolve_llm()
        return {"configured": True, "provider": name, "model": model}
    except RuntimeError as exc:
        return {"configured": False, "detail": str(exc)}
