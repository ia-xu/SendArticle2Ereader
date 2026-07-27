# 让 arXiv 论文在 Kindle 上 readable：TeX 源码转电子书的完整方案

> 这是系列文章的第三篇。[第一篇](article1-mcp-tokindle.md)介绍了 MCP 工具的基础用法，[第二篇](article2-bilingual-books.md)讲了双语书制作。这一篇是最硬核的部分：**把充满数学公式的 arXiv 论文，变成 Kindle 上阅读体验良好的电子书**。

## 为什么 arXiv 论文在电子阅读器上那么难读

如果你试过在 Kindle 上读 arXiv 论文，大概率经历过这些痛苦：

**PDF 直传——排版灾难。** Kindle 屏幕就那么大，PDF 的 A4 比例根本不适合竖屏阅读。缩小看不清公式，放大要来回滑动。重排功能？公式位置全乱了。

**arXiv 的 HTML 版——聊胜于无。** arXiv 现在提供了 HTML 渲染，但阅读体验一般：公式渲染依赖浏览器，图片经常丢失，排版不够紧凑，长公式溢出屏幕。

**核心问题是公式。** 一篇普通的机器学习论文可能有上百个公式，从简单的 $\sum_{i=1}^N x_i$ 到复杂的矩阵推导 $\mathbf{S}_t = \alpha_t(\mathbf{I} - \beta_t \mathbf{k}_t \mathbf{k}_t^\top)\mathbf{S}_{t-1}$。这些公式如果在 Kindle 上渲染不出来或者乱码，整篇文章就没法读。

## 我的思路：从 TeX 源码出发，不走 PDF

关键洞察是：**arXiv 论文的原生格式是 LaTeX，不是 PDF**。PDF 是排版终产物，已经丢失了结构信息。而 TeX 源码包含完整的章节结构、公式语义、图表引用——这才是转换的最佳起点。

arXiv 允许下载论文的 TeX 源码压缩包。我的工具链做的事就是：

```
TeX 源码 (.tex)
  │
  ├── 解析多文件 \input{} 结构
  ├── 展开自定义宏（\newcommand）
  ├── 数学环境 → $$...$$（保留原始 LaTeX）
  ├── PDF 图表 → PNG（pymupdf 渲染）
  ├── 表格、算法块、定理环境 → Markdown
  │
  ▼
Markdown 文件（结构完整，公式保留为 LaTeX）
  │
  ├── LaTeX 公式 → MathML（latex2mathml）
  ├── 代码块 → 语法高亮图片
  ├── 自动生成目录
  │
  ▼
EPUB / KFX → 推送到 Kindle
```

## 关键技术细节

### 1. 宏展开：处理论文作者的「私货」

学术论文作者都喜欢定义自己的宏命令。比如：

```latex
\newcommand{\bm}[1]{\boldsymbol{#1}}
\newcommand{\S}{\mathbf{S}}
\newcommand{\model}{SAO}
```

如果不展开这些宏，转换后的 Markdown 里会到处都是 `\bm{k}_t` 这样的未解析命令，latex2mathml 处理不了。

`tex2md.py` 脚本会在转换前提取所有 `\newcommand` 和 `\def` 定义，然后用**词边界匹配**展开。所谓词边界匹配，就是展开 `\mat` 宏时不会误匹配到 `\mathbb`——这是个容易踩的坑。

### 2. 公式保留：不做任何「翻译」

很多 Markdown 转换工具会把 `$\alpha$` 转成 Unicode 字符 `α`。看似方便，但实际上：

- `\mathbf{S}` 转成什么？加粗的 S？Unicode 没有数学粗体。
- `\sum_{i=1}^N` 转成 `Σᵢ₌₁ᴺ`？在 Kindle 上显示惨不忍睹。
- `\frac{a}{b}` 转成什么？Unicode 根本不支持分数。

**正确做法是保留原始 LaTeX**，让后续的 `latex2mathml` 把 `$\frac{a}{b}$` 转成结构化的 MathML：

