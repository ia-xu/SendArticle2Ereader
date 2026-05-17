# Windows 下配置 mcp-chrome-bridge

## 1. 安装 mcp-chrome-bridge

### 基本安装命令

```bash
npm install -g mcp-chrome-bridge
```

### 处理 better-sqlite3 编译问题

在 Windows 上安装时，经常会遇到 `better-sqlite3` 原生模块编译失败的问题：

```
gyp ERR! find VS could not find a version of Visual Studio 2017 or newer to use
```

这是因为缺少 Visual Studio 构建工具。解决方案是使用预编译的 `better-sqlite3.node` 文件。

#### 步骤 1：跳过构建脚本安装

```bash
npm install -g mcp-chrome-bridge --ignore-scripts
```

#### 步骤 2：确定 Node.js ABI 版本

查看 Node.js 版本：

```bash
node -v
```

根据 Node.js 版本找到对应的 ABI 编号：

| Node.js 版本 | ABI 编号 |
|-------------|---------|
| 18.x        | v108    |
| 20.x        | v115    |
| 22.x        | v127    |

例如 Node.js v22.22.2 对应 **node-v127**。

#### 步骤 3：下载预编译文件

从 GitHub Releases 页面下载对应版本的预编译文件：

```
https://github.com/WiseLibs/better-sqlite3/releases
```

选择正确的文件格式：`better-sqlite3-v{版本}-node-v{ABI}-win32-x64.tar.gz`

例如 Node.js 22.x + Windows x64：

```
better-sqlite3-v12.9.0-node-v127-win32-x64.tar.gz
```

#### 步骤 4：解压并复制

解压下载的文件，将 `build/Release/better_sqlite3.node` 复制到 npm 全局模块目录：

```bash
# 解压到临时目录
mkdir -p C:\Users\{用户名}\tmp\better-sqlite3
tar -xf better-sqlite3-v12.9.0-node-v127-win32-x64.tar.gz -C C:\Users\{用户名}\tmp

# 复制到正确位置
mkdir -p "C:\Users\{用户名}\AppData\Roaming\npm\node_modules\mcp-chrome-bridge\node_modules\better-sqlite3\build\Release"
copy "C:\Users\{用户名}\tmp\build\Release\better_sqlite3.node" "C:\Users\{用户名}\AppData\Roaming\npm\node_modules\mcp-chrome-bridge\node_modules\better-sqlite3\build\Release\"
```

#### 步骤 5：验证安装

```bash
cd "C:\Users\{用户名}\AppData\Roaming\npm\node_modules\mcp-chrome-bridge\node_modules\better-sqlite3"
node -e "const db = require('better-sqlite3')('test.db'); console.log('better-sqlite3 loaded successfully'); db.close();"
```

输出 `better-sqlite3 loaded successfully` 表示成功。

#### 步骤 6：注册 Native Messaging Host

```bash
mcp-chrome-bridge register --browser chrome
```

## 2. 配置 Edge 浏览器

mcp-chrome-bridge 默认不支持 Edge，但 Edge 基于 Chromium，可以手动配置。

### 方法：手动创建 Edge 配置文件

Edge 的 Native Messaging Host 配置目录：

```
%APPDATA%\Microsoft\Edge\NativeMessagingHosts\
```

#### 步骤 1：创建配置目录

```bash
mkdir "%APPDATA%\Microsoft\Edge\NativeMessagingHosts"
```

#### 步骤 2：复制 Chrome 配置文件

Chrome 配置文件位于：

```
%APPDATA%\Google\Chrome\NativeMessagingHosts\com.chromemcp.nativehost.json
```

复制到 Edge 目录：

```bash
copy "%APPDATA%\Google\Chrome\NativeMessagingHosts\com.chromemcp.nativehost.json" "%APPDATA%\Microsoft\Edge\NativeMessagingHosts\"
```

或者手动创建配置文件：

```json
{
  "name": "com.chromemcp.nativehost",
  "description": "Node.js Host for Browser Bridge Extension",
  "path": "C:\\Users\\{用户名}\\AppData\\Roaming\\npm\\node_modules\\mcp-chrome-bridge\\dist\\run_host.bat",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://hbdgbgagpkpjffpklnamcljpakneikee/"
  ]
}
```

注意：将 `{用户名}` 替换为你的 Windows 用户名。

### 验证配置

运行诊断命令：

```bash
mcp-chrome-bridge doctor
```

所有项目显示 `[OK]` 表示配置成功。

## 3. 安装 Chrome 扩展

在 Chrome 或 Edge 中安装对应的扩展，扩展 ID 为：

```
hbdgbgagpkpjffpklnamcljpakneikee
```

在扩展中点击 "Connect"，服务会自动启动。

## 4. 服务端口

mcp-chrome-bridge 默认运行在：

```
http://127.0.0.1:12306/mcp
```

可以通过以下命令修改端口：

```bash
mcp-chrome-bridge update-port <新端口>
```

## 5. 常用命令

```bash
# 诊断安装状态
mcp-chrome-bridge doctor

# 注册浏览器
mcp-chrome-bridge register --browser chrome
mcp-chrome-bridge register --browser chromium
mcp-chrome-bridge register --detect

# 查看帮助
mcp-chrome-bridge --help
```