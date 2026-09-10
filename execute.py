#!/usr/bin/env python3
"""
03 执行智能体 Executor
读 judged.json,按三轨分派子流程,产出可发布的小红书笔记:
- tutorial:标题+步骤正文+界面截图风格配图
- skill:标题+skill代码+演示输入输出+流程图配图
- ppt:标题+正文+python-pptx生成PPT文件+页面缩略图

输出 produced.json + data/images/{topic_id}/ + data/ppt_templates/{topic_id}/
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

PLAN_DIR = Path(__file__).parent
DATA_DIR = PLAN_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
PPT_DIR = DATA_DIR / "ppt_templates"
JUDGED_PATH = DATA_DIR / "judged.json"
PRODUCED_PATH = DATA_DIR / "produced.json"
OPENCLAW_PATH = Path.home() / ".openclaw" / "openclaw.json"


def rel(p):
    """数据里只存相对项目根的路径,保证 produced.json 可跨机器/部署目录迁移"""
    try:
        return str(Path(p).resolve().relative_to(PLAN_DIR.resolve()))
    except (ValueError, OSError):
        return str(p)


def load_providers():
    oc = json.load(open(OPENCLAW_PATH, "r", encoding="utf-8"))
    return oc.get("models", {}).get("providers", {})


def call_llm(providers, provider_name, model, prompt, max_tokens=4000, retries=2,
             timeout=300, json_mode=True):
    """调用 LLM,带重试。json_mode=True 时走 json_object 强制合法 JSON。"""
    p = providers[provider_name]
    base_url = p["baseUrl"].rstrip("/")
    api_key = p["apiKey"]
    api_type = p.get("api", "openai")

    last_err = None
    for i in range(retries + 1):
        try:
            if "anthropic" in api_type:
                url = f"{base_url}/v1/messages"
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
                           "content-type": "application/json"}
                payload = {"model": model, "max_tokens": max_tokens,
                           "messages": [{"role": "user", "content": prompt}]}
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
                r.raise_for_status()
                return r.json()["content"][0]["text"]
            else:
                url = f"{base_url}/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": model, "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            print(f"    [LLM retry {i+1}/{retries+1}] {e}")
            time.sleep(3)
    raise last_err


def parse_json_tolerant(text):
    """容错解析 LLM 输出的 JSON"""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
    text = text.strip()
    # 对象
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end+1])
    # 数组
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        return json.loads(text[start:end+1])
    raise ValueError("no JSON found")


def gen_image(prompt, out_dir, prefix, size="3:4"):
    """调 bl image generate 生成一张图,返回本地路径或 None"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "bl", "image", "generate",
        "--prompt", prompt,
        "--size", size,
        "--out-dir", str(out_dir),
        "--out-prefix", prefix,
        "--quiet",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        # 找生成的文件
        files = sorted(out_dir.glob(f"{prefix}*.png")) + sorted(out_dir.glob(f"{prefix}*.jpg"))
        if files:
            return str(files[0])
        print(f"    [IMG WARN] no file: {r.stdout[-100:]} {r.stderr[-100:]}")
        return None
    except Exception as e:
        print(f"    [IMG FAIL] {e}")
        return None


# ============ 教程轨 ============

def produce_tutorial(providers, topic, topic_dir):
    """教程轨:标题+步骤正文+配图"""
    title_hint = topic.get("title_hint", "")
    angle = topic.get("angle", "")
    cross_sell = topic.get("cross_sell_hint", "")

    prompt = f"""你是小红书爆款作者。写一篇AI教程笔记。

选题:{title_hint}
切入角度:{angle}
导流话术(必须自然融入正文结尾):{cross_sell}

严格输出 JSON(字段如下):
{{
  "title": "最终标题(≤20字,可基于选题微调)",
  "body": "正文500-700字。结构:1-2句痛点钩子开头;2-3段教程步骤(每步一小段,带序号);结果对比;结尾福利引导。用真实口吻,短段落,适当emoji,不要markdown标题符号",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "steps": [
    {{"desc": "步骤1描述", "screenshot_prompt": "配图描述,中文,具体到界面元素,小红书实拍截图风格"}}
  ],
  "image_prompts": ["首图prompt:突出结果对比或标题大字感觉的封面描述"]
}}

要求:steps 3-5 个,image_prompts 1 个(首图)。只输出 JSON。"""
    text = call_llm(providers, "zhipu", "GLM-5.3-Flash", prompt, max_tokens=6000)
    data = parse_json_tolerant(text)

    # 生成配图
    image_paths = []
    if data.get("image_prompts"):
        p = gen_image(data["image_prompts"][0] + ",小红书封面风格,3:4竖版", topic_dir, "cover")
        if p:
            image_paths.append(p)
    for i, step in enumerate(data.get("steps", [])[:3]):
        sp = step.get("screenshot_prompt", "")
        if sp:
            p = gen_image(f"{sp},软件界面截图风格,清晰", topic_dir, f"step{i+1}")
            if p:
                image_paths.append(p)

    data["image_paths"] = [rel(p) for p in image_paths]
    return data