```xml
<mfrac>
  <mi>a</mi>
  <mi>b</mi>
</mfrac>
```

Kindle 的 KFX 引擎能渲染 MathML，公式效果接近原生 LaTeX 排版。

支持的 LaTeX 命令包括：

| 类型 | 示例 |
|------|------|
| 希腊字母 | `\alpha`, `\theta`, `\epsilon` |
| 分数/根号 | `\frac{a}{b}`, `\sqrt{x}` |
| 求和/积分 | `\sum_{i=1}^N`, `\int_0^\infty` |
| 矩阵/向量 | `\mathbf{S}`, `\boldsymbol{\alpha}` |
| 条件分支 | `\begin{cases}...\end{cases}` |
| 对齐公式 | `\begin{aligned}...\end{aligned}` |
| 取消线 | `\cancel{x}`, `\bcancel{x}` |

### 3. 图表处理：PDF → PNG

arXiv 论文的图表通常是 PDF 格式（矢量图）。`tex2md.py` 使用 pymupdf（fitz）将每个 PDF 图表渲染为 200 DPI 的 PNG，在 Kindle 上清晰可辨。

对于使用 TikZ/pgfplots **内联绘图**的论文（图表代码直接写在 .tex 里，而不是引用外部 PDF），脚本会检测并提示你手动处理——通常的做法是直接从论文 PDF 中截取对应图表区域。

### 4. 公式分隔符校验：防止「一个 $$ 毁掉全书」

这是我在实际使用中遇到的最坑的问题。

TeX 转 Markdown 的过程中，偶尔会产生**配对错误的 `$` / `$$` 标记**。比如一个行内公式的结尾被误写成了 `$$`：

```markdown
Additionally, $\mathcal{A}_{[t]} \in \mathbb{R}^{C\times C}$$ is the matrix...
```

这个多余的 `$$` 会让后续所有块级公式的配对全部错位。结果是：两段公式之间的**英文正文被当成公式内容**，送进 latex2mathml 转换，每个英文字母变成一个 `<mi>` 标签——

```xml
<mi>i</mi><mi>s</mi><mi>t</mi><mi>h</mi><mi>e</mi>
```

这就是「isthe」被当成数学公式了。一篇正常论文可能因此产生 4 万多个垃圾 MathML 元素，直接让 Kindle Previewer 3 崩溃。

**解决方案**是一个预检脚本 `check_math_delimiters.py`：

```bash
python scripts/check_math_delimiters.py paper.md
```

它会扫描整个 Markdown 文件，检查：

| 检查项 | 说明 |
|--------|------|
| `ODD_DD_COUNT` | `$$` 数量为奇数 → 有未配对的块级公式 |
| `ODD_D_COUNT` | `$` 数量为奇数 → 有未配对的行内公式 |
| `STRAY_DD` | 行中间出现 `$$`（应该是 `$`） |
| `MISPAIRED_DD` | `$$` 对内包含标题/正文（非公式内容） |

发现问题后，AI Agent 读取报告，定位到具体行号，修复 `$` 配对，然后重新检查。整个过程全自动，不需要你手动排查。

## 自动生成中文论文导读

光把论文导入 Kindle 还不够。面对一篇 40 页的英文论文，打开后不知道重点在哪。

我的工具链里有一个 **AI 论文导读** 功能。Agent 会读取完整的论文 Markdown，按照一套 12 节分析框架，用**中文**生成导读，然后拼在论文原文前面：

```
---
## 中文导读（AI 生成）

### 1. 研究问题与动机
这篇论文要解决的核心问题是...

### 2. 前人工作及其不足
之前的方法主要有...

### 3. 重建作者的思考路径
作者为什么要这么设计？关键转折点在于...

...（共 12 节）

---
## 论文原文（英文，原封不动）

# Kimi Linear: An Expressive, Efficient Attention Architecture
...
```

**12 节框架**包括：

1. 研究问题与动机
2. 前人工作及其不足
3. **重建作者的思考路径**（最重要的一节）
4. 核心思想精炼
5. 方法流程与实例
6. 数学基础
7. 实验设计
8. 关键收获
9. 最脆弱的假设
10. 最小复现方案
11. 攻击向量
12. Follow-up 研究方向

