#!/usr/bin/env bash
# 健身计划 · Ubuntu 22.04 / 24.04 一键部署（裸机 venv + systemd + Nginx）
#
# 用法（在服务器上、解压后的项目根目录执行）：
#   sudo bash deploy/deploy.sh                 # 只用 IP 访问（http）
#   sudo DOMAIN=fitness.example.com bash deploy/deploy.sh   # 配域名 + 自动申请 HTTPS
#
# 环境变量：
#   APP_DIR     安装目录，默认 /opt/fitness
#   PORT        后端端口，默认 8000
#   DOMAIN      域名；留空则不配 Nginx 域名规则里的证书申请
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/fitness}"
PORT="${PORT:-8000}"
DOMAIN="${DOMAIN:-}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '\033[32m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 或 sudo 执行"

log "1/8 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx curl rsync >/dev/null

log "2/8 创建运行用户与目录"
id fitness >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin fitness
mkdir -p "$APP_DIR" "$APP_DIR/data"
chown -R fitness:fitness "$APP_DIR"

log "3/8 同步代码到 $APP_DIR"
rsync -a --delete \
  --exclude 'data/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '.venv/' --exclude '*.zip' --exclude 'deploy/' \
  "$SRC_DIR"/ "$APP_DIR"/
# 已有数据库保留（rsync 的 --delete 已排除 data/，这里再确认一次权限）
chown -R fitness:fitness "$APP_DIR/data"

log "4/8 建立虚拟环境并安装依赖"
sudo -u fitness python3 -m venv "$APP_DIR/.venv"
sudo -u fitness "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u fitness "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

log "5/8 写入 systemd 服务"
COOKIE_SECURE="false"
if [ -n "$DOMAIN" ]; then COOKIE_SECURE="true"; fi
sed -e "s#/opt/fitness#$APP_DIR#g" \
    -e "s#FIT_PORT=8000#FIT_PORT=$PORT#g" \
    -e "s#FIT_COOKIE_SECURE=false#FIT_COOKIE_SECURE=$COOKIE_SECURE#g" \
    -e "s#--port 8000#--port $PORT#g" \
    "$SRC_DIR/deploy/fitness.service" > /etc/systemd/system/fitness.service
systemctl daemon-reload
systemctl enable --now fitness >/dev/null
systemctl restart fitness

log "6/8 等待服务起来并自检"
for i in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 1
  [ "$i" = 20 ] && { journalctl -u fitness -n 30 --no-pager; die "服务未能启动，见上面的 journal 日志"; }
done
curl -fsS "http://127.0.0.1:$PORT/health"; echo

log "7/8 配置 Nginx 反向代理"
SERVER_NAME="${DOMAIN:-_}"
sed -e "s#fitness.example.com#$SERVER_NAME#g" \
    -e "s#127.0.0.1:8000#127.0.0.1:$PORT#g" \
    "$SRC_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/fitness
ln -sf /etc/nginx/sites-available/fitness /etc/nginx/sites-enabled/fitness
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

log "8/8 完成"
if [ -n "$DOMAIN" ]; then
  log "申请 HTTPS 证书（需要域名已解析到本机）"
  apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@${DOMAIN#*.}" --redirect || \
    log "证书申请失败（多半是域名未解析），可稍后手动执行： certbot --nginx -d $DOMAIN"
fi

IP="$(curl -fsS --max-time 5 ifconfig.me 2>/dev/null || echo '服务器IP')"
cat <<EOF

================ 部署完成 =================
访问地址： http://$IP$( [ -n "$DOMAIN" ] && echo "  或  https://$DOMAIN" )
数据文件： $APP_DIR/data/fitness.db
服务管理： systemctl status fitness | restart fitness
实时日志： journalctl -u fitness -f
备份数据： cp $APP_DIR/data/fitness.db /root/fitness-$(date +%F).db
==========================================

EOF
