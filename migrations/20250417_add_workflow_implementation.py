"""
工作流实施标记功能数据库迁移脚本
创建日期: 2026-04-17

功能说明:
1. 创建 eve_industry_plan_task_implementation 表（实施标记云端备份）
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


def upgrade():
    """升级数据库"""

    # 创建 eve_industry_plan_task_implementation 表
    op.create_table(
        "eve_industry_plan_task_implementation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_name", sa.Text(), nullable=False),
        sa.Column("plan_name", sa.Text(), nullable=False),
        sa.Column("calculation_id", sa.BigInteger(), nullable=False),
        sa.Column("workflow_item_key", sa.Text(), nullable=False),
        sa.Column("implemented", sa.Boolean(), default=True),
        sa.Column("runs_implemented", sa.Integer(), nullable=True),
        sa.Column(
            "modified_at", sa.DateTime(), default=datetime.utcnow, nullable=False
        ),
        sa.Column("modified_by_client", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_name",
            "plan_name",
            "calculation_id",
            "workflow_item_key",
            name="uq_impl_user_plan_calc_item",
        ),
        sa.Index("idx_impl_user_plan_calc", "user_name", "plan_name", "calculation_id"),
        sa.Index("idx_impl_modified", "modified_at"),
    )

    print("✓ 创建 eve_industry_plan_task_implementation 表成功")


def downgrade():
    """回滚数据库"""

    # 删除 eve_industry_plan_task_implementation 表
    op.drop_table("eve_industry_plan_task_implementation")
    print("✓ 删除 eve_industry_plan_task_implementation 表成功")


# 允许直接运行脚本
if __name__ == "__main__":
    print("请使用 alembic 运行迁移:")
    print("  alembic upgrade head")
    print("或手动执行 upgrade() 函数")