# ============ Skill 轨 ============

def produce_skill(providers, topic, topic_dir):
    """Skill 轨:标题+skill代码+演示+配图"""
    title_hint = topic.get("title_hint", "")
    angle = topic.get("angle", "")

    prompt = f"""你是 AI agent 开发者兼小红书博主。写一篇 skill 分享笔记。

选题:{title_hint}
切入角度:{angle}

严格输出 JSON:
{{
  "title": "最终标题(≤20字)",
  "body": "正文600-900字。结构:痛点钩子;skill设计思路1-2段;核心代码说明(不用贴完整代码,说关键逻辑);调用演示(input/output简述);复用建议;结尾引导。真实口吻+短段落+emoji",
  "skill_script": "核心代码或prompt模板(15-40行,可运行/可复制的程度,Python或JSON格式skill定义)",
  "demo_input": "演示输入示例(简短)",
  "demo_output": "演示输出示例(简短)",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "image_prompts": ["首图prompt:流程图或before-after对比,小红书封面风格"]
}}

只输出 JSON。"""
    text = call_llm(providers, "zhipu", "GLM-5.3-Flash", prompt, max_tokens=6000)
    data = parse_json_tolerant(text)

    image_paths = []
    if data.get("image_prompts"):
        p = gen_image(data["image_prompts"][0] + ",简洁流程图风格,白底,3:4竖版", topic_dir, "cover")
        if p:
            image_paths.append(p)

    # skill 代码存文件
    if data.get("skill_script"):
        code_path = topic_dir / "skill_script.txt"
        code_path.write_text(data["skill_script"], encoding="utf-8")
        data["skill_script_path"] = rel(code_path)

    data["image_paths"] = [rel(p) for p in image_paths]
    return data


# ============ PPT 轨 ============

def produce_ppt(providers, topic, topic_dir):
    """PPT 轨(纯 Markdown 版):标题+正文+完整 Markdown 文案模板+封面图。
    不再生成 pptx,核心交付物是可直接复制使用的逐页成稿 Markdown。"""
    title_hint = topic.get("title_hint", "")
    angle = topic.get("angle", "")
    cross_sell = topic.get("cross_sell_hint", "")

    # ---- 第 1 步:小 JSON,拿笔记元数据 ----
    meta_prompt = f"""你是小红书博主。为一套 PPT 文案模板写笔记元数据。

笔记选题:{title_hint}
切入角度:{angle}
导流话术(必须自然融入正文结尾):{cross_sell}

严格输出 JSON:
{{
  "title": "小红书笔记最终标题(≤20字)",
  "body": "小红书正文400-600字:成品钩子开头;这套模板解决什么问题、适合谁;模板结构亮点;导流话术结尾。短段落+emoji,不要markdown符号",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "md_filename": "英文短文件名(如 thesis-defense-template.md)",
  "cover_prompt": "小红书封面图描述:干净的桌面/文档氛围,突出主题文字感,暖色调,3:4竖版,不要出现真实人脸"
}}

只输出 JSON。"""
    meta_text = call_llm(providers, "zhipu", "GLM-5.3-Flash",
                         meta_prompt, max_tokens=3000, json_mode=True)
    data = parse_json_tolerant(meta_text)

    # ---- 第 2 步:纯文本输出完整 Markdown(不包 JSON,避免转义/截断) ----
    md_prompt = f"""你是资深 PPT 文案策划。写一套【纯 Markdown 格式的 PPT 完整文案模板】,核心是内容本身——用户拿到后可以直接把每页文案复制进自己的 PPT。

主题:{data.get('title', title_hint)}
切入角度:{angle}

结构要求(务必写满写细):
1. 一级标题是模板名;开头用引用块写:适用场景 + 建议页数 + 使用方法(复制每页【页面文案】下的内容到 PPT 文本框)
2. 每页用二级标题,格式「## 第N页 · 页面类型 · 页标题」,类型含 封面/目录/背景/方法/数据/案例/总结/致谢 等
3. 每页必须包含:
   - **页面文案**:这页上要出现的完整文字(成段表达,不是干巴巴的要点;该成段的地方写完整句子,该列点的地方用列表),用户可直接照抄
   - **演讲备注**:2-4 句这页口头怎么讲
   - **排版建议**:一句话(配色/图示/留白),不需要的页可省略
4. 总页数 10-12 页,内容总字数 1500-2200 字;必须覆盖:封面、目录、问题背景、核心内容 3-5 页(要有真实可用的实质内容,不要空话套话)、总结/行动建议、致谢/结尾
5. 只使用标准 Markdown:## 标题、**加粗**、- 无序列表、1. 有序列表、> 引用、--- 分隔线;不要用表格和代码块
6. 内容要具体到该选题场景(例如答辩模板就写答辩该讲什么),不要泛泛而谈

直接输出 Markdown 正文,从一级标题开始,不要任何解释、不要用代码块包裹。"""
    md_content = call_llm(providers, "zhipu", "GLM-5.3-Flash",
                          md_prompt, max_tokens=9000, json_mode=False)
    md_content = md_content.strip()
    # 剥掉可能的 ```markdown 包裹
    if md_content.startswith("```"):
        lines = md_content.split("\n")
        lines = lines[1:]  # 去首行 ```
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        md_content = "\n".join(lines).strip()
    # 质量校验:必须有一级标题和足够的二级标题页
    page_count = md_content.count("\n## ") + (1 if md_content.startswith("## ") else 0)
    if not md_content.startswith("#") or page_count < 8:
        raise ValueError(f"markdown 质量不合格(页数={page_count},长度={len(md_content)})")

    # 1. Markdown 模板落盘
    topic_dir.mkdir(parents=True, exist_ok=True)
    md_name = data.get("md_filename") or f"{topic.get('id', 'template')}.md"
    if not md_name.endswith(".md"):
        md_name += ".md"
    # 文件名只保留安全字符
    md_name = "".join(c for c in md_name if c.isalnum() or c in "-_.")
    md_path = topic_dir / md_name
    md_path.write_text(md_content, encoding="utf-8")
    data["md_file"] = rel(md_path)

    # 2. 封面图
    image_paths = []
    cover_prompt = data.get("cover_prompt", f"PPT文案模板封面,主题「{title_hint}」")
    p = gen_image(cover_prompt + ",小红书封面风格,3:4竖版", topic_dir, "cover")
    if p:
        image_paths.append(p)
    data["image_paths"] = [rel(p) for p in image_paths]
    return data


