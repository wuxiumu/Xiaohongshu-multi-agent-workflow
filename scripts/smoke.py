#!/usr/bin/env python3
"""离线冒烟：不调用 LLM、不打开浏览器、不访问小红书。

用法（在仓库根目录）：
  python3 scripts/smoke.py
  python3 scripts/smoke.py --with-php

默认：若本机有 php，则顺便检查 api.php 语法并用样板数据请求 stats/list。
没有 php 时只打印 SKIP，退出码仍为 0。--with-php 在缺少 php 时失败。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_FILES = [
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "runtime_env.py",
    "collect_config.yaml",
    "expand_keywords.py",
    "scrape_xhs.py",
    "judge.py",
    "execute.py",
    "api.php",
    "index.html",
    "README.md",
    "data/collected.json",
    "data/judged.json",
    "data/produced.json",
    "profiles/example-beauty.yaml",
    "profiles/example-education.yaml",
    "docs/agents/00_总览.md",
    "docs/agents/01_收集智能体.md",
    "docs/agents/02_判断智能体.md",
    "docs/agents/03_执行智能体.md",
]

ENV_KEYS = [
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "OPENCLAW_CONFIG_PATH",
    "DATA_DIR",
    "COLLECT_CONFIG_PATH",
    "XHS_STATE_PATH",
    "BL_BIN",
]

SECRET_VALUE = re.compile(
    r"(?:sk-|sk-ant-|AKIA)[A-Za-z0-9_\-]{12,}|(?:apiKey|api_key|LLM_API_KEY)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{24,}"
)


class SmokeFailure(Exception):
    pass


def ok(message: str) -> None:
    print(f"[OK] {message}")


def skip(message: str) -> None:
    print(f"[SKIP] {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)
    ok(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_layout() -> None:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    check(not missing, "required files present" if not missing else "missing: " + ", ".join(missing))
    if sys.version_info < (3, 9):
        raise SmokeFailure(f"Python >= 3.9 required, found {sys.version}")
    ok(f"python {sys.version.split()[0]}")


def check_config_and_samples() -> None:
    try:
        import yaml
    except ImportError as exc:
        raise SmokeFailure("PyYAML missing. Run: python3 -m pip install -r requirements.txt") from exc

    cfg = yaml.safe_load(read_text(ROOT / "collect_config.yaml")) or {}
    check(bool(cfg.get("niche")), "collect_config.yaml has niche")
    llm = cfg.get("llm") or {}
    check(bool(llm.get("provider") and llm.get("model")), "collect_config.yaml has llm.provider and llm.model")
    tracks = cfg.get("tracks") or {}
    check(set(tracks) >= {"tutorial", "skill", "ppt"}, "collect_config.yaml has tutorial/skill/ppt tracks")
    for name, track in tracks.items():
        seeds = (track or {}).get("seeds") or []
        check(len(seeds) > 0, f"track {name} has seeds")

    for profile in (ROOT / "profiles").glob("*.yaml"):
        parsed = yaml.safe_load(read_text(profile)) or {}
        check(bool(parsed.get("niche")), f"{profile.name} has niche")

    collected = json.loads(read_text(ROOT / "data/collected.json"))
    judged = json.loads(read_text(ROOT / "data/judged.json"))
    produced = json.loads(read_text(ROOT / "data/produced.json"))
    check(set(collected.get("tracks") or {}) >= {"tutorial", "skill", "ppt"}, "collected.json tracks")
    check(set(judged.get("tracks") or {}) >= {"tutorial", "skill", "ppt"}, "judged.json tracks")
    posts = produced.get("posts") or []
    ready = [p for p in posts if p.get("status") == "ready" and p.get("title")]
    check(len(ready) > 0, f"produced.json has {len(ready)} ready posts")
    check(
        {"tutorial", "skill", "ppt"} <= {p.get("track") for p in ready},
        "produced.json covers tutorial, skill, and ppt",
    )


def check_secrets_hygiene() -> None:
    ignore = read_text(ROOT / ".gitignore")
    check(".env" in ignore, ".gitignore lists .env")
    check("xhs_state.json" in ignore, ".gitignore lists xhs_state.json")
    example = read_text(ROOT / ".env.example")
    for key in ENV_KEYS:
        check(key in example, f".env.example documents {key}")
    check("你的智谱Key" not in example and "sk-" not in example, ".env.example has no sample secret token")
    leaked = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.name == ".env":
            continue
        if path.suffix.lower() not in {".py", ".php", ".md", ".yaml", ".yml", ".html", ".js", ".txt", ".example", ".json"}:
            continue
        if path.parts[-2:] == ("data", "produced.json"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_VALUE.search(text):
            leaked.append(str(path.relative_to(ROOT)))
    check(not leaked, "no live-looking API keys in source" if not leaked else "possible secrets in " + ", ".join(leaked))


def check_extension_markers() -> None:
    markers = {
        "expand_keywords.py": "EXTENSION",
        "scrape_xhs.py": "EXTENSION",
        "judge.py": "EXTENSION",
        "execute.py": "EXTENSION",
        "docs/agents/00_总览.md": "定制扩展点",
        "docs/agents/01_收集智能体.md": "定制扩展点",
        "docs/agents/02_判断智能体.md": "定制扩展点",
        "docs/agents/03_执行智能体.md": "定制扩展点",
    }
    for rel, needle in markers.items():
        check(needle in read_text(ROOT / rel), f"{rel} documents extension point")


def check_runtime_env() -> None:
    import runtime_env

    status = runtime_env.llm_status()
    if status.get("configured"):
        ok(f"LLM configured ({status.get('provider')} / {status.get('model')})")
    else:
        skip("LLM key not configured; sample dashboard does not need it")
    check(runtime_env.data_dir().name != "", "data_dir resolves")
    check(runtime_env.bl_bin() == "bl" or bool(runtime_env.bl_bin()), "bl_bin has a default")


def check_php(required: bool) -> None:
    php = shutil.which("php")
    if not php:
        message = "php not on PATH. Install php-cli, then: php -S 127.0.0.1:8080"
        if required:
            raise SmokeFailure(message)
        skip(message)
        return
    lint = subprocess.run([php, "-l", str(ROOT / "api.php")], cwd=ROOT, capture_output=True, text=True)
    check(lint.returncode == 0, "php -l api.php" if lint.returncode == 0 else lint.stderr.strip() or lint.stdout.strip())

    port = 8765
    proc = subprocess.Popen(
        [php, "-S", f"127.0.0.1:{port}", "-t", str(ROOT)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 5
        stats = None
        last_error = "server did not respond"
        while time.time() < deadline:
            try:
                stats = fetch_json(f"http://127.0.0.1:{port}/api.php?action=stats")
                break
            except Exception as exc:  # noqa: BLE001 — retry until the built-in server accepts
                last_error = str(exc)
                time.sleep(0.2)
        if not isinstance(stats, dict) or stats.get("total", 0) <= 0:
            raise SmokeFailure(f"GET action=stats failed: {last_error}")
        ok("GET action=stats")
        listing = fetch_json(f"http://127.0.0.1:{port}/api.php?action=list")
        check(listing.get("total", 0) > 0, "GET action=list")
        flow = fetch_json(f"http://127.0.0.1:{port}/api.php?action=flow")
        check(len(flow.get("steps") or []) == 3, "GET action=flow has 3 agents")
        code = http_status(f"http://127.0.0.1:{port}/api.php?action=image&path=../api.php")
        check(code == 403, f"image path escape rejected ({code})")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def fetch_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise SmokeFailure(f"{url} -> HTTP {exc.code}: {body}") from exc
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SmokeFailure(f"expected JSON object from {url}")
    return payload


def http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline smoke check for the content factory.")
    parser.add_argument("--with-php", action="store_true", help="fail when php-cli is missing")
    args = parser.parse_args()
    try:
        check_layout()
        check_config_and_samples()
        check_secrets_hygiene()
        check_extension_markers()
        check_runtime_env()
        check_php(required=args.with_php)
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}")
        return 1
    print("[DONE] smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
