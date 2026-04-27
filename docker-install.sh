#!/bin/bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/OCI}"
REPO_URL="${REPO_URL:-https://github.com/yigehen/OCI.git}"
BRANCH="${BRANCH:-main}"
ENV_FILE="$INSTALL_DIR/.env"

print_info() { echo -e "\e[34m[信息]\e[0m $1"; }
print_success() { echo -e "\e[32m[成功]\e[0m $1"; }
print_warning() { echo -e "\e[33m[警告]\e[0m $1"; }
print_error() { echo -e "\e[31m[错误]\e[0m $1"; exit 1; }

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    print_warning "未检测到 Docker，正在安装..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable --now docker
  fi
  if ! docker compose version >/dev/null 2>&1; then
    print_error "未检测到 docker compose plugin，请先检查 Docker 安装是否完整。"
  fi
  if ! command -v git >/dev/null 2>&1; then
    apt-get update
    apt-get install -y git curl
  fi
}

prepare_repo() {
  mkdir -p "$(dirname "$INSTALL_DIR")"
  if [ ! -d "$INSTALL_DIR/.git" ]; then
    print_info "正在克隆仓库: $REPO_URL"
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  else
    print_info "检测到现有安装目录，后续执行同步更新"
  fi
  cd "$INSTALL_DIR"
  mkdir -p data
  [ -f .env ] || cp .env.example .env
}

sync_repo() {
  cd "$INSTALL_DIR"
  git remote set-url origin "$REPO_URL" || true
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"
}

write_env_value() {
  local key="$1"
  local value="$2"
  touch "$ENV_FILE"
  sed -i "/^${key}=/d" "$ENV_FILE" || true
  echo "${key}=${value}" >> "$ENV_FILE"
}

generate_ip_override() {
  local port="${1:-5000}"
  cat > docker-compose.override.yml <<EOF
services:
  web:
    ports:
      - "${port}:5000"
EOF
}

generate_domain_override() {
  local domain="$1"
  cat > Caddyfile <<EOF
${domain} {
    reverse_proxy web:5000
}
EOF

  cat > docker-compose.override.yml <<EOF
services:
  web:
    expose:
      - "5000"
  caddy:
    image: caddy:latest
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - web

volumes:
  caddy_data:
  caddy_config:
EOF
}

install_ip_mode() {
  ensure_docker
  prepare_repo

  read -r -p "请输入新的面板登录密码: " new_password
  read -r -p "请输入要映射的主机端口 [默认: 5000]: " host_port
  host_port="${host_port:-5000}"

  write_env_value "PANEL_PASSWORD" "$new_password"
  write_env_value "HOST_PORT" "$host_port"
  generate_ip_override "$host_port"

  docker compose down --remove-orphans || true
  docker compose up -d --build

  SERVER_IP=$(curl -s ifconfig.me || true)
  print_success "安装完成： http://${SERVER_IP:-<服务器IP>}:${host_port}"
}

install_domain_mode() {
  ensure_docker
  prepare_repo

  read -r -p "请输入新的面板登录密码: " new_password
  read -r -p "请输入您的域名: " domain_name

  write_env_value "PANEL_PASSWORD" "$new_password"
  write_env_value "DOMAIN_OR_IP" "$domain_name"
  generate_domain_override "$domain_name"

  docker compose down --remove-orphans || true
  docker compose up -d --build
  print_success "安装完成： https://${domain_name}"
}

update_panel() {
  [ -d "$INSTALL_DIR" ] || print_error "未找到安装目录，请先安装。"
  ensure_docker
  sync_repo

  if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
  fi

  if [ -n "${DOMAIN_OR_IP:-}" ]; then
    generate_domain_override "$DOMAIN_OR_IP"
  else
    generate_ip_override "${HOST_PORT:-5000}"
  fi

  docker compose down --remove-orphans || true
  docker compose up -d --build
  print_success "更新完成。"
}

uninstall_panel() {
  print_warning "确定要卸载吗？(yes/no)"
  read -r -p "输入 yes 确认: " confirm
  if [ "$confirm" = "yes" ] && [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    docker compose down -v || true
    cd ..
    rm -rf "$INSTALL_DIR"
    print_success "卸载完成。"
  else
    print_info "取消卸载。"
  fi
}

if [ "$(id -u)" -ne 0 ]; then
  print_error "请使用 root 运行。"
fi

clear
print_info "OCI Docker 管理脚本"
echo "=========================================================="
echo "  1) 安装: IP+端口模式"
echo "  2) 安装: 域名+Caddy HTTPS 模式"
echo "  3) 更新: 同步仓库并重建容器"
echo "  4) 卸载: 删除文件和容器"
echo "  5) 退出"
echo "=========================================================="
read -r -p "请输入选项 [1-5]: " choice

case "$choice" in
  1) install_ip_mode ;;
  2) install_domain_mode ;;
  3) update_panel ;;
  4) uninstall_panel ;;
  5) exit 0 ;;
  *) print_error "无效选项" ;;
esac