不是被动摘要，而是带着批判性思维去分析论文。每一条论断标注来源：`[paper]` 原文说的、`[literature]` 文献引用的、`[inference]` 推断的、`[speculation]` 猜测的。

## 实战：Kimi Linear 论文转换全流程

拿最近 Moonshot 的 Kimi Linear 论文做一次完整演示：

**Step 1：下载 TeX 源码**

```bash
curl -L -o kimi.tar.gz "https://arxiv.org/src/2607.07508"
tar xzf kimi.tar.gz -C /tmp/kimi-paper/
```

**Step 2：TeX → Markdown**

```bash
python skills/tex_to_kindle/scripts/tex2md.py \
  --tex-dir /tmp/kimi-paper/ \
  --output kimi-linear.md \
  --title "Kimi Linear" --author "Kimi Team"
```

**Step 3：公式分隔符检查**

```bash
python scripts/check_math_delimiters.py kimi-linear.md
```

这次检查发现了 8 个问题：一个 stray `$$`（应该是 `$`）、一个孤立 `$`、两个 orphan `$$` 行。全部修复后重新检查，0 issues。

**Step 4：AI 中文导读**

跟 Hermes Agent 说：「读这篇论文，生成 12 节中文导读，拼在论文前面」。

**Step 5：转 KFX**

```bash
python src/md2kfx.py kimi-linear-with-guide.md -o kimi-linear.kfx -a "Kimi Team"
```

**结果**：1.58 MB 的 KFX 文件，公式渲染正常，图表清晰，目录可导航。在 Kindle 上阅读体验和看 HTML 版论文差不多，但更舒适——没有浏览器干扰，专注阅读。

## 效果对比

| 维度 | PDF 直传 | arXiv HTML | 本方案 |
|------|---------|-----------|--------|
| 公式渲染 | 图片（不缩放看不清） | MathJax（依赖浏览器） | MathML（KFX 原生渲染） |
| 排版适配 | 差（A4 比例） | 一般 | 好（自适应） |
| 图表质量 | 取决于 PDF | 取决于浏览器 | 200 DPI PNG |
| 目录导航 | 无 | 有（但层级浅） | 有（完整层级 + 锚点） |
| 中文导读 | 无 | 无 | 有（12 节 AI 分析） |
| 代码块 | 纯文本 | 纯文本 | 语法高亮图片 |
| 离线阅读 | 支持 | 不支持 | 支持 |

## 工具链总览

```
skills/tex_to_kindle/
├── scripts/
│   ├── tex2md.py                # TeX → Markdown 转换器
│   └── check_math_delimiters.py # 公式分隔符检查
├── templates/
│   └── paper_analysis.md        # 12 节论文导读模板
└── SKILL.md                     # 完整工作流文档
```

## 总结

把 arXiv 论文导入 Kindle，核心难点不在「下载」而在**公式和图表的转换质量**。

本方案的关键设计决策是：

1. **从 TeX 源码出发**，而不是从 PDF 或 HTML——保留最多结构信息
2. **公式保留为 LaTeX**，不做 Unicode 翻译——让 MathML 引擎做专业渲染
3. **转换前校验公式分隔符**——一个预检脚本避免灾难性的配对错误
4. **AI 生成中文导读**——降低英文论文的阅读门槛

这套流程我已经用它转换了多篇论文（线性注意力、RL 训练、DPLR 矩阵），公式渲染和阅读体验都达到了实用水平。

---

项目地址：[GitHub - SendArticle2Kindle](https://github.com/ia-xu/SendArticle2Kindle)

系列文章：
- [第一篇：一个把 Markdown 导入电子书的 MCP 小工具](article1-mcp-tokindle.md)
- [第二篇：用 AI Agent 制作双语对照电子书](article2-bilingual-books.md)
- **第三篇：arXiv 论文 TeX 转电子书完整方案**（本文）
