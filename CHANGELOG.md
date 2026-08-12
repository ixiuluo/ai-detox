# Changelog

所有重要变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-08-12

### 新增
- 首个公开发布，作为 Claude Code 插件分发。
- 七层扫描框架（L1-L7）：词汇 / 句式 / 段落 / 论证逻辑 / 信息密度 / 引用文献 / 元书写。
- 九类 AI 特征排查清单（空壳词、三板斧句式、过渡招牌、空洞概括、标点、逻辑链、风格句式、黑话词汇替换、自测清单）。
- 六种改写策略（S1-S6）：词汇替换、句式破形、段落重塑、论证深化、信息增密、元书写清理。
- 确定性扫描器 `scripts/scan.py`：Python 标准库零依赖，支持文件 / `--text` / `--json` / `--min-severity` / `--dict`。
- 特征词库 `data/ai-patterns.json`：106 条模式，含层级 / 严重级别 / 替换建议 / 启用开关。
