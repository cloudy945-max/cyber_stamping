#!/bin/bash
# cyber_stamping 部署脚本
# 适用：Ubuntu 22.04/24.04，腾讯轻量云 2核4G，无域名
# 用法：sudo bash deploy.sh
set -e

APP_DIR="/opt/cyber_stamping"
REPO_URL="${1:-}"  # 可传入 git 仓库地址，否则从本地拷贝

echo "========================================"
echo "  cyber_stamping 部署脚本"
echo "  系统: Ubuntu 22.04/24.04"
echo "  配置: 2核4G"
echo "========================================"

# ===== 1. 安装系统依赖 =====
echo "[1/8] 安装系统依赖..."
apt update -y
apt install -y python3 python3-venv python3-pip nginx git curl

# 检测系统 Python 版本（Ubuntu 22.04=3.10, Ubuntu 24.04=3.12）
PYTHON_BIN="python3"
PYTHON_VER=$($PYTHON_BIN --version 2>&1 | awk '{print $2}')
echo "  系统 Python: $PYTHON_VER"

# 如果版本 < 3.10，尝试安装 3.11
PY_MINOR=$($PYTHON_BIN -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MINOR" -lt 10 ]; then
    echo "  Python 3.${PY_MINOR} 版本过低，尝试安装 3.11..."
    apt install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt update -y
    apt install -y python3.11 python3.11-venv
    PYTHON_BIN="python3.11"
    PYTHON_VER=$($PYTHON_BIN --version 2>&1 | awk '{print $2}')
    echo "  已切换到 Python: $PYTHON_VER"
fi

# 检查 Node.js
if ! command -v node &>/dev/null || [ "$(node -v | cut -d. -f1 | cut -dv -f2)" -lt 18 ]; then
    echo "  安装 Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt install -y nodejs
fi

echo "  Python: $($PYTHON_BIN --version)"
echo "  Node.js: $(node -v)"

# ===== 2. 拉取代码 =====
echo "[2/8] 获取代码..."
if [ -n "$REPO_URL" ]; then
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
elif [ -d "$(dirname "$0")/../backend" ]; then
    # 从脚本所在目录的上层拷贝（本地部署）
    mkdir -p "$APP_DIR"
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    rsync -a --exclude='.git' --exclude='node_modules' --exclude='.venv' \
          --exclude='__pycache__' --exclude='test_output' \
          --exclude='data' --exclude='dist' \
          "$PROJECT_DIR/" "$APP_DIR/"
    echo "  从本地拷贝完成: $PROJECT_DIR → $APP_DIR"
else
    echo "  错误：请传入 git 仓库地址，或从项目目录运行"
    exit 1
fi

cd "$APP_DIR"

# ===== 3. 创建数据目录 =====
echo "[3/8] 创建数据目录..."
mkdir -p data/stamps/original data/stamps/sticker

# ===== 4. 配置环境变量 =====
echo "[4/8] 配置环境变量..."
if [ ! -f .env ]; then
    cp .env.example .env

    # 生成随机密钥
    JWT_SECRET=$($PYTHON_BIN -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|SECRET_KEY=.*|SECRET_KEY=$JWT_SECRET|" .env
    sed -i "s|DEBUG=.*|DEBUG=false|" .env

    echo "  .env 已生成，请编辑修改 ADMIN_PASSWORD 和 AMAP_KEY："
    echo "    nano $APP_DIR/.env"
    echo ""
    echo "  ⚠️  必须修改以下项："
    echo "    ADMIN_PASSWORD=你的密码"
    echo "    AMAP_KEY=你的高德API Key"
else
    echo "  .env 已存在，跳过"
fi

# ===== 5. 安装后端依赖 =====
echo "[5/8] 安装后端依赖..."
cd "$APP_DIR/backend"
$PYTHON_BIN -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
echo "  后端依赖安装完成"

# ===== 6. 预下载 rembg 模型 =====
echo "[6/8] 下载 rembg 模型 (u2netp, ~4.7MB)..."
mkdir -p ~/.u2net
if [ ! -f ~/.u2net/u2netp.onnx ]; then
    curl -L -o ~/.u2net/u2netp.onnx \
      "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
    echo "  模型下载完成"
else
    echo "  模型已存在，跳过"
fi

# ===== 7. 构建前端 =====
echo "[7/8] 构建前端..."
cd "$APP_DIR/frontend"
npm install
npm run build
echo "  前端构建完成: dist/"

# ===== 8. 配置 Nginx + systemd =====
echo "[8/8] 配置服务..."

# Nginx
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/cyber-stamping
ln -sf /etc/nginx/sites-available/cyber-stamping /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
systemctl enable nginx

# systemd
cp "$APP_DIR/deploy/cyber-stamping.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable cyber-stamping
systemctl restart cyber-stamping

# 等待后端启动
sleep 3
if systemctl is-active --quiet cyber-stamping; then
    echo ""
    echo "========================================"
    echo "  ✅ 部署完成！"
    echo "========================================"
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo ""
    echo "  访问地址: http://$SERVER_IP"
    echo "  后端 API: http://$SERVER_IP/api/docs"
    echo ""
    echo "  下一步："
    echo "    1. 编辑配置: nano $APP_DIR/.env"
    echo "    2. 重启后端: systemctl restart cyber-stamping"
    echo ""
    echo "  常用命令："
    echo "    查看日志: journalctl -u cyber-stamping -f"
    echo "    重启后端: systemctl restart cyber-stamping"
    echo "    重启 Nginx: systemctl restart nginx"
    echo "========================================"
else
    echo ""
    echo "❌ 后端启动失败，请查看日志："
    echo "  journalctl -u cyber-stamping -n 50"
    exit 1
fi
