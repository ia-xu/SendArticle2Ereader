# MCP Server for tokindle

基于 [FastMCP](https://github.com/jlowin/fastmcp) 实现的 MCP 服务，将 Markdown 文章下载、转换为 KFX/EPUB 并推送到墨水平板。

## 快速开始

### 启动方式

**SSE 模式**（默认，HTTP 长连接，适合调试和远程调用）：

```bash
python mcp_server.py
```

服务监听 `127.0.0.1:48000`。

**stdio 模式**（标准输入输出，适合 AI agent 自启动）：

```bash
python mcp_server.py --transport stdio
```

### 配置 AI Agent 自启动

以 Claude Desktop 为例，编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "tokindle": {
      "command": "/path/to/your/python",
      "args": ["/path/to/tokindle/mcp_server.py", "--transport", "stdio"],
      "env": {}
    }
  }
}
```

AI agent 会自动启动该进程，通过 stdin/stdout 的 JSON-RPC 协议通信，无需手动启动服务。

---

## API 参考

所有工具返回统一的响应结构：`{"success": bool, ...}`。`success=false` 时附带 `error` 字段说明失败原因。

### 内容获取

#### `download_and_convert`

从 URL 下载文章并转换为 KFX/EPUB。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | `str` | 是 | 文章链接（知乎 / 微信公众号 / arXiv） |
| `title` | `str` | 否 | 自定义标题，不传则从正文自动提取 |
| `author` | `str` | 否 | 自定义作者，不传则从正文自动提取 |

返回示例：

```json
{
  "success": true,
  "file_id": "a1b2c3d4",
  "title": "文章标题",
  "author": "作者名",
  "source": "zhihu",
  "has_kfx": true,
  "has_epub": true,
  "status": "converted",
  "message": "下载并转换成功"
}
```

#### `batch_download_and_convert`

批量并行下载多篇文章，参数与单篇一致但以列表形式传入。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `urls` | `list[str]` | 是 | 文章链接列表 |
| `titles` | `list[str]` | 否 | 标题列表，与 urls 一一对应 |
| `authors` | `list[str]` | 否 | 作者列表，与 urls 一一对应 |

返回示例：

```json
{
  "success": true,
  "total": 3,
  "success_count": 2,
  "failed_count": 1,
  "results": [...],
  "message": "完成 2/3 篇文章下载转换"
}
```

#### `upload_local_file`

上传本地 Markdown 文件并转换。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_path` | `str` | 是 | 本地 `.md` 文件的绝对路径 |
| `title` | `str` | 否 | 自定义标题 |
| `author` | `str` | 否 | 自定义作者 |

#### `batch_upload_local_files`

批量上传本地 Markdown 文件。参数与单文件一致但以列表形式传入。

### 文件管理

#### `list_files`

列出数据库中所有已下载/已转换的文件。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `status` | `str` | 无 | 按状态过滤：`uploaded` / `converted` / `converted_epub` |
| `source` | `str` | 无 | 按来源过滤：`zhihu` / `wechat` / `arxiv` / `upload` |
| `limit` | `int` | `50` | 最大返回条数，`0` 不限制 |

#### `search_files`

按关键字搜索文件标题。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `keyword` | `str` | — | 搜索关键字 |
| `check_kindle` | `bool` | `false` | 是否同时检查文件是否已在 Kindle 上 |

#### `get_file_info`

获取单个文件的详细信息，包括转换状态、文件路径、是否已在 Kindle 等。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_id` | `str` | 是 | 文件 ID |

#### `delete_file`

删除本地文件及数据库记录。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `file_id` | `str` | — | 文件 ID |
| `remove_from_kindle` | `bool` | `false` | 是否同时从 Kindle 删除 |

### Kindle 设备操作

#### `check_kindle_connection`

检查墨水平板是否通过 USB 连接到电脑。返回设备挂载路径和连接状态。

#### `send_to_kindle`

将文件推送到墨水平板。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `file_id` | `str` | — | 文件 ID |
| `format` | `str` | `"kfx"` | 推送格式：`kfx` 或 `epub` |

#### `delete_from_kindle`

从墨水平板删除文件及关联的 SDR 文件夹。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_id` | `str` | 是 | 文件 ID |

#### `list_kindle_files`

列出墨水平板上所有 KFX/EPUB 文件。

---

## 工作流程

整个服务围绕一条核心链路运转：**获取 Markdown → 转换格式 → 管理文件 → 推送到设备**。

### 1. 内容获取（下载 / 上传）

**URL 下载**：`download_and_convert` 和 `batch_download_and_convert` 接收文章链接后，按 URL 域名自动分发到对应下载器：

- **知乎** (`zhihu2markdown`)：优先使用已保存的 Cookie 以无头模式抓取；若 cookie 失效则回退到 Playwright 浏览器模拟登录
- **微信公众号** (`wechat2markdown`)：使用 Playwright 浏览器抓取，自动展开被折叠的内容
- **arXiv** (`arxiv2markdown`)：通过 arXiv API 获取论文元数据和 PDF，转为 Markdown 引用格式

**本地上传**：`upload_local_file` 将本地 `.md` 文件复制到 `uploads/` 目录。标题和作者优先使用调用者指定的值，否则按顺序从 YAML frontmatter、第一个 `#` 标题、文件名逐级降级提取。如果文件同目录下存在 `images/` 文件夹，会一并复制保留图片引用。

每个文件在系统中获得一个 8 位 UUID 作为唯一标识（`file_id`）。

### 2. 格式转换

获取到 Markdown 文件后，`MarkdownToKFX` 转换器接手：

1. 解析 Markdown 中的图片引用、表格、公式（LaTeX）
2. 使用 Calibre 的 `ebook-convert` 生成 EPUB，再通过 Kindle Previewer 转为 KFX
3. 如果用户配置中启用了 EPUB 支持（`enable_epub_support`，默认开启），同时保留一份 EPUB 副本

转换结果写入 `output/` 目录，状态更新到 `database.json`。

### 3. 文件管理

所有文件元数据存储在项目根目录的 `database.json`（JSON 文件）中，包含标题、作者、来源、转换状态、上传时间等字段。`search_files`、`list_files`、`get_file_info` 和 `delete_file` 都直接操作该数据库，配合文件系统的增删来完成管理。

### 4. Kindle 推送

当墨水平板通过 USB 连接到电脑时，`send_to_kindle` 将 `output/` 下的 KFX 或 EPUB 文件复制到 Kindle 的 `documents/` 目录，Kindle 会自动识别并导入。`delete_from_kindle` 则同时删除文件及其配套的 SDR（阅读进度/标注）文件夹。
