# 云端部署指南

三种方式，按你的条件选：

| 场景 | 选哪个 | 需要的条件 |
| --- | --- | --- |
| 有云服务器（阿里云/腾讯云/华为云 ECS，Ubuntu） | **方式一**：一键脚本 | 一台能 SSH 的 Linux 机器 |
| 想用容器、便于迁移备份 | **方式二**：Docker Compose | 服务器已装 Docker |
| 不想买服务器 / 想让家人手机也能用 | **方式三**：Render（Docker + 持久盘） | 一个 GitHub 账号 + Render 付费实例 |

> 手机随时练、随时记，必须部署到有公网 IP 的地方；`python main.py` 只能本机或同一 WiFi 访问。

---

## 方式一：云服务器一键部署（推荐）

**1. 服务器准备**（云控制台里做）

- 系统装 **Ubuntu 22.04 或 24.04**
- 安全组放行 **22（SSH）、80（HTTP）、443（HTTPS）**
- 记下公网 IP

**2. 上传代码**

在本地把整个 `fitness_tracker` 目录打包上传（或用 scp）：

```bash
scp -r fitness_tracker root@<服务器IP>:/root/
```

**3. 一键部署**

```bash
ssh root@<服务器IP>
cd /root/fitness_tracker
sudo bash deploy/deploy.sh                  # 只用 IP 访问
# 有域名时（先在云解析里把域名 A 记录指向服务器 IP）：
sudo DOMAIN=fit.你的域名.com bash deploy/deploy.sh
```

脚本做的事：装 Python/venv/Nginx → 建 `fitness` 运行用户 → 代码同步到 `/opt/fitness` → 装依赖 → 注册 systemd 服务 → 自检 `/health` → 配 Nginx 反代 → 有域名则自动申请 Let's Encrypt 证书并强制 HTTPS。

完成后终端会打印访问地址。手机浏览器直接打开即可，注册账号开始用。

**4. 日常运维**

```bash
systemctl status fitness        # 运行状态
systemctl restart fitness       # 重启
journalctl -u fitness -f        # 实时日志
cp /opt/fitness/data/fitness.db /root/fitness-$(date +%F).db   # 备份
```

更新代码：把新代码传上去，在项目目录重新执行 `sudo bash deploy/deploy.sh`（`data/` 不会被覆盖，账号与训练记录保留）。

---

## 方式二：Docker Compose

```bash
# 服务器上装 Docker（一次）
curl -fsSL https://get.docker.com | sh

cd /root/fitness_tracker
mkdir -p data
docker compose up -d --build
docker compose logs -f          # 看日志
```

再用方式一里的 Nginx 配置反代 `127.0.0.1:8000`（把 `deploy/nginx.conf` 里 upstream 端口对齐即可），或者临时把 `docker-compose.yml` 的端口改成 `"8000:8000"` 直接暴露（不推荐长期这样）。

数据在宿主机 `./data/fitness.db`，`docker compose down` 也不会丢。

---

## 方式三：Render 部署（有 Dockerfile，开箱即用）

仓库里带 `Dockerfile` 和 `render.yaml`，Render 会按容器方式构建，不用你装 Python。

**前提：代码在 GitHub 仓库里**（Render 只能从 Git 拉代码，不能直接传 zip）。把整个 `fitness_tracker` 目录推到 GitHub 私有仓库即可，`data/` 已被 `.dockerignore` 排除，不会把本地库传上去。

### 路线 A：Blueprint 一键建（推荐）

1. Render 控制台 → **New → Blueprint** → 选你的仓库，它会读 `render.yaml` 自动建服务
2. 按提示改 `name`（决定域名 `https://<name>.onrender.com`），确认 `plan: starter`（**持久磁盘只有付费实例才有**）
3. 点 **Apply**，等第一次构建（约 3–6 分钟，pip 装依赖是大头）
4. 构建完访问 `https://<name>.onrender.com/health`，应返回：

```json
{"status":"ok","app":"健身记录","version":"7.2","db":"/var/data/fitness.db"}
```

`db` 必须是 `/var/data/fitness.db`；如果还是 `/app/data/fitness.db`，说明 `FIT_DB_PATH` 没生效，改环境变量后手动 **Manual Deploy → Clear build cache & deploy**。

### 路线 B：手动建 Web Service

1. **New → Web Service** → 连仓库
2. Language 选 **Docker**，Dockerfile Path 填 `./Dockerfile`
3. Region 选 **Singapore**（离国内最近，延迟比 Oregon 低不少）
4. Instance Type 选 **Starter**（$7/月左右），**不要选 Free**，理由见下面「免费实例的硬伤」
5. **Disks → Add Disk**：Name `fitness-data`，Mount Path `/var/data`，Size 1 GB
6. **Environment Variables** 加上面「环境变量」表里的四项
7. Health Check Path 填 `/health`，保存后自动部署

