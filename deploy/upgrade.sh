#!/bin/bash
# cyber_stamping 升级脚本
# 适用：已通过 deploy.sh 部署过的腾讯轻量云服务器
# 用法：sudo bash deploy/upgrade.sh
set -e

APP_DIR="/opt/cyber_stamping"
REPO_URL="https://github.com/cloudy945-max/cyber_stamping.git"
BRANCH="main"

echo "========================================"
echo "  cyber_stamping 升级脚本"
echo "  新增高保真印章 Alpha 提取引擎"
echo "========================================"
echo ""

# ===== 0. 前置检查 =====
if [ ! -d "$APP_DIR" ]; then
    echo "❌ 未找到 $APP_DIR，请先运行 deploy.sh 完成初次部署"
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo "❌ 请使用 sudo 运行：sudo bash deploy/upgrade.sh"
    exit 1
fi

echo "[1/7] 检查环境..."
# 找到 Python（优先虚拟环境，其次系统）
if [ -f "$APP_DIR/backend/.venv/bin/python" ]; then
    PY="$APP_DIR/backend/.venv/bin/python"
else
    PY=$(which python3)
fi
echo "  Python: $($PY --version)"

if command -v node &>/dev/null; then
    echo "  Node.js: $(node -v)"
else
    echo "  ❌ Node.js 未安装"
    exit 1
fi

# ===== 1. 备份当前版本 =====
echo ""
echo "[2/7] 备份当前版本..."
BACKUP_DIR="/opt/cyber_stamping_bak_$(date +%Y%m%d_%H%M%S)"
cp -a "$APP_DIR" "$BACKUP_DIR"
# 备份不包含 node_modules 和 venv（太大了）
rm -rf "$BACKUP_DIR/frontend/node_modules" "$BACKUP_DIR/backend/.venv"
echo "  备份到: $BACKUP_DIR"

# ===== 2. 拉取最新代码 =====
echo ""
echo "[3/7] 拉取最新代码..."
cd "$APP_DIR"

# 检查是否是 git 仓库
if [ -d "$APP_DIR/.git" ]; then
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
    echo "  git pull 完成"
else
    echo "  当前目录不是 git 仓库，尝试从 GitHub 克隆..."
    cd /opt
    git clone --branch "$BRANCH" "$REPO_URL" "${APP_DIR}_new"
    
    # 保留 .env 和 data 和 models
    cp -a "$APP_DIR/.env" "${APP_DIR}_new/.env" 2>/dev/null || true
    cp -a "$APP_DIR/data" "${APP_DIR}_new/data" 2>/dev/null || true
    cp -a "$APP_DIR/models" "${APP_DIR}_new/models" 2>/dev/null || true
    cp -a "$APP_DIR/backend/.venv" "${APP_DIR}_new/backend/.venv" 2>/dev/null || true
    
    rm -rf "$APP_DIR"
    mv "${APP_DIR}_new" "$APP_DIR"
    cd "$APP_DIR"
    echo "  克隆完成"
fi

# ===== 3. 更新 .env 配置 =====
echo ""
echo "[4/7] 更新 .env 配置..."

# 备份当前 .env
cp "$APP_DIR/.env" "$APP_DIR/.env.bak.$(date +%Y%m%d)"

# 如果 .env 中没有 SEGMENT_METHOD，追加新配置
if ! grep -q "SEGMENT_METHOD" "$APP_DIR/.env"; then
    cat >> "$APP_DIR/.env" << 'ENVEOF'

# ===== 印章抠图方法 =====
# extractor（高保真 Alpha，新） / legacy（R-G+rembg，旧）
SEGMENT_METHOD=extractor
# extractor 预设：default / preserve_light / conservative
EXTRACTOR_PRESET=default
ENVEOF
    echo "  已追加 SEGMENT_METHOD=extractor, EXTRACTOR_PRESET=default"
else
    echo "  SEGMENT_METHOD 已存在，跳过"
fi

# ===== 4. 更新后端依赖 =====
echo ""
echo "[5/7] 更新后端依赖..."
cd "$APP_DIR/backend"

# 如果虚拟环境不存在，重新创建
if [ ! -d ".venv" ]; then
    $PY -m venv .venv
fi

.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "  后端依赖安装完成"

# 验证 stamp_extractor 可导入（需从项目根目录运行，stamp_extractor 在项目根）
cd "$APP_DIR"
if backend/.venv/bin/python -c "from stamp_extractor.processor import StampExtractor; print('  stamp_extractor 导入成功')" 2>/dev/null; then
    echo "  ✅ 新引擎验证通过"
else
    echo "  ⚠️  stamp_extractor 导入失败，请检查日志"
    echo "  尝试手动验证: cd $APP_DIR && backend/.venv/bin/python -c 'from stamp_extractor.processor import StampExtractor'"
fi

# ===== 5. 重新构建前端 =====
echo ""
echo "[6/7] 重新构建前端..."
cd "$APP_DIR/frontend"
npm install --silent 2>/dev/null || npm install
npm run build 2>&1 | tail -3
echo "  前端构建完成"

# ===== 6. 重启服务 =====
echo ""
echo "[7/7] 重启服务..."
cd "$APP_DIR"

# 更新 Nginx 配置（如果有变化）
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/cyber-stamping
nginx -t 2>&1
systemctl reload nginx

# 更新 systemd 配置（如果有变化）
cp "$APP_DIR/deploy/cyber-stamping.service" /etc/systemd/system/
systemctl daemon-reload
systemctl restart cyber-stamping

# 等待后端启动
sleep 3
if systemctl is-active --quiet cyber-stamping; then
    echo ""
    echo "========================================"
    echo "  ✅ 升级完成！"
    echo "========================================"
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo ""
    echo "  访问地址: http://$SERVER_IP"
    echo "  测试页面: http://$SERVER_IP/segment-test"
    echo ""
    echo "  新功能："
    echo "    - 印章分割测试页新增「高保真 Alpha（新）」方法"
    echo "    - 三种预设：Default / Preserve Light / Conservative"
    echo "    - 上传流程默认使用新引擎"
    echo ""
    echo "  回滚方法："
    echo "    1. 编辑 .env: nano $APP_DIR/.env"
    echo "    2. 改为: SEGMENT_METHOD=legacy"
    echo "    3. 重启: systemctl restart cyber-stamping"
    echo ""
    echo "  回滚到旧版本："
    echo "    sudo rm -rf $APP_DIR"
    echo "    sudo mv $BACKUP_DIR $APP_DIR"
    echo "    sudo systemctl restart cyber-stamping"
    echo ""
    echo "  查看日志: journalctl -u cyber-stamping -f"
    echo "========================================"
else
    echo ""
    echo "❌ 后端启动失败！"
    echo ""
    echo "  查看日志: journalctl -u cyber-stamping -n 50"
    echo ""
    echo "  回滚方法："
    echo "    sudo rm -rf $APP_DIR"
    echo "    sudo mv $BACKUP_DIR $APP_DIR"
    echo "    sudo systemctl restart cyber-stamping"
    exit 1
fi
