"""
权限风险检测模块（MVP 空壳）。

当前返回 0，保留接口供后续阶段扩展。
扩展时在此实现实际权限验证逻辑。
"""


class PermissionChecker:
    """权限风险检测器。"""

    def calculate_permission_risk(self, context: dict = None) -> float:
        """
        计算权限风险评分。

        MVP 阶段返回 0，后续实现：
        - 会话权限校验
        - 操作权限校验
        - 敏感资源分级访问

        Args:
            context: 权限上下文（用户角色、会话凭证等）

        Returns:
            权限风险评分 0-1
        """
        return 0.0

    def check_resource_access(self, resource_path: str, user_role: str = "") -> dict:
        """
        检查资源访问权限（预留接口）。

        Args:
            resource_path: 资源路径
            user_role: 用户角色

        Returns:
            {"allowed": bool, "reason": str}
        """
        return {"allowed": True, "reason": "权限检查未启用（MVP）"}


def create_permission_checker() -> PermissionChecker:
    """创建权限检测器实例。"""
    return PermissionChecker()
