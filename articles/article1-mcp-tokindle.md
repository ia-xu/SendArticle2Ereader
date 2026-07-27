# 我做了一个 MCP 小工具：跟 AI 说句话，就能把任何文章导入 Kindle

> 这是系列文章的第一篇。整个系列讲一个核心问题：**怎么让电子阅读器（Kindle 等）能方便地读任何网上内容**——知乎长文、微信公众号、arXiv 论文，甚至你自己写的 Markdown 笔记。

## 痛点：电子阅读器很好，但导入内容太麻烦了

你可能也有类似经历：

刷知乎看到一篇深度好文，想细细品读，但手机屏幕太累眼。你心想：「要是能在 Kindle 上看就好了。」

于是你开始折腾：复制全文 → 找排版工具 → 转格式 → 传到设备。等你弄完，阅读的兴致已经少了一半。

微信公众号文章也一样。收藏了十几篇「稍后阅读」，再也没打开过——因为手机上读长文体验实在太差。

更别提 arXiv 论文了。PDF 在 Kindle 上重排后排版惨不忍睹，公式变成天书。

**问题的本质是：从「看到一篇好文章」到「在阅读器上打开它」，中间的链路太长了。**

## 我的方案：一个 MCP 工具 + AI Agent = 一句话导入

我做了个开源工具叫 **SendArticle2Kindle**（Tokindle），它是一个 [MCP（Model Context Protocol）](https://modelcontextprotocol.io/) 服务器。

MCP 是什么？简单说，它是一套协议，让 AI Agent（比如 Claude Desktop、Hermes Agent）能调用外部工具。你把这个工具配好之后，**只需要对 AI 说一句话**，它就帮你完成下载、格式转换、推送的全流程。

### 实际体验长什么样

假设你已经配置好了 Hermes Agent（或 Claude Desktop），你的日常操作是这样的：

**场景一：知乎文章**

你在微信/浏览器里看到一篇知乎专栏文章，把链接甩给 Agent：

> 我：下载这篇知乎文章，转成 KFX https://zhuanlan.zhihu.com/p/xxxxxx

Agent 自动抓取全文、转换格式、生成电子书文件。等你回家把 Kindle 和电脑一插：

> 我：把这篇文章推送到 Kindle

搞定。第二天通勤路上直接打开看。

**场景二：微信公众号**

> 我：把这篇微信文章转成电子书 https://mp.weixin.qq.com/s/xxxxxx

同样，一键搞定。图片、排版、代码块都保留。

**场景三：批量导入**

攒了一周的好文章，一次性处理：

> 我：批量下载这几篇：
> - https://zhuanlan.zhihu.com/p/111
> - https://mp.weixin.qq.com/s/222
> - https://zhuanlan.zhihu.com/p/333

Agent 并行下载转换，几分钟后全部就绪。

## 工具做了什么

整个流程分三步：

```
URL（知乎 / 微信 / arXiv）
  │
  ▼  文章下载器（自动抓取 + 转 Markdown）
  │
  ▼  Markdown 文件（.md，包含公式、图片、代码块）
  │
  ▼  md2kfx 转换器
  │
  ▼  EPUB + KFX（自动目录、公式渲染、代码转图片）
  │
  ▼  推送到阅读器
```

### 下载器支持

| 来源 | 说明 |
|------|------|
| 知乎 | 专栏文章 + 问题回答，保留公式和图片 |
| 微信公众号 | 需要配置公众号 Cookie |
| arXiv | 支持 HTML 页面和 TeX 源码两种模式 |
| 本地文件 | 任何 .md 文件都可以直接上传转换 |

### 转换器亮点

**数学公式**：LaTeX 公式（`$E=mc^2$`）转为 MathML 渲染，不是纯文本。这在阅读学术论文时尤其重要。

**代码块**：带语法高亮的代码块自动转为图片，适配墨水屏尺寸，不会出现排版错乱。

**图片处理**：远程图片自动下载嵌入，GIF/WebP 自动转 PNG，PDF 图表也能提取。

**目录生成**：标题层级自动生成可导航目录。

## 怎么配置

### 1. 安装工具

```bash
git clone https://github.com/ia-xu/SendArticle2Kindle.git
cd SendArticle2Kindle
pip install -r requirements.txt
```

### 2. 安装 KFX 依赖（Kindle 用户）

转换 KFX 格式需要三个组件：

- **Calibre**（格式转换）→ [官网下载](https://calibre-ebook.com/download)
- **Kindle Previewer 3**（KFX 渲染引擎）→ [Amazon 下载](https://www.amazon.com/Kindle-Previewer/b?ie=UTF8&node=21381691011)
- **KFX Output 插件**（连接 Calibre 和 Previewer）→ 在 Calibre 插件管理中安装

> 如果你的阅读器支持 EPUB（文石 Boox、Kobo 等），跳过这步，EPUB 转换不需要额外依赖。

### 3. 配置到 AI Agent

以 Hermes Agent 为例，在 `config.yaml` 中添加：

```yaml
mcp_servers:
  tokindle:
    command: /path/to/your/python
    args:
      - /path/to/tokindle/mcp_server.py
      - --transport
      - stdio
```

Claude Desktop 用户编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "tokindle": {
      "command": "/path/to/your/python",
      "args": ["/path/to/tokindle/mcp_server.py", "--transport", "stdio"]
    }
  }
}
```

配置完成后重启 Agent，就可以直接在对话中使用了。

## 实际用了一段时间的感受

最大的变化是**导入链路从「不想折腾」变成了「随手导入」**。

以前看到一个公式密集的知乎回答，心想「这个想在 Kindle 上看」，但一想到要手动复制、排版、转格式，就放弃了。现在直接把链接甩给 Agent，几秒钟就处理好了。

下载和转换都是自动的，我只需要在 Kindle 连接电脑时说一句「推送」，其他什么都不用管。

**最有成就感的瞬间**：把一篇 arXiv 论文完整导入 Kindle，公式渲染正常，图表清晰，目录可导航——这在以前是想都不敢想的体验。

## 支持的设备

| 设备 | 推荐格式 | 说明 |
|------|---------|------|
| Kindle 系列 | KFX | 增强排版，支持公式渲染 |
| Kindle Paperwhite 6+ | KFX / EPUB | MTP 模式需额外配置 |
| 文石 Boox / Kobo / reMarkable | EPUB | 原生支持，无需额外组件 |

## 下篇预告

这篇文章讲了基础的文章导入流程。但如果你想在阅读器上读 **arXiv 学术论文**——那些充满数学公式的 PDF——故事会更精彩。

下一篇，我会介绍如何用这个工具把 arXiv 论文的 **TeX 源码**转成 Kindle 可读的格式，包括公式如何渲染、图表怎么处理、以及一套自动生成中文论文导读的流程。

---

项目地址：[GitHub - SendArticle2Kindle](https://github.com/ia-xu/SendArticle2Kindle)

更多配置细节见项目 README。
