# 小红书多智能体内容生产流水线（收集 → 判断 → 执行）

> 一套用 **Python + LLM + Playwright + PHP** 实现的小红书（Xiaohongshu / RED）选题研究与内容生产自动化框架。三个智能体分工：**收集市场信号 → 规则+LLM 混合评分决策 → 分派生成可发布成品**，全程产出本地物料，**系统不自动发帖、不导流站外**。

**English:** A multi-agent content production pipeline for Xiaohongshu (RED) operators — a Collector (LLM keyword expansion + Playwright scraping), a Judge (deterministic scoring + LLM topic generation), and an Executor (tutorial / skill / PPT three-track content assembly), orchestrated in Python with a zero-dependency PHP + static-HTML local dashboard.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![PHP](https://img.shields.io/badge/PHP-7.4%2B-777BB4)](https://www.php.net/)
[![Stack](https://img.shields.io/badge/Stack-Python%20%7C%20LLM%20%7C%20Playwright%20%7C%20PHP-orange)]()

---

## 这是什么（30 秒概览）

- **三智能体架构**：`收集智能体` 扩词+抓爆款 → `判断智能体` 评分排序+生成选题 → `执行智能体` 按三轨（AI 教程 / Skill 分享 / PPT 模板）生成笔记成品
- **混合决策**：评分用纯 Python 规则（快、确定、零 token），LLM 只做爆款模式提炼与选题生成
- **零框架看板**：根目录静态 `index.html` + 单文件只读 `api.php`，`php -S` 一键起本地内容工坊页面，无需数据库
- **断点续跑**：每一步都落 JSON 文件（`collected.json → judged.json → produced.json`），任何环节中断后重跑命令即可从断点继续
- **真实跑通过的样板数据**：仓库内置 16 篇 produced 样板（8 skill / 4 tutorial / 4 PPT，图片因体积未入库，跑脚本即可重生成）

## 适用人群

做小红书矩阵、自媒体选题研究、AI 内容工程（AI content engineering）、多智能体工作流（multi-agent workflow）的开发者/运营；也适合当作「LLM 应用的文件型状态机」教学样本。

## 架构

```
┌─────────────┐   关键词库+爆款样本   ┌─────────────┐   带优先级选题清单   ┌─────────────┐
│ 01 收集智能体 │ ───────────────────→ │ 02 判断智能体 │ ──────────────────→ │ 03 执行智能体 │
│  Collector   │                      │   Judge     │                     │  Executor   │
│ LLM扩词+爬取  │                      │ 规则评分+LLM │                     │ 三轨内容组装  │
└─────────────┘                      └─────────────┘                     └──────┬──────┘
      ↑ 反馈回流(点赞/收藏数据加权)                                            │
      └──────────────────────────────────────────────────────────────────────┘
                            全部状态落 data/*.json（文件型状态机）
```

## 目录结构

```
Xiaohongshu-multi-agent-workflow/
├── index.html            # 本地看板：作品墙/详情/源码查看/流程说明（三轨色标）
├── api.php               # 只读 JSON API + 图片白名单代理（单文件，无框架）
├── collect_config.yaml   # 赛道/三轨种子词/LLM provider 选择（不含密钥）
├── expand_keywords.py    # 01a 收集：种子词 → 长尾关键词（LLM）
├── scrape_xhs.py         # 01b 收集：Playwright 抓小红书爆款样本（扫码登录一次）
├── judge.py              # 02 判断：规则评分 + LLM 提炼爆款模式/生成选题
├── execute.py            # 03 执行：三轨成品组装（教程/Skill/PPT）
├── data/
│   ├── collected.json    # 关键词库 + 爆款样本
│   ├── judged.json       # 评分结果 + 选题队列
│   ├── produced.json     # 成品笔记（16 篇样板）
│   └── images/           # 生成的配图（gitignore，跑脚本生成）
└── 00_总览.md / 01~03_*.md  # 三智能体设计文档
```

## 快速开始

### 1. 环境依赖

```bash
python3 -m pip install pyyaml requests python-pptx playwright pillow
playwright install chromium
# 抓取还需要本地 PHP（macOS 自带或 brew install php）
```

### 2. 配置 LLM Provider

密钥不写进项目配置，统一放用户目录的 `~/.openclaw/openclaw.json`（代码只读 provider 名与 model 名）：

```json
{
  "models": {
    "providers": {
      "zhipu": { "apiKey": "你的智谱Key", "baseUrl": "https://open.bigmodel.cn/api/paas/v4" }
    }
  }
}
```

### 3. 跑流水线

```bash
python3 expand_keywords.py     # 01a 种子词 → 长尾词（纯 LLM，不爬站）
python3 scrape_xhs.py          # 01b 首次运行弹浏览器扫码登录，之后 headless 复用
python3 judge.py               # 02 评分排序 + 生成选题
python3 execute.py             # 03 生成 16 篇成品到 data/produced.json
```

### 4. 打开本地看板

```bash
php -S 127.0.0.1:8080
# 浏览器打开 http://127.0.0.1:8080/index.html
```

## API 一览（api.php，全部只读）

| Action | 说明 |
|---|---|
| `?action=list` | 成品列表（三轨标记、封面、标签数） |
| `?action=post&id=xxx` | 单篇详情（步骤/正文/配图路径） |
| `?action=stats` | 各轨成品统计 |
| `?action=flow` | 三智能体流程元数据 |
| `?action=scripts` / `?action=script&name=judge.py` | 白名单脚本源码查看（防目录穿越） |
| `?action=image&path=data/images/...` | 图片代理，realpath 限制在 data 目录内 |
| `?action=md_download&id=xxx` | PPT 轨 Markdown 模板下载 |

## 设计原则

1. **人在环路（human-in-the-loop）**：系统只产出「待发布物料」，永远不调发布接口；发什么、什么时候发，人决定
2. **确定性优先**：能量化的（热度、轨道配额、优先级）用规则算，LLM 只用在需要语义的环节
3. **文件即数据库**：JSON 中间产物可读、可 diff、可手工修，重启无状态丢失
4. **密钥与仓库分离**：仓库内没有任何 API Key / Cookie；小红书登录态 `xhs_state.json` 默认 gitignore
5. **礼貌爬取**：单关键词间隔 5–8 秒、模拟滚动、单次 ≤50 条，仅用于个人市场研究

## 技术栈

Python 3.9+ · 智谱 GLM（OpenAI 兼容协议，可替换任意兼容 endpoint）· Playwright/Chromium · 阿里云百炼 `bl` CLI（文生图）· PHP 7.4+（内置 server）· 原生 HTML/CSS/JS 单页

## 常见问题（FAQ）

**Q：会不会自动发小红书？**
不会。流水线终点是本地 `produced.json` + 配图文件，复制粘贴由人完成，也不生成任何站外导流话术。

**Q：必须用智谱的模型吗？**
不是。各脚本内的 LLM 调用走标准 OpenAI 兼容协议，`~/.openclaw/openclaw.json` 里换成任意兼容服务（百炼/本地 vLLM 等）即可。

**Q：抓到的数据合规吗？**
`scrape_xhs.py` 使用你本人扫码后的登录态、限速访问、仅做个人选题研究，不做二次分发、不存储他人内容到公开仓库（图片与登录态均不入库）。

**Q：没有图片看板是空的？**
图片属于生成产物（体积大），未纳入 git。跑完 `execute.py` 后图片落到 `data/images/`，看板自动展示。

**Q：三轨内容分别是什么格式？**
tutorial = 标题+分步教程+配图；skill = 标题+skill 代码+演示输入输出；ppt = 标题+正文+python-pptx 生成的 .pptx 与页面缩略图。

## License

MIT。本仓库不含任何第三方平台素材；生成内容请自行遵守平台规则与当地法律。