# ============ main ============

def main():
    if not JUDGED_PATH.exists():
        print(f"[ERR] {JUDGED_PATH} 不存在,先跑 judge.py")
        sys.exit(1)

    judged = json.load(open(JUDGED_PATH, "r", encoding="utf-8"))
    providers = load_providers()

    # resume:读已有 produced.json,ready 的跳过
    produced = {
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "posts": []
    }
    done_ids = set()
    if PRODUCED_PATH.exists():
        try:
            prev = json.load(open(PRODUCED_PATH, "r", encoding="utf-8"))
            for p in prev.get("posts", []):
                if p.get("status") == "ready":
                    produced["posts"].append(p)
                    done_ids.add(p.get("topic_id"))
            print(f"[RESUME] 已有 {len(done_ids)} 个 ready,跳过")
        except Exception:
            pass

    # 可指定只跑前 N 个(测试用)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 999

    count = 0
    for track_name, track in judged["tracks"].items():
        print(f"\n[Track] {track_name} - {len(track['topics'])} topics")
        for topic in track["topics"]:
            tid = topic.get("id", f"{track_name[:3]}_{count:03d}")
            if tid in done_ids:
                print(f"\n  [{tid}] SKIP(已 ready)")
                count += 1
                continue
            if count >= limit:
                break
            print(f"\n  [{tid}] {topic.get('title_hint','')[:40]}")

            topic_dir = IMAGES_DIR / tid
            topic_dir.mkdir(parents=True, exist_ok=True)

            try:
                if track_name == "tutorial":
                    data = produce_tutorial(providers, topic, topic_dir)
                elif track_name == "skill":
                    data = produce_skill(providers, topic, topic_dir)
                elif track_name == "ppt":
                    ppt_topic_dir = PPT_DIR / tid
                    ppt_topic_dir.mkdir(parents=True, exist_ok=True)
                    data = produce_ppt(providers, topic, ppt_topic_dir)
                else:
                    data = None

                if data:
                    data["topic_id"] = tid
                    data["track"] = track_name
                    data["status"] = "ready"
                    produced["posts"].append(data)
                    print(f"     OK: {data.get('title','')[:36]} | {len(data.get('image_paths',[]))} images")
                else:
                    produced["posts"].append({
                        "topic_id": tid, "track": track_name,
                        "status": "skipped", "skip_reason": "unknown track"
                    })
            except Exception as e:
                print(f"     FAILED: {e}")
                produced["posts"].append({
                    "topic_id": tid, "track": track_name,
                    "status": "skipped", "skip_reason": str(e)[:200]
                })
            count += 1

        # 每轨结束就落盘一次,防中途挂
        with open(PRODUCED_PATH, "w", encoding="utf-8") as f:
            json.dump(produced, f, ensure_ascii=False, indent=2)

    with open(PRODUCED_PATH, "w", encoding="utf-8") as f:
        json.dump(produced, f, ensure_ascii=False, indent=2)

    ready = sum(1 for p in produced["posts"] if p.get("status") == "ready")
    print(f"\n[DONE] {ready}/{len(produced['posts'])} ready -> {PRODUCED_PATH}")


if __name__ == "__main__":
    main()
