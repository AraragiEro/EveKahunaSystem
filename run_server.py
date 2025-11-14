#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quart异步后端启动脚本
支持开发和生产环境模式切换
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from hypercorn.config import Config
from hypercorn.asyncio import serve
import asyncio
from src_v2.backend.app import get_app, init_server


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='启动Quart异步后端服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_server.py --dev              # 开发模式，默认端口9527
  python run_server.py --prod             # 生产模式，默认端口9527
  python run_server.py --dev --port 8080  # 开发模式，自定义端口
  python run_server.py --prod --host 127.0.0.1  # 生产模式，仅本地访问
        """
    )
    
    # 模式选择（互斥）
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--dev', '-d',
        action='store_true',
        help='开发模式（启用热重载、调试信息）'
    )
    mode_group.add_argument(
        '--prod', '-p',
        action='store_true',
        help='生产模式（性能优化、多worker）'
    )
    
    # 服务器配置
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='服务器主机地址（默认: 0.0.0.0）'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=9527,
        help='服务器端口号（默认: 9527）'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='生产模式下的worker数量（默认: CPU核心数）'
    )
    
    return parser.parse_args()


def create_config(args):
    """创建hypercorn配置"""
    config = Config()
    config.bind = [f"{args.host}:{args.port}"]
    
    if args.dev:
        # 开发模式配置
        config.use_reload = True  # 启用热重载
        config.log_level = "DEBUG"  # 调试日志级别
        config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"  # 详细访问日志
        print(f"[开发模式] 服务器启动在 http://{args.host}:{args.port}")
        print(f"[开发模式] 热重载已启用，代码修改将自动重启服务器")
    else:
        # 生产模式配置
        config.use_reload = False
        config.log_level = "INFO"
        config.access_log_format = "%(h)s %(r)s %(s)s %(b)s"
        
        # Worker配置
        if args.workers:
            config.workers = args.workers
        else:
            # 默认使用CPU核心数
            import multiprocessing
            config.workers = multiprocessing.cpu_count()
        
        print(f"[生产模式] 服务器启动在 http://{args.host}:{args.port}")
        print(f"[生产模式] Worker数量: {config.workers}")
        print(f"[生产模式] 性能优化已启用")
    
    return config


async def main():
    """主函数"""
    args = parse_args()
    config = create_config(args)
    
    # 获取Quart应用实例
    await init_server()
    app = get_app()
    
    # 启动服务器
    try:
        await serve(app, config)
    except KeyboardInterrupt:
        print("\n[信息] 服务器已停止")
    except Exception as e:
        print(f"[错误] 服务器启动失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())

