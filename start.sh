#!/bin/bash
# ==============================================================================
# WritingBot 一键启动脚本
# ==============================================================================
# 使用方法: chmod +x start.sh && ./start.sh
# 停止: Ctrl+C (同时停止前端和后端)
# ==============================================================================

set -e

# 颜色
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 项目目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  WritingBot 一键启动${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# 清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}正在停止所有服务...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo -e "${GREEN}所有服务已停止${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# 启动后端
echo -e "${BLUE}[1/2] 启动后端 (FastAPI on :5001)...${NC}"
cd "$PROJECT_DIR"
conda run -n writingbot python -m uvicorn src.api.main:app \
    --host 0.0.0.0 --port 5001 --reload \
    --reload-exclude "data/*" --reload-exclude "web/*" --reload-exclude ".git/*" &
BACKEND_PID=$!

# 等待后端启动
sleep 3

# 启动前端
echo -e "${BLUE}[2/2] 启动前端 (Next.js on :3000)...${NC}"
cd "$PROJECT_DIR/web"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✅ 服务启动成功！${NC}"
echo -e "${GREEN}  后端: http://localhost:5001${NC}"
echo -e "${GREEN}  前端: http://localhost:3000${NC}"
echo -e "${GREEN}  API 文档: http://localhost:5001/docs${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "${YELLOW}  按 Ctrl+C 停止所有服务${NC}"
echo ""

# 等待进程
wait $BACKEND_PID $FRONTEND_PID
