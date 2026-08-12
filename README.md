# AI Detox — AI 特征诊断与去除

对任意中文学术文本（论文、课程报告、结课作业、分析报告），系统化检测 AI 写作痕迹并改写为自然学术写作的 Claude Code 技能（Skill）。

核心方法论三件套：**七层扫描框架（诊断）+ 九类特征排查清单（核对）+ 六种改写策略（治疗）**。

> 核心原则：AI 特征的关键在"信息密度和具体性"，不在表面措辞。删除一个 AI 词，必须补一个具体事实；不删不补，文字只会变弱。

## ✨ 特性

- **七层扫描框架 L1-L7**：词汇 / 句式 / 段落 / 论证逻辑 / 信息密度 / 引用文献 / 元书写，逐层定位 AI 写作痕迹
- **九类特征排查清单 + 姿势级修辞识别**：空壳词、三板斧句式、过渡招牌、空洞概括、AI 高频标点、万能逻辑链、风格句式、黑话词汇替换、快速自测，另加翻案腔 / 抒情借喻 / 同构排比 / 动词名词化等"动作级"识别
- **结构统计层**：句长变异系数、连词密度、"的"字长句、同字排比、「」金句密度、借喻簇、短段连击 7 项统计检查
- **六种改写策略 S1-S6**：词汇替换、句式破形、段落重塑、论证深化、信息增密、元书写清理（含段落作用标记与材料来源标注）
- **零依赖确定性扫描器**：`scripts/scan.py` 仅用 Python 标准库，任何环境 `python3` 即跑
- **可扩展特征词库**：`data/ai-patterns.json` 含 147 条模式（层级 / 风险等级 / 替换建议 / 启用开关 / 语境判定），可自行追加条目
- **触发场景**：降 AI 率、AIGC 检测后修改、去除 AI 味、AI 特征扫描、论文查重前改写、AI 话术避坑、知网 AIGC 检测报告处理

## 📦 安装（Claude Code 插件）

```bash
# 添加市场（GitHub 仓库）
claude plugin marketplace add ixiuluo/ai-detox
```

然后在 Claude Code 中打开 `/plugin`，找到 `ai-detox` 并启用。

> 已安装用户更新：`claude plugin update ai-detox`（重启后生效）。

## 🚀 快速使用

安装启用后，直接描述需求即可触发，例如：

- "帮我扫描这段论文的 AI 特征"
- "这篇结课报告要降 AI 率，改写一下"
- "处理知网 AIGC 检测报告标记的段落"

### 命令行扫描器（Phase 1 确定性扫描）

```bash
# 以 $CLAUDE_SKILL_DIR 定位 skill 目录（Claude Code 自动注入），或直接 cd 到仓库目录
python3 "$CLAUDE_SKILL_DIR/scripts/scan.py" 论文.txt                          # 扫描文件
python3 "$CLAUDE_SKILL_DIR/scripts/scan.py" --text "待扫描文本"               # 扫描命令行文本
python3 "$CLAUDE_SKILL_DIR/scripts/scan.py" 论文.txt --json                  # 输出 JSON 报告
python3 "$CLAUDE_SKILL_DIR/scripts/scan.py" 论文.txt --min-severity medium   # 只看中危以上
python3 "$CLAUDE_SKILL_DIR/scripts/scan.py" 论文.txt --dict 自定义词库.json    # 自定义词库
```

## 📂 文件结构

```
ai-detox/
├── .claude-plugin/
│   ├── marketplace.json      # 插件市场清单
│   └── plugin.json           # 插件清单（版本 / 授权 / 来源）
├── SKILL.md                  # 方法论：七层扫描、九类清单、六种改写策略
├── data/
│   └── ai-patterns.json      # 特征词库（147 条模式，机器可读）
├── scripts/
│   └── scan.py               # 确定性扫描器（Phase 1）
├── LICENSE                   # MIT
└── README.md
```

## 🔧 词库扩展

`data/ai-patterns.json` 中每条模式含 `id / type / pattern / flags / layer / category / severity / suggestion / enabled`。发现新 AI 特征可追加条目；某条规则误报过多可将 `enabled` 置 `false` 临时关闭，无需删除。

## 🧠 方法论概览

```
输入文本
   │
   ▼
① 七层扫描 L1-L7   → Phase 1: scripts/scan.py 词库确定性命中
                       Phase 2: Claude 按 L1-L7 做上下文/逻辑盲审
   │
   ▼
② 按策略改写 S1-S6  → 从最上层(元书写/词汇)到底层(密度/论证)依次处理
   │
   ▼
③ 复检对比          → 再次七层扫描，对比前后评分，逐项确认高危特征消除
   │
   ▼
输出：改写后文本 + 诊断报告
```

高危优先级：**L7 元书写 > L1 词汇 > L5 密度 > L3 段落**。先删承诺预告，再替换词汇，再增密，最后重塑段落。

## 📄 开源协议

[MIT](LICENSE) © ixiuluo
