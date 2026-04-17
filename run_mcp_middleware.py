#!/usr/bin/env python3
"""
启动 MCP 中间层服务

使用方法:
    uv run python run_mcp_middleware.py
    uv run python run_mcp_middleware.py --port 9000 --quart-url http://localhost:9527
"""

import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src_v2.mcp_middleware.server import main

if __name__ == "__main__":
    main()
