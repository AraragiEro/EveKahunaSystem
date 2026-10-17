"""权限变更的纵深防御守卫

安全审计分册 03 #14：`admin:write` 权限粒度过粗，仅凭该权限即可执行"授予权限"
类的写操作，存在三条真实问题：

1. **自我升级**：持有 admin:write 的非管理员账号可调用
   `POST /api/permission/users/roles` 把自己加成 admin 角色；
2. **横向扩散**：可通过 `POST /api/permission/roles/permissions` 把 admin:write
   加到任意角色上，从而持久化扩散写权限；
3. **越权发 VIP**：`PUT /api/vip/<user_name>` 只需 admin:write 就能给自己或他人
   发放 vip_alpha / vip_omega，而 role_required 会把 VIP 等级当作角色使用，
   等于解锁企业版 / 资产 / 工业等全部付费接口。

因此本模块统一提供"操作者必须是真管理员"的判定（复用
`src_v2.backend.auth.is_admin_user`，含角色继承语义）、自我授予 admin 的拦截，
以及不留口令 / token 的审计日志。

角色继承语义提醒：`add_role_hierarchy('user', 'admin')` 表示 admin 是 user 的
子角色、admin 继承 user 的权限；`get_all_descendant_roles(role)` 实际返回的是
**父角色**。判定真管理员一律走 `is_admin_user`，不要在本模块重写继承逻辑。
"""
from src_v2.backend.auth import is_admin_user
from src_v2.core.log import logger

# 无管理员身份时的统一提示（中文）
_ADMIN_REQUIRED_MESSAGE = "需要管理员（admin）角色才能执行该操作"


class GrantDenied(Exception):
    """权限授予被拒绝

    用于表示"操作者不具备执行权限变更所需的管理员身份"。
    由 API 层捕获后统一转成 403 响应。
    """


async def assert_admin_operator(operator_id: str) -> None:
    """断言操作者具备 admin 角色（含其继承的父角色）

    Args:
        operator_id: 操作者用户 ID（即 JWT 中的 user_id，本项目与 user_name 一致）

    Raises:
        GrantDenied: 操作者不是管理员，或身份无法确认（fail-closed）
    """
    operator_id = (operator_id or "").strip()
    if not operator_id:
        raise GrantDenied(_ADMIN_REQUIRED_MESSAGE)

    try:
        admin = await is_admin_user(operator_id)
    except Exception as exc:  # 判定失败一律按"不是管理员"处理，避免放行
        logger.warning(f"校验操作者 {operator_id} 的管理员身份失败: {exc}")
        admin = False

    if not admin:
        raise GrantDenied(_ADMIN_REQUIRED_MESSAGE)


def audit_grant(operator: str, action: str, target: str, item: str) -> None:
    """记录权限变更审计日志

    只记录操作者、动作、目标与变更项，**绝不记录口令 / token 等凭据**。

    Args:
        operator: 操作者用户 ID
        action: 动作标识，如 add-role-to-user / update-vip
        target: 变更目标，如目标用户名或角色名
        item: 变更项，如角色名、权限名或 VIP 等级
    """
    logger.info(
        f"[grant-audit] operator={operator} action={action} target={target} item={item}"
    )


def is_self_admin_grant(operator: str, target_user: str, role_name: str) -> bool:
    """判定是否为"给自己授予 admin 角色"的自我升级操作

    纵深防御：即使操作者已经是管理员，也拒绝重复自授 admin，
    避免出现"先降权再自授"或误操作导致的权限链异常。

    Args:
        operator: 操作者用户 ID
        target_user: 请求体中的目标用户名
        role_name: 请求体中的角色名

    Returns:
        bool: 操作者与目标相同且角色为 admin 时返回 True
    """
    if not operator or not target_user or not role_name:
        return False
    return (
        str(operator).strip() == str(target_user).strip()
        and str(role_name).strip() == "admin"
    )
