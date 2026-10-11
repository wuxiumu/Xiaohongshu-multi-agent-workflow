# 品类配置档

这些 yaml 是交付给客户前的简报，**不会被脚本自动加载**。

定制时复制一份，改 `niche`、`seed_keywords`、`banned_topics`、`tone`、`brand`，再把种子词手工抄进仓库根目录的 `collect_config.yaml`（`tracks.tutorial` / `skill` / `ppt` 的 `seeds`）。评分权重和成稿提示词仍在 `judge.py`、`execute.py`，文件头有 `EXTENSION` 标记。
