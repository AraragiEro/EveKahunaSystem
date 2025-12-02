import argparse
import sys
import asyncio
import platform
import signal
from pathlib import Path

from hypercorn.config import Config
from hypercorn.asyncio import serve
from src_v2.backend.app import get_app, serve_vue
from src_v2.core import init_database
from src_v2.model.EVE.eveesi import init_esi_manager
from src_v2.core.permission.permission_manager import permission_manager
from src_v2.core.user.user_manager import UserManager
from src_v2.core.config.config import config
from werkzeug.security import generate_password_hash
from src_v2.core.log import logger

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 全局变量用于存储清理函数
_cleanup_tasks = []

def parse_args():
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dev", "-d", action="store_true")
    group.add_argument("--prod", "-p", action="store_true")

    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9527)

    return parser.parse_args()


async def cleanup_resources():
    """清理所有资源"""
    from src_v2.core.database.connect_manager import postgres_manager, redis_manager, neo4j_manager
    from src_v2.model.EVE.eveesi import shutdown_esi_manager
    
    try:
        # 关闭 ESI 管理器
        await shutdown_esi_manager()
    except Exception as e:
        print(f"[清理] ESI 管理器关闭时出错: {e}")
    
    try:
        # 关闭 Neo4j 连接
        await neo4j_manager.close()
    except Exception as e:
        # 如果 Python 正在关闭，忽略 ImportError
        if "sys.meta_path is None" not in str(e) and "shutting down" not in str(e).lower():
            print(f"[清理] Neo4j 连接关闭时出错: {e}")
    
    try:
        # 关闭 PostgreSQL 连接
        await postgres_manager.close()
    except Exception as e:
        print(f"[清理] PostgreSQL 连接关闭时出错: {e}")
    
    try:
        # 关闭 SDE 数据库连接
        from src_v2.model.EVE.sde.utils import SdeUtils
        await SdeUtils.close_database()
    except Exception as e:
        print(f"[清理] SDE 数据库连接关闭时出错: {e}")
    
    try:
        # 关闭 Redis 连接（如果有 close 方法）
        if hasattr(redis_manager, 'close'):
            await redis_manager.close()
    except Exception as e:
        print(f"[清理] Redis 连接关闭时出错: {e}")


def setup_signal_handlers():
    """设置信号处理器以优雅关闭"""
    def signal_handler(signum, frame):
        print(f"\n[信号] 收到信号 {signum}，开始优雅关闭...")
        # 创建新的事件循环来执行清理
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建任务
                asyncio.create_task(cleanup_resources())
            else:
                # 否则直接运行
                loop.run_until_complete(cleanup_resources())
        except Exception as e:
            print(f"[清理] 信号处理器执行清理时出错: {e}")
        sys.exit(0)
    
    # 注册信号处理器（Windows 上只支持 SIGINT）
    if platform.system() != "Windows":
        signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


async def main():
    args = parse_args()

    config = Config()
    config.bind = [f"{args.host}:{args.port}"]

    # 配置 worker 模式：优先使用 uvloop（性能更好），否则使用 asyncio
    # 注意：uvloop 在 Windows 上不支持，会自动回退到 asyncio
    if platform.system() != "Windows":
        try:
            import uvloop
            config.worker_class = "uvloop"
            print("[性能优化] 使用 uvloop 事件循环（高性能模式）")
        except ImportError:
            config.worker_class = "asyncio"
            print("[默认模式] 使用 asyncio 事件循环（安装 uvloop 可提升性能：pip install uvloop）")
    else:
        config.worker_class = "asyncio"
        print("[Windows 模式] 使用 asyncio 事件循环（uvloop 不支持 Windows）")

    if args.dev:
        # 🔥 关键点：Hypercorn 0.18 就是用这个重载
        config.use_reloader = True
        print("[开发模式] 热重载已启用（默认监控整个项目目录）")
    else:
        config.use_reloader = False
        print("[生产模式] 正常启动")

    # 设置信号处理器
    setup_signal_handlers()

    # 初始化数据库和基础服务
    await init_database()
    from src_v2.model.EVE.sde.utils import SdeUtils
    await SdeUtils.init_database()
    await init_esi_manager()
    await permission_manager.init_base_roles()

    # 检查并创建默认管理员账号
    try:
        create_admin = config.getboolean('ADMIN', 'create_admin', fallback=False)
        if create_admin:
            admin_user = config.get('ADMIN', 'admin_user', fallback='kahuna')
            admin_passwd = config.get('ADMIN', 'admin_passwd', fallback='kahuna')
            
            logger.info(f"检查管理员账号创建配置: CREATE_ADMIN={create_admin}, ADMIN_USER={admin_user}")
            
            # 检查用户是否已存在
            user_manager = UserManager()
            existing_user = await user_manager.get_user(admin_user)
            
            if existing_user:
                logger.info(f"管理员账号 '{admin_user}' 已存在，跳过创建")
            else:
                # 创建管理员账号
                logger.info(f"开始创建管理员账号: {admin_user}")
                passwd_hash = generate_password_hash(admin_passwd)
                await user_manager.create_user(admin_user, passwd_hash)
                logger.info(f"管理员账号 '{admin_user}' 创建成功")
                
                # 赋予 admin 角色
                try:
                    await permission_manager.add_role_to_user(admin_user, 'admin')
                    logger.info(f"已为管理员账号 '{admin_user}' 赋予 admin 角色")
                except ValueError as e:
                    # 如果角色已存在或其他错误，记录日志但不中断启动
                    logger.warning(f"为管理员账号 '{admin_user}' 赋予 admin 角色时出错: {e}")
        else:
            logger.info("CREATE_ADMIN 配置为 false，跳过管理员账号创建")
    except Exception as e:
        logger.error(f"创建管理员账号时发生错误: {e}", exc_info=True)
        # 不中断启动流程，只记录错误

    from src_v2.core.database.connect_manager import redis_manager
    # await redis_manager.r.flushall()

    # 仅在版本为企业版且模块存在时注册
    from src_v2.core.edition import is_enterprise
    if is_enterprise():
        try:
            from src_v2.enterprise.model.market_history_refresh_timer import MarketHistoryRefreshTimer
            MarketHistoryRefreshTimer().start()
            logger.info("市场历史数据刷新定时器已启动")
        except ImportError as e:
            logger.warning(f"企业版 model 模块不存在，跳过注册: {e}")
        except Exception as e:
            logger.error(f"注册企业版 model 时发生错误: {e}")

    # 初始化 Quart App
    app = get_app()
    
    # 生产模式下启用前端静态文件服务
    if args.prod:
        serve_vue()
        print("[生产模式] 前端静态文件服务已启用")

    print(f"启动服务器：http://{args.host}:{args.port}")

    try:
        # 0.18 reloader 逻辑内置在 serve() 里
        await serve(app, config)
    finally:
        # 确保在退出前清理资源
        print("[清理] 开始清理资源...")
        await cleanup_resources()
        print("[清理] 资源清理完成")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[中断] 收到键盘中断，正在退出...")
    except Exception as e:
        print(f"[错误] 启动失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 最后的清理尝试
        try:
            import sys
            if sys.meta_path is not None:  # 只有在 Python 还未完全关闭时才尝试清理
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(cleanup_resources())
                loop.close()
        except Exception:
            pass  # 忽略清理时的所有错误
