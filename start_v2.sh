#!/bin/bash
# AMQ2API v2.0 启动脚本

echo "================================================"
echo "  AMQ2API v2.0 - Account Pool & API Key Auth"
echo "================================================"
echo ""

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python 版本: $PYTHON_VERSION"

# 检查依赖
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "❌ 依赖未安装，正在安装..."
    pip install -r requirements.txt
fi

# 检查数据库
if [ ! -f "data/amq2api.db" ]; then
    echo "📦 初始化数据库..."
    python3 -c "from app.models.database import init_db; init_db()"
    echo "✅ 数据库初始化完成"
fi

# 获取端口
PORT=${PORT:-8080}

echo ""
echo "🚀 启动服务..."
echo "   端口: $PORT"
echo "   管理界面: http://localhost:$PORT/admin/dashboard"
echo "   API 文档: http://localhost:$PORT/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo "================================================"
echo ""

# 启动服务
python3 app_new.py
