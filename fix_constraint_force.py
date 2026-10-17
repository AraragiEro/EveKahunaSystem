"""
强力修复数据库约束 - 使用原始SQL
"""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# 数据库配置
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "192.168.5.2"),
    "port": os.getenv("POSTGRES_PORT", "62011"),
    "database": os.getenv("POSTGRES_DB", "kahunabot"),
    "user": os.getenv("POSTGRES_USER", "kahunabot"),
    "password": os.getenv("POSTGRES_PASSWORD", "kahunabot"),
}


async def fix_constraint_force():
    """强力修复约束"""
    database_url = f"postgresql+asyncpg://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    engine = create_async_engine(database_url)
    
    async with engine.connect() as conn:
        # 开始事务
        trans = await conn.begin()
        
        try:
            print("Step 1: 检查现有约束...")
            result = await conn.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'eve_industry_plan_task_claim' 
                AND constraint_type = 'UNIQUE'
            """))
            existing = [row[0] for row in result]
            print(f"  现有约束: {existing}")
            
            print("\nStep 2: 删除所有旧约束...")
            for constraint_name in existing:
                try:
                    await conn.execute(text(f"""
                        ALTER TABLE eve_industry_plan_task_claim 
                        DROP CONSTRAINT IF EXISTS "{constraint_name}"
                    """))
                    print(f"  删除: {constraint_name}")
                except Exception as e:
                    print(f"  删除 {constraint_name} 失败: {e}")
            
            print("\nStep 3: 创建新约束...")
            await conn.execute(text("""
                ALTER TABLE eve_industry_plan_task_claim 
                ADD CONSTRAINT uq_task_claim_per_user_item 
                UNIQUE (plan_token, workflow_item_key, claimed_by)
            """))
            print("  创建成功: uq_task_claim_per_user_item")
            
            # 提交事务
            await trans.commit()
            print("\n  [COMMIT] 事务已提交")
            
        except Exception as e:
            await trans.rollback()
            print(f"\n  [ROLLBACK] 事务回滚: {e}")
            raise
    
    # 验证
    print("\nStep 4: 验证结果...")
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT tc.constraint_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'eve_industry_plan_task_claim' 
            AND tc.constraint_type = 'UNIQUE'
            ORDER BY kcu.ordinal_position
        """))
        
        constraints = {}
        for row in result:
            name = row[0]
            col = row[1]
            if name not in constraints:
                constraints[name] = []
            constraints[name].append(col)
        
        for name, cols in constraints.items():
            print(f"  - {name}: {', '.join(cols)}")
    
    print("\n修复完成!")


if __name__ == "__main__":
    asyncio.run(fix_constraint_force())
