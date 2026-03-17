# toKindle

将网络文章转换为 Kindle 友好格式的工具集。

## 功能模块

### 1. zhihu2markdown - 知乎专栏文章转 Markdown

将知乎专栏文章抓取并转换为 Markdown 格式，保留图片原始 URL、公式和代码块。

#### 安装依赖

```bash
pip install requests beautifulsoup4

# 可选：浏览器模式需要
pip install playwright
playwright install chromium
```

#### 使用方法

**第一步：登录获取 Cookie（推荐）**

```bash
# 交互式登录，会打开浏览器让你手动登录
python src/zhihu2markdown.py login
```

登录成功后，Cookie 会自动保存到 `config/zhihu_cookies.json`。

其他登录方式：

```bash
# 从浏览器复制 Cookie 字符串
python src/zhihu2markdown.py login -c "z_c0=xxx; _xsrf=yyy"

# 检查登录状态
python src/zhihu2markdown.py login --check
```

**第二步：爬取文章**

```bash
# 基本用法（使用已保存的 Cookie）
python src/zhihu2markdown.py fetch https://zhuanlan.zhihu.com/p/123456789

# 指定输出目录
python src/zhihu2markdown.py fetch https://zhuanlan.zhihu.com/p/123456789 -o ./output

# 强制使用浏览器模式（应对反爬）
python src/zhihu2markdown.py fetch https://zhuanlan.zhihu.com/p/123456789 --browser
```

#### 支持的 URL 格式

- 专栏文章：`https://zhuanlan.zhihu.com/p/123456789`
- 问题回答：`https://www.zhihu.com/question/xxx/answer/yyy`

#### 输出格式

- 图片保留原始 URL（知乎图床），不下载到本地
- 公式转换为 LaTeX 格式
- 代码块保留语法高亮标记

示例输出：

```markdown
# 文章标题

![](https://pic1.zhimg.com/v2-xxx_r.jpg)

正文内容...

$$
\mathbf{S}_t = \mathbf{S}_{t-1} + \mathbf{v}_t\mathbf{k}_t^\top
$$

\`\`\`python
print("Hello")
\`\`\`
```

#### 命令一览

```
python src/zhihu2markdown.py login              # 交互式登录
python src/zhihu2markdown.py login -c "cookie"  # 从字符串导入 Cookie
python src/zhihu2markdown.py login --check      # 检查登录状态
python src/zhihu2markdown.py fetch <url>        # 爬取文章
python src/zhihu2markdown.py fetch <url> -o dir # 指定输出目录
python src/zhihu2markdown.py fetch <url> --browser  # 浏览器模式
```

---

### 2. wechat2markdown - 微信公众号文章转 Markdown

将微信公众号文章抓取并转换为 Markdown 格式，保留图片原始 URL、代码块等。

#### 安装依赖

```bash
pip install requests beautifulsoup4

# 浏览器模式需要
pip install playwright
playwright install chromium
```

#### 使用方法

**设置 Cookie（可选，部分文章需要）**

```bash
# 交互式登录（会打开浏览器让你扫码登录微信）
python src/downloader/wechat2markdown.py login

# 从浏览器复制 Cookie 字符串
python src/downloader/wechat2markdown.py login -c "cookie字符串"

# 检查登录状态
python src/downloader/wechat2markdown.py login --check
```

**爬取文章**

```bash
# 使用文章 URL
python src/downloader/wechat2markdown.py fetch "https://mp.weixin.qq.com/s/xxx"

# 使用搜索关键词（通过搜狗微信搜索）
python src/downloader/wechat2markdown.py fetch "Python 教程"

# 指定输出目录
python src/downloader/wechat2markdown.py fetch "https://mp.weixin.qq.com/s/xxx" -o ./output
```

#### 支持的输入格式

- 微信文章链接：`https://mp.weixin.qq.com/s/xxx`
- 搜索关键词：直接输入文章标题或关键词搜索

#### 输出格式

- 图片保留原始 URL（微信图床），不下载到本地
- 代码块保留格式
- 视频、音频保留链接

#### 命令一览

```
python src/downloader/wechat2markdown.py login -c "cookie"  # 设置 Cookie
python src/downloader/wechat2markdown.py fetch <url>       # 爬取文章
python src/downloader/wechat2markdown.py fetch <url> -o dir # 指定输出目录
```

---

### 3. md2markdown_v4 - Markdown 转 KFX

将 Markdown 文件转换为 Kindle KFX 格式。

#### 使用方法

```bash
python src/md2markdown_v4.py input.md -o output.kfx -a "作者名"
```

#### 依赖

```bash
pip install markdown beautifulsoup4 requests EbookLib pygments latex2mathml
```

需要安装 [Calibre](https://calibre-ebook.com/) 以支持 KFX 转换。

---

## 目录结构

```
tokindle/
├── src/
│   ├── downloader/
│   │   ├── zhihu2markdown.py    # 知乎文章爬取
│   │   └── wechat2markdown.py  # 微信公众号爬取
│   └── md2markdown_v4.py       # Markdown 转 KFX
├── config/
│   ├── zhihu_cookies.json      # 知乎登录 Cookie（自动生成）
│   └── wechat_cookies.json     # 微信 Cookie（可选）
└── requirements.txt
```

## 常见问题

### Q: 提示 401/403 错误？

A: 需要先登录获取 Cookie：

```bash
python src/zhihu2markdown.py login
```

### Q: 如何获取 Cookie 字符串？

A:
1. 浏览器登录知乎
2. F12 打开开发者工具
3. 切换到 Network 标签
4. 刷新页面，找到任意请求
5. 在 Headers 中找到 Cookie 值并复制

### Q: 图片无法显示？

A: 图片保留知乎原始 URL，需要网络访问。知乎图片可能需要正确的 Referer 才能显示。

### Q: 微信公众号文章无法抓取？

A: 微信公众号文章可能需要特殊处理：
1. 确保文章是公开的（未设置权限）
2. 尝试使用浏览器模式抓取
3. 某些文章可能需要微信登录 Cookie

## License

MIT


# 
# https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
