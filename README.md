# OCI

一个面向 **Oracle Cloud Infrastructure (OCI)** 的网页管理面板，当前仓库已整理为：
- **可直接上传到 GitHub**
- **可在任意 Linux 服务器 git clone 后安装**
- **支持 Docker Compose 部署**
- **支持 systemd + 本机 Python 部署**
- **运行数据与源码分离，用户数据保存在 `data/` 目录**

---

## 部署方式

### 方式一：Docker 一键安装

适合大多数服务器。

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/yigehen/OCI/main/docker-install.sh)
```

也可以指定仓库与分支：

```bash
REPO_URL=https://github.com/yigehen/OCI.git \
BRANCH=main \
bash <(curl -fsSL https://raw.githubusercontent.com/yigehen/OCI/main/docker-install.sh)
```

### 方式二：源码拉取 + systemd 安装

```bash
git clone https://github.com/yigehen/OCI.git
cd OCI
sudo bash install.sh
```

---

## 本地开发启动

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少修改：
- `PANEL_PASSWORD`
- `SECRET_KEY`

### 3. 启动 Redis

如果本地没有 Redis，可以用 Docker：

```bash
docker run -d --name oci-redis -p 6379:6379 redis:7-alpine
```

### 4. 启动 Web

```bash
source .venv/bin/activate
python app.py
# 然后访问 http://127.0.0.1:5001
```

### 5. 启动 Worker

另开一个终端：

```bash
source .venv/bin/activate
celery -A app_pkg.celery_app.celery worker --pool=threads --concurrency=100 --loglevel=info
```

---

## Docker Compose 手动运行

```bash
cp .env.example .env
mkdir -p data
docker compose up -d --build
```

默认情况下：
- 应用运行数据保存在 `./data/`
- Redis 数据保存在 Docker volume 中

如果要暴露端口，可创建 `docker-compose.override.yml`：

```yaml
services:
  web:
    ports:
      - "5000:5000"
```

然后执行：

```bash
docker compose up -d --build
```

---

## 运行数据说明

以下文件不再建议提交到 GitHub，而是运行时自动生成到 `data/`：

- `config.json`
- `oci_profiles.json`
- `oci_tasks.db`
- `tg_settings.json`
- `cloudflare_settings.json`
- `default_key.json`
- `default_startup_script.sh`
- `xui_settings.json`
- `mfa_secret.json`

---

## 推荐发布到 GitHub 前的清理

在推送前请确认仓库中 **不要包含真实敏感数据**：

- `.env`
- `data/` 目录
- 真实 OCI 账户配置
- 真实 Cloudflare / Telegram / XUI 凭据
- 本地数据库文件

建议检查：

```bash
git status
```

---

## 服务器要求

### Docker 方案
- Debian / Ubuntu
- Docker
- Docker Compose Plugin

### 非 Docker 方案
- Debian / Ubuntu
- Python 3.10+
- Redis
- systemd

---

## 启动入口

- Web WSGI 入口：`app:app`
- 工厂函数：`app_pkg.create_app`
- Celery 实例：`app_pkg.extensions.celery`

---

## 上传到 GitHub 的基本步骤

```bash
git init
git add .
git commit -m "feat: prepare portable OCI manager release"
git branch -M main
git remote add origin https://github.com/yigehen/OCI.git
git push -u origin main
```

如果你已经有远程仓库，先检查：

```bash
git remote -v
```

---

## 当前发布目标

这个版本的目标不是继续拆代码，而是保证它具备：
- 仓库可公开上传
- 可 fork
- 可 pull
- 可一键安装
- 可在新服务器上首次启动时自动生成运行文件
