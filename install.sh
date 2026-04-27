#!/bin/bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/OCI}"
REPO_URL="${REPO_URL:-https://github.com/yigehen/OCI.git}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="oci"
CELERY_SERVICE_NAME="oci-worker"
APP_USER="${APP_USER:-www-data}"

print_info() { echo -e "\e[34m[信息]\e[0m $1"; }
print_success() { echo -e "\e[32m[成功]\e[0m $1"; }
print_warning() { echo -e "\e[33m[警告]\e[0m $1"; }
print_error() { echo -e "\e[31m[错误]\e[0m $1"; exit 1; }

ensure_user() {
  id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
}

install_or_update_panel() {
  print_info "安装依赖..."
  apt-get update
  apt-get install -y git python3-venv python3-pip redis-server curl python3-dev gcc libffi-dev libssl-dev

  ensure_user

  if [ -d "$INSTALL_DIR/.git" ]; then
    print_info "检测到已安装，执行更新..."
    systemctl stop ${SERVICE_NAME}.service || true
    systemctl stop ${CELERY_SERVICE_NAME}.service || true
    cd "$INSTALL_DIR"
    git remote set-url origin "$REPO_URL" || true
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
  else
    print_info "全新安装..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
  fi

  mkdir -p "$INSTALL_DIR/data"
  [ -f "$INSTALL_DIR/.env" ] || cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"

  print_info "配置 Python..."
  cd "$INSTALL_DIR"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  deactivate

  chown -R "$APP_USER":"$APP_USER" "$INSTALL_DIR"

  print_info "配置 systemd 服务..."
  cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=OCI Web
After=network.target redis-server.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
Environment=APP_DATA_DIR=${INSTALL_DIR}/data
ExecStart=${INSTALL_DIR}/.venv/bin/gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/${CELERY_SERVICE_NAME}.service <<EOF
[Unit]
Description=OCI Worker
After=network.target redis-server.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
Environment=APP_DATA_DIR=${INSTALL_DIR}/data
ExecStart=${INSTALL_DIR}/.venv/bin/celery -A app_pkg.celery_app.celery worker --pool=threads --concurrency=100 --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable redis-server ${SERVICE_NAME} ${CELERY_SERVICE_NAME}
  systemctl restart redis-server ${SERVICE_NAME} ${CELERY_SERVICE_NAME}

  print_success "安装/更新完成"
  echo "Web 状态: systemctl status ${SERVICE_NAME}"
  echo "Worker 状态: systemctl status ${CELERY_SERVICE_NAME}"
}

uninstall_panel() {
  print_warning "确定要卸载吗？"
  read -r -p "输入 yes 确认: " confirmation
  confirmation=$(echo "$confirmation" | tr '[:upper:]' '[:lower:]' | xargs)
  if [[ "$confirmation" != "yes" ]]; then
    print_info "取消卸载。"
    exit 0
  fi

  systemctl stop ${SERVICE_NAME}.service || true
  systemctl stop ${CELERY_SERVICE_NAME}.service || true
  systemctl disable ${SERVICE_NAME}.service || true
  systemctl disable ${CELERY_SERVICE_NAME}.service || true
  rm -f /etc/systemd/system/${SERVICE_NAME}.service
  rm -f /etc/systemd/system/${CELERY_SERVICE_NAME}.service
  systemctl daemon-reload
  rm -rf "${INSTALL_DIR}"
  print_success "卸载完成"
}

if [ "$(id -u)" -ne 0 ]; then
  print_error "必须使用 root 运行"
fi

clear
echo "======================================"
echo " OCI 安装脚本"
echo "======================================"
echo "1) 安装 / 更新"
echo "2) 卸载"
echo "3) 退出"
echo "======================================"
read -r -p "请选择 [1]: " choice
choice=${choice:-1}

case $choice in
  1) install_or_update_panel ;;
  2) uninstall_panel ;;
  3) exit 0 ;;
  *) print_error "无效选项" ;;
esac
