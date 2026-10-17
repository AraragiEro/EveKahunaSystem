#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移管理 CLI 工具

用法：
    # 预览即将执行的变更（dry-run）
    python -m src_v2.core.database.migration_cli --dry-run
    
    # 执行迁移
    python -m src_v2.core.database.migration_cli
    
    # 查看迁移历史
    python -m src_v2.core.database.migration_cli --history
    
    # 回滚上次迁移
    python -m src_v2.core.database.migration_cli --rollback
    
    # 开发模式（自动确认所有变更）
    python -m src_v2.core.database.migration_cli --dev

环境变量：
    MIGRATION_DRY_RUN=true      # 仅预览不执行
    MIGRATION_AUTO_CONFIRM=true # 自动确认中等风险变更
    POSTGRES_HOST               # PostgreSQL 主机
    POSTGRES_PORT               # PostgreSQL 端口
    POSTGRES_DB                 # PostgreSQL 数据库名
    POSTGRES_USER               # PostgreSQL 用户名
    POSTGRES_PASSWORD           # PostgreSQL 密码
"""

import argparse
import asyncio
import io
import os
import sys
from datetime import datetime

# 修复 Windows 控制台 Unicode 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from src_v2.core.config.config import config
from src_v2.core.database.connect_manager import PostgreDatabaseManager
from src_v2.core.database.auto_migration import AutoMigrationManager
from src_v2.core.database.model import all_model


async def show_migration_history(limit: int = 10):
    """显示迁移历史"""
    db_manager = PostgreDatabaseManager()
    
    # 初始化数据库连接
    host = os.getenv('POSTGRES_HOST') or config.get('POSTGREDB', 'Host', fallback='localhost')
    port = int(os.getenv('POSTGRES_PORT', 0)) or config.getint('POSTGREDB', 'Port', fallback=5432)
    database = os.getenv('POSTGRES_DB') or config.get('POSTGREDB', 'Database', fallback='kahunabot')
    user = os.getenv('POSTGRES_USER') or config.get('POSTGREDB', 'User', fallback='kahunabot')
    password = os.getenv('POSTGRES_PASSWORD') or config.get('POSTGREDB', 'Password', fallback='kahunabot')
    
    await db_manager.create_async_session(host, port, database, user, password)
    
    async with db_manager.engine.begin() as conn:
        from sqlalchemy import text
        
        result = await conn.execute(text(f"""
            SELECT version, timestamp, migration_type, description, success
            FROM _migration_history
            ORDER BY timestamp DESC
            LIMIT {limit}
        """))
        
        rows = result.fetchall()
        
        if not rows:
            print("没有找到迁移历史")
            return
        
        print(f"\n{'='*80}")
        print(f"最近 {len(rows)} 条迁移历史")
        print(f"{'='*80}")
        print(f"{'时间':<20} {'版本':<20} {'类型':<12} {'状态':<8} {'描述'}")
        print(f"{'-'*80}")
        
        for row in rows:
            timestamp = row[1].strftime("%Y-%m-%d %H:%M") if isinstance(row[1], datetime) else str(row[1])[:16]
            version = row[0][:18] if len(row[0]) > 18 else row[0]
            mig_type = row[2]
            status = "OK" if row[4] else "FAIL"
            desc = row[3][:30] + "..." if row[3] and len(row[3]) > 30 else (row[3] or "")
            
            print(f"{timestamp:<20} {version:<20} {mig_type:<12} {status:<8} {desc}")
        
        print(f"{'='*80}\n")
    
    await db_manager.close()


async def rollback_last_migration():
    """回滚上次迁移"""
    db_manager = PostgreDatabaseManager()
    
    # 初始化数据库连接
    host = os.getenv('POSTGRES_HOST') or config.get('POSTGREDB', 'Host', fallback='localhost')
    port = int(os.getenv('POSTGRES_PORT', 0)) or config.getint('POSTGREDB', 'Port', fallback=5432)
    database = os.getenv('POSTGRES_DB') or config.get('POSTGREDB', 'Database', fallback='kahunabot')
    user = os.getenv('POSTGRES_USER') or config.get('POSTGREDB', 'User', fallback='kahunabot')
    password = os.getenv('POSTGRES_PASSWORD') or config.get('POSTGREDB', 'Password', fallback='kahunabot')
    
    await db_manager.create_async_session(host, port, database, user, password)
    
    manager = AutoMigrationManager(db_manager)
    
    print("正在回滚上次迁移...")
    try:
        await manager.rollback_last()
        print("[OK] 回滚成功")
    except ValueError as e:
        print(f"[ERROR] {e}")
    except Exception as e:
        print(f"[ERROR] 回滚失败: {e}")
    finally:
        await db_manager.close()


async def run_migration(
    dry_run: bool = False,
    auto_confirm: bool = False,
    skip_dangerous: bool = True
):
    """运行迁移"""
    # 创建数据库管理器
    db_manager = PostgreDatabaseManager()
    
    try:
        # 初始化数据库连接（不创建表，因为我们用新的迁移系统）
        host = os.getenv('POSTGRES_HOST') or config.get('POSTGREDB', 'Host', fallback='localhost')
        port = int(os.getenv('POSTGRES_PORT', 0)) or config.getint('POSTGREDB', 'Port', fallback=5432)
        database = os.getenv('POSTGRES_DB') or config.get('POSTGREDB', 'Database', fallback='kahunabot')
        user = os.getenv('POSTGRES_USER') or config.get('POSTGREDB', 'User', fallback='kahunabot')
        password = os.getenv('POSTGRES_PASSWORD') or config.get('POSTGREDB', 'Password', fallback='kahunabot')
        
        print(f"\n连接数据库: {host}:{port}/{database}")
        await db_manager.create_async_session(host, port, database, user, password)
        
        if dry_run:
            print("\n[DRY-RUN] 模式：仅预览，不执行实际变更\n")
        
        # 创建迁移管理器并执行
        migration_manager = AutoMigrationManager(db_manager)
        
        context = await migration_manager.lifecycle_manage(
            base_classes=all_model,
            dry_run=dry_run,
            auto_confirm=auto_confirm,
            skip_dangerous=skip_dangerous
        )
        
        if not dry_run:
            print(f"\n[OK] 迁移完成！耗时 {context.execution_time_ms}ms")
            if context.changes:
                print(f"   执行了 {len(context.changes)} 项变更")
        else:
            print(f"\n[INFO] Dry-run 完成，共检测到 {len(context.changes)} 项变更")
        
    except Exception as e:
        print(f"\n[ERROR] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await db_manager.close()


def main():
    parser = argparse.ArgumentParser(
        description='数据库迁移管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览即将执行的变更
  python migration_cli.py --dry-run
  
  # 执行迁移
  python migration_cli.py
  
  # 查看最近10条迁移历史
  python migration_cli.py --history
  
  # 回滚上次迁移
  python migration_cli.py --rollback
  
  # 开发模式（自动确认所有变更）
  python migration_cli.py --dev
        """
    )
    
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='仅预览变更，不实际执行'
    )
    
    parser.add_argument(
        '--history', '-l',
        action='store_true',
        help='显示迁移历史'
    )
    
    parser.add_argument(
        '--rollback', '-r',
        action='store_true',
        help='回滚上次迁移'
    )
    
    parser.add_argument(
        '--dev',
        action='store_true',
        help='开发模式：自动确认所有变更'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='强制执行危险操作（谨慎使用）'
    )
    
    args = parser.parse_args()
    
    # 执行相应操作
    if args.history:
        asyncio.run(show_migration_history())
    elif args.rollback:
        asyncio.run(rollback_last_migration())
    else:
        asyncio.run(run_migration(
            dry_run=args.dry_run,
            auto_confirm=args.dev,
            skip_dangerous=not args.force
        ))


if __name__ == '__main__':
    main()
