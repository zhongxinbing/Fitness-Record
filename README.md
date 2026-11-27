# 健身记录 · 静态版（可直接部署到 Render 静态站点）

整个应用就是三个文件：`index.html` + `assets/style.css` + `assets/*.js`。没有后端、没有数据库、没有服务器进程，
所以可以直接丢到任何静态托管（Render Static Site / GitHub Pages / Cloudflare Pages / 对象存储），**免费、不冷启动、几乎没有运维**。

## 它和服务器版的区别（务必先看）

| | 静态版（本包） | 服务器版（FastAPI + SQLite） |
| --- | --- | --- |
| 账号 | 有，但只是**本机账号**（同一浏览器内的多份档案），不是服务器账号 | 真账号，服务端校验、多用户隔离 |
| 数据存哪 | **你自己浏览器的 localStorage**，按账号分键存放 | 服务器上的 `data/fitness.db` |
| 换手机/换浏览器 | 账号带不走，需登录同名账号后「备份 → 导入」 | 登录即可，天然同步 |
| 清浏览器缓存 | **数据会丢** | 不影响 |
| 部署成本 | 免费静态托管，秒开 | 需要实例 + 持久磁盘（付费） |

一句话：**静态版是单机应用，数据跟着浏览器走。** 想要「手机、电脑看到同一份数据」，只能选服务器版，或者以后接一个云端数据库。

## 账号怎么工作（别误解）

- 注册/登录在**浏览器本地**完成：账号表存在 `fitness_accounts_v1`，密码用 PBKDF2-SHA256（12 万次迭代 + 随机盐）派生后只存哈希，明文不落地
- 每个账号的数据单独一个键 `fitness_data_v1_<id>`，互不可见；退出登录后内存中的数据也清掉
- **它挡不住懂技术的人**：数据就在本机，能打开浏览器开发者工具的人可以绕过入口直接读 localStorage。它的作用只是「一台设备上几个人各记各的、别互相看」，不是安全边界
- 换设备/换浏览器：账号不存在了，需重新注册一个同名账号，再「备份 → 导入」把数据搬过去
- 首次注册时会自动认领上一版（无账号版）留下的数据，并提示「已把之前本机保存的训练数据归到你的账号」
- 忘记密码：本机没有找回渠道，只能清掉账号重建（数据可用之前的 JSON 备份导回）

备份入口在右上角：`备份` → 导出 JSON / 导入 JSON / 清空当前账号。

## 部署到 Render（Static Site）

### 方式 A：Blueprint 一键

1. 新建一个 GitHub 仓库，把本目录内容（`index.html`、`assets/`、`render.yaml`）推上去
2. Render → **New → Blueprint** → 选该仓库 → **Apply**
3. 建好后域名是 `https://<render.yaml 里的 name>.onrender.com`

### 方式 B：手动建 Static Site

1. Render → **New → Static Site** → 连仓库
2. **Build Command** 留空（没有构建）
3. **Publish Directory** 填 `.`（如果仓库里放在 `static/` 子目录，就填 `static`）
4. **Create Static Site**，等 30 秒左右即可上线

两种方式都**不需要**环境变量、磁盘、健康检查——静态站点没有这些东西。

### 链接

- 默认：`https://<服务名>.onrender.com`（服务名在创建时决定，重名会要求改名）
- 自定义域名：服务页 Settings → Custom Domains，把给的 CNAME 记录填到你的域名解析里，证书自动签发

## 本地预览

```bash
cd 本目录
python -m http.server 8000
# 浏览器打开 http://127.0.0.1:8000
```

注意必须是 http 服务，直接用文件管理器双击 `index.html`（`file://`）部分浏览器会限制 localStorage 行为，不推荐。

## 手机使用建议

1. 浏览器打开链接 → 菜单里选「添加到主屏幕」，以后像 App 一样点开
2. **同一个链接、同一个浏览器**才是同一份数据；iOS 的 Safari 和 Chrome 数据不互通
3. 每周点一次「备份 → 导出备份到本地」，把 JSON 存到网盘

## 出问题怎么查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 打开一片空白 | 资源路径改了（`assets/` 目录没一起上传，或 Publish Directory 填错） | 确认 `index.html` 和 `assets/` 在同一层；浏览器 F12 看 404 |
| 改完代码还是旧的 | 浏览器/CDN 缓存 | Ctrl+F5（手机：清该站点缓存）；或临时把 `Cache-Control` 调成 `no-cache` |
| 数据不见了 | 清了浏览器数据 / 换了浏览器 / 换了域名（localStorage 按域名隔离） | 登录同名账号后用之前导出的 JSON 导入；域名变了要用旧域名的备份 |
| 忘了本机账号密码 | 本机没有找回功能 | 清掉 `fitness_accounts_v1` 重建账号（F12 → Application → Local Storage），再用备份导入数据 |
| 提示「本地存储已满」 | localStorage 约 5 MB 上限，一般是极大量历史 | 先导出备份，删掉很老的计划 |

## 文件清单

```
index.html          页面（原 Jinja 模板去掉账号区块后的纯 HTML）
assets/style.css    样式（同服务器版，追加了备份弹层的细节样式）
assets/app.js       前端交互（与服务器版同一份，只把 api() 换成本地数据层）
assets/store.js     本地数据层：用 localStorage 实现 /api/*（含本机账号注册登录）
render.yaml         Render 静态站点蓝图
README.md           本文件
```

`store.js` 里的接口路径、请求体、返回结构都照着服务器版 `app/repository.py` 复刻，所以前端逻辑一行没改：
计划增删改、逐组勾选、每组 RPE、动作替换/跳过、组间休息计时、体重曲线、周视图、动作 PR 与估算 1RM 全部可用。
