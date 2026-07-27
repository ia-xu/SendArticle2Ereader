# tex_to_kindle 变更日志

## v3.2 — Kimi Linear 论文实战驱动 (2026-07-25)

以 arXiv 2510.26692（Kimi Linear）论文为实际案例，发现并修复了以下问题：

### 1. AMS 数学子环境无限循环

**问题**：`aligned`、`cases`、`split`、`gathered` 等 AMS 子环境在 `_convert_math_env` 中被重新包裹 `$$\begin{aligned}...\end{aligned}$$`，导致 `_process_environments` 循环将其再次匹配，形成无限循环（46+ 次）。

**修复**：`_convert_math_env` 对子环境直接解包返回内部数学内容，不重新包裹。外层 `equation` 已提供 `$$`。

### 2. 复杂表格 → 图片渲染

**问题**：包含 `@{}`、`>{}`、`!{}` 列格式的表格无法转换为 Markdown，内容直接丢失。

**修复**：
- `tex2md.py`：新增 `_convert_table_env` 方法，检测复杂列格式 → 用 `\LATEXBS` 转义全部 LaTeX 命令 → 发射 `<!-- TABLE_RAW:N|caption -->` 占位符
- **新建** `scripts/table_renderer.py`：解析占位符 → 恢复转义 → standalone 编译 → PDF→PNG → 替换为 Markdown 图片引用

### 3. 代码型 figure → 图片渲染

**问题**：`figure` 环境内含 `minted`/`lstlisting` 代码而非 `\includegraphics` 时，`_convert_figure_env` 返回空字符串，代码完全丢失。

**修复**：
- `tex2md.py`：`_convert_figure_env` 增加代码检测分支 → 发射 `<!-- CODE_RAW:N|caption -->` 占位符
- **新建** `scripts/code_renderer.py`：standalone 编译（`--shell-escape` 支持 minted）→ PDF→PNG

### 4. $$ 公式配对级联错误

**问题**：一处 `$$` 未闭合会引发多米诺效应，影响后续所有公式配对。

**根因**：`_process_special_chars` 将 `\$` 转为 `USD($)`。当 `$$` 出现在行末时可能被误判为 `\$` → 产生 `\USD($)$` → 打破 `$$` 配对。

**修复**：`_process_math` 末尾增加 `content.replace('\USD($)$', '$$')`。

**调试方法（P18）**：栈式匹配找到第一个孤 `$$` → 修复根因后级联自动解除。

### 5. `\bm x` 单字符无括号形式

**问题**：`\bm a`（无 `{}`）未被转换，`\bm{...}` 已处理但 `\bm x` 漏掉。

**修复**：`re.sub(r'\\bm\s+([a-zA-Z])', r'\\boldsymbol{\1}', content)`

### 6. Python 编译警告消除

**问题**：8 处 docstring 含 `\i`、`\d`、`\e` 等非法转义序列，产生 `DeprecationWarning`。

**修复**：相关 docstring 加 `r` 前缀改为 raw string。

### 7. 孤括号清理

**问题**：`{width=1\columnwidth,center}` 等 `\includegraphics` 选项残留为孤括号。

**修复**：`_cleanup` 末尾增加 `re.sub(r'\{width=[^}]*\}', '', content)`。

### 8. 自定义颜色宏残留

**问题**：`\brickred{...}`、`\midnightblue{...}`、`\white{...}` 等 paper 自定义宏未被展开。

**修复**：`_process_math` 增加循环正则剥离这些宏，保留内部内容。

### 新增/修改文件

| 文件 | 操作 |
|------|------|
| `scripts/tex2md.py` | 修改：+120 行（3 个新方法 + 多处修复） |
| `scripts/table_renderer.py` | 新建 |
| `scripts/code_renderer.py` | 新建 |
| `SKILL.md` | 更新：v3.2 说明 + Step 3b/3c + P18 |

### 仍需 LLM 处理的手动步骤

| 问题 | 识别方式 |
|------|---------|
| prose 中 ` ``` ` 三反引号 | 搜索非代码上下文的 `` ``` `` |
| Markdown 表格中 `$\phi$` → `$$` | 表格单元格含 `$$` |
| 表格 `{rrccc}` 列格式泄漏 | 表格首行含 `{r` |
| `$...$$...$` 嵌套数学 | 行内 `$` 后紧跟 `$$` |