### 环境变量（Render 后台 Environment 页填）

| Key | Value | 为什么 |
| --- | --- | --- |
| `FIT_DB_PATH` | `/var/data/fitness.db` | 必须落在持久盘挂载点，否则重启就清空 |
| `FIT_COOKIE_SECURE` | `true` | Render 只给 HTTPS 域名，Cookie 不带 Secure 会被浏览器拒收，表现为「登录成功又弹回登录页」 |
| `FIT_TIMEZONE` | `Asia/Shanghai` | 「今天」按北京时间算，不然凌晨记的训练会算到前一天 |
| `FIT_DEBUG` | `false` | 生产不要热重载 |

**端口不用自己设**：Render 会注入 `$PORT`（随机端口，历史默认 10000），容器启动命令已写成 `--port ${PORT:-8000}`，本地没设 `PORT` 时回退 8000。监听地址是 `0.0.0.0`，Render 才能从外部探到 `/health`。

### 免费实例的硬伤（这点必须知道）

- **没有持久磁盘**：容器文件系统是临时的，每次重新部署、实例重启、或空闲 15 分钟后被回收重启，`fitness.db` 都会回到镜像里的空库 → 账号和训练记录全丢
- **空闲休眠**：15 分钟没访问就睡，下一次打开要等 30 秒以上冷启动，手机端体验很差
- 结论：免费实例只适合看界面、验证能不能跑通；**真实训练数据别放免费实例**

### 部署后自检清单

| 检查 | 期望 |
| --- | --- |
| `/health` 的 `version` | `7.2`（对不上说明镜像没重新构建，Clear build cache 再部署） |
| `/health` 的 `db` | `/var/data/fitness.db` |
| 注册一个账号 | 201，且 Render 日志里出现 `启动完成 v7.2 \| 库文件：/var/data/fitness.db \| 表数量：7` |
| 触发一次重新部署 | 重新部署后账号还在（证明磁盘挂对了；不在就是磁盘没挂或路径写错） |
| 手机浏览器访问 | 能注册、能登录、能记录，说明 Cookie Secure 配置正确 |

### 数据备份与迁移（Render 上没有 SSH，靠这两招）

1. **本地拉一份**：Render 后台 **Shell**（Starter 及以上可用）执行 `cp /var/data/fitness.db /var/data/backup-$(date +%F).db`；更稳的做法是在本地从 `/var/data/fitness.db` 下载（后台 SFTP/Shell 支持 `cat` 出来再落地）
2. **平台无关的备份**：SQLite 单文件就是全部数据，定期下载 `fitness.db` 存本地，换平台时把文件放回 `FIT_DB_PATH` 指的位置即可，代码零改动

### 为什么不用 Render 的 PostgreSQL

现在仓储层是直连 SQLite 的 SQL，换 Postgres 要改 `repository.py` 的方言（自增、`datetime('now','localtime')`、UPSERT 语法等）。单用户健身记录的量级（一天几条到几十条）SQLite 完全够，别为这个付出改造成本。真要多实例/多人共享再迁移。

---

## 上线后一定要检查的几件事

| 项 | 说明 |
| --- | --- |
| `FIT_COOKIE_SECURE` | **走 HTTPS 时必须 `true`**；只用 http 访问时必须 `false`，否则浏览器不保存登录 Cookie，表现为“登录成功又立刻回登录页” |
| 数据库文件权限 | 属主必须是运行用户（脚本已处理为 `fitness`），否则写不进去会 500 |
| 端口暴露 | 自建服务器时后端只监听 `127.0.0.1`，公网只开 80/443；Render 上则由平台注入 `PORT` |
| 备份 | `data/fitness.db` 是唯一数据源，建议 cron 每天拷一份 |
| 证书续期 | certbot 会自动装 systemd timer，`systemctl list-timers | grep certbot` 可确认 |

## 常见问题

**打开是 404 / `{"detail":"Not Found"}`** → 反代路径或端口不匹配，`curl http://127.0.0.1:8000/health` 看后端是否活着。

**登录后又跳回登录页** → Cookie 的 Secure 标记和实际协议不一致，见上表。

**手机能开但很慢** → 服务器在国内、机房线路一般；页面本身只有几十 KB，主要看带宽，可开 Nginx `gzip`（配置已带）。

**想多台机器/多人高并发** → SQLite 单文件适合单实例。需要横向扩容时把仓储层换成 PostgreSQL，`repository.py` 里 SQL 已集中，改动面可控。
