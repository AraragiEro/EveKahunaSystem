"""
工作流任务接取约束诊断与修复脚本 v2

功能:
  --diagnose  只读检查当前 UNIQUE 约束状态
  --fix       安全替换旧约束 uq_task_claim_per_item 为新约束 uq_task_claim_per_user_item

用法:
  python migrations/fix_claim_constraint_v2.py --diagnose
  python migrations/fix_claim_constraint_v2.py --fix
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src_v2.core.database.connect_manager import get_postgres_manager
from sqlalchemy import text


DIAGNOSE_SQL = text("""
    SELECT
        tc.constraint_name,
        kcu.column_name,
        kcu.ordinal_position
    FROM
        information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
    WHERE
        tc.table_name = 'eve_industry_plan_task_claim'
        AND tc.constraint_type = 'UNIQUE'
    ORDER BY
        tc.constraint_name,
        kcu.ordinal_position
""")


async def diagnose(session) -> list[dict]:
    """查询并打印当前 UNIQUE 约束，返回约束列表。"""
    result = await session.execute(DIAGNOSE_SQL)

    constraints: dict[str, list[tuple[int, str]]] = {}
    for row in result:
        name = row[0]
        col = row[1]
        pos = row[2]
        constraints.setdefault(name, []).append((pos, col))

    if not constraints:
        print("  当前无 UNIQUE 约束")
        return []

    constraint_list = []
    for name in sorted(constraints):
        cols = [c[1] for c in sorted(constraints[name])]
        cols_str = ", ".join(cols)
        print(f"  - {name}: ({cols_str})")
        constraint_list.append({"name": name, "columns": cols})

    return constraint_list


async def run_diagnose():
    """--diagnose 模式：只读检查。"""
    print("=" * 60)
    print("  约束诊断模式（只读）")
    print("=" * 60)

    pm = get_postgres_manager()
    await pm.init(subprocess=True)
    async with pm.get_session() as session:
        print("\n📋 表 eve_industry_plan_task_claim 当前 UNIQUE 约束状态：")
        await diagnose(session)

    print("\n✅ 诊断完成，未做任何修改。")


async def run_fix():
    """--fix 模式：替换约束。"""
    print("=" * 60)
    print("  约束修复模式")
    print("=" * 60)

    pm = get_postgres_manager()
    await pm.init(subprocess=True)
    async with pm.get_session() as session:
        # Step 1: 诊断当前状态
        print("\n📋 修复前约束状态：")
        await diagnose(session)

        # Step 2: 删除旧约束（安全 - IF EXISTS）
        print("\n🔧 步骤 1/3：删除旧约束 uq_task_claim_per_item...")
        try:
            await session.execute(text("""
                ALTER TABLE eve_industry_plan_task_claim
                DROP CONSTRAINT IF EXISTS uq_task_claim_per_item
            """))
            print("  ✅ 删除成功（或不存在）")
        except Exception as e:
            print(f"  ❌ 删除失败: {e}")
            await session.rollback()
            return False

        # Step 3: 创建新约束（处理 "already exists" 错误实现幂等）
        print("\n🔧 步骤 2/3：创建新约束 uq_task_claim_per_user_item...")
        try:
            await session.execute(text("""
                ALTER TABLE eve_industry_plan_task_claim
                ADD CONSTRAINT uq_task_claim_per_user_item
                UNIQUE (plan_token, workflow_item_key, claimed_by)
            """))
            print("  ✅ 创建成功")
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg:
                await session.rollback()
                print("  ⏭️  约束已存在，跳过创建")
            else:
                print(f"  ❌ 创建失败: {e}")
                await session.rollback()
                return False

        # Step 4: 验证最终状态
        print("\n🔧 步骤 3/3：验证修复结果...")
        print("\n📋 修复后约束状态：")
        final_constraints = await diagnose(session)

        await session.commit()

        # Step 5: 打印总结
        print("\n" + "=" * 60)
        has_new = any(c["name"] == "uq_task_claim_per_user_item" for c in final_constraints)
        has_old = any(c["name"] == "uq_task_claim_per_item" for c in final_constraints)

        if has_new and not has_old:
            print("  ✅ 修复完成！新约束已生效。")
            print("  约束: uq_task_claim_per_user_item (plan_token, workflow_item_key, claimed_by)")
        elif has_new and has_old:
            print("  ⚠️  修复部分完成：新旧约束同时存在。请检查。")
        else:
            print("  ❌ 修复失败：新约束未创建成功。")

        return True


def main():
    parser = argparse.ArgumentParser(
        description="修复 eve_industry_plan_task_claim 表 UNIQUE 约束"
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="只读诊断模式：检查当前 UNIQUE 约束状态",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="修复模式：替换旧约束 uq_task_claim_per_item 为新约束",
    )

    args = parser.parse_args()

    if not args.diagnose and not args.fix:
        parser.print_help()
        sys.exit(0)

    if args.diagnose:
        asyncio.run(run_diagnose())
    else:
        result = asyncio.run(run_fix())
        sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
