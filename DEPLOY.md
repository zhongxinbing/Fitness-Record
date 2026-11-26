# 云端部署指南

三种方式，按你的条件选：

| 场景 | 选哪个 | 需要的条件 |
| --- | --- | --- |
| 有云服务器（阿里云/腾讯云/华为云 ECS，Ubuntu） | **方式一**：一键脚本 | 一台能 SSH 的 Linux 机器 |
| 想用容器、便于迁移备份 | **方式二**：Docker Compose | 服务器已装 Docker |
| 不想买服务器，先跑起来试试 | **方式三**：Render / Railway | 一个 GitHub 账号 |

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

## 方式三：Render / Railway（免费额度起步）

仓库里已带 `Dockerfile`，平台会自动识别：

1. 把项目推到 GitHub
2. Render 新建 **Web Service** → 选该仓库 → 自动用 Dockerfile 构建
3. 环境变量加上 `FIT_COOKIE_SECURE=true`（平台默认 HTTPS）、`FIT_TIMEZONE=Asia/Shanghai`
4. **必须挂持久磁盘**并设 `FIT_DB_PATH=/app/data/fitness.db`，否则每次重新部署账号和记录会被清空

坦白说：这类免费 PaaS 的文件系统是临时的，SQLite 必须配持久卷（付费项）。只想试用可以先不挂卷，但别把真实训练数据留在上面。

---

## 上线后一定要检查的几件事

| 项 | 说明 |
| --- | --- |
| `FIT_COOKIE_SECURE` | **走 HTTPS 时必须 `true`**；只用 http 访问时必须 `false`，否则浏览器不保存登录 Cookie，表现为“登录成功又立刻回登录页” |
| 数据库文件权限 | 属主必须是运行用户（脚本已处理为 `fitness`），否则写不进去会 500 |
| 端口暴露 | 后端只监听 `127.0.0.1`，公网只开 80/443，别把 8000 直接暴露到公网 |
| 备份 | `data/fitness.db` 是唯一数据源，建议 cron 每天拷一份 |
| 证书续期 | certbot 会自动装 systemd timer，`systemctl list-timers | grep certbot` 可确认 |

## 常见问题

**打开是 404 / `{"detail":"Not Found"}`** → 反代路径或端口不匹配，`curl http://127.0.0.1:8000/health` 看后端是否活着。

**登录后又跳回登录页** → Cookie 的 Secure 标记和实际协议不一致，见上表。

**手机能开但很慢** → 服务器在国内、机房线路一般；页面本身只有几十 KB，主要看带宽，可开 Nginx `gzip`（配置已带）。

**想多台机器/多人高并发** → SQLite 单文件适合单实例。需要横向扩容时把仓储层换成 PostgreSQL，`repository.py` 里 SQL 已集中，改动面可控。
