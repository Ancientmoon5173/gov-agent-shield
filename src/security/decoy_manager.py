"""
诱饵管理器（DecoyManager）。

主动防御模块：在系统中布置模拟的敏感资源，
当 Agent 触碰这些资源时生成高可信风险事件。

这不是传统 Honeypot，而是 SecurityOrchestrator 中的一个风险信号源。
诱饵检测结果进入 RiskScorer 统一评分，不直接阻断。
"""

from pathlib import Path
from typing import Dict, Any, Optional, List

from src.config import DATA_DIR
from src.decoy_monitor import DecoyGenerator, DecoyMonitor


class DecoyManager:
    """
    诱饵管理器。

    职责：
    1. setup_decoys() — 初始化默认诱饵资源
    2. check_access() — 检查工具调用是否命中诱饵
    3. 返回风险事件供 RiskScorer 融合
    """

    def __init__(self):
        self._generator = None
        self._monitor = None
        self._initialized = False

    def setup(self, decoy_dir: Optional[Path] = None) -> None:
        """
        初始化并生成默认诱饵资源。

        Args:
            decoy_dir: 诱饵目录，默认 data/decoys
        """
        if self._initialized:
            return

        decoy_path = decoy_dir or (DATA_DIR / "decoys")
        decoy_path.mkdir(parents=True, exist_ok=True)

        # 创建 Generator 并生成所有诱饵
        generator = DecoyGenerator(decoy_path)
        self._generate_government_decoys(generator)

        # 创建 Monitor 跟踪诱饵触碰
        self._monitor = DecoyMonitor(generator.registry)
        self._generator = generator
        self._initialized = True

        total = len(generator.registry)
        print(f"[DecoyManager] 已生成 {total} 个诱饵资源: {decoy_path}")

    def _generate_government_decoys(self, generator: DecoyGenerator) -> None:
        """生成政企场景诱饵资源。"""
        # 1. 敏感文档诱饵
        generator.create_fake_contract("内部合同审批记录.docx")
        generator.create_fake_contract("财务预算审批表.xlsx")
        generator.create_fake_contract("人事信息汇总.pdf")

        # 2. 凭证诱饵
        generator.create_fake_key("fake_openai_key.txt")
        generator.create_fake_contract("admin_config.json")
        generator.create_fake_contract("secret_contract.pdf")
        generator.create_fake_contract("employee_salary.xlsx")
        generator.create_fake_contract("key_management.txt")
        generator.create_fake_contract("sensitive_report.xls")
        # 手动创建额外的凭证诱饵
        pwd_file = generator.decoy_dir / "fake_database_password.txt"
        pwd_file.write_text(
            "# 数据库密码文件（诱饵）\n\n"
            "prod_db: postgresql://sa:Decoy!P@ss@192.168.1.100:5432/gov_db\n"
            "audit_db: mysql://auditor:Decoy@ud1t@10.0.0.50:3306/audit_log\n",
            encoding="utf-8"
        )
        generator._register("file", str(pwd_file), "CRITICAL")

        # 3. 敏感目录诱饵
        generator.create_fake_dir("internal_backup")
        generator.create_fake_dir("database_backup")
        generator.create_fake_dir("secret_archive")

    def check_access(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查工具调用是否命中诱饵资源。

        不直接阻断，只返回风险事件供后续评分决策。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            {
                "triggered": bool,        # 是否命中诱饵
                "decoy_type": str,        # 诱饵类型
                "resource": str,          # 触发的资源路径
                "risk_score": float,      # 风险评分（命中=1.0）
                "detail": str,            # 检测详情
            }
        """
        if not self._initialized:
            self.setup()

        # 只检查与文件路径相关的工具
        file_param = self._extract_file_param(tool_name, params)
        if not file_param:
            return {
                "triggered": False,
                "decoy_type": "",
                "resource": "",
                "risk_score": 0.0,
                "detail": "",
            }

        # 检查路径是否匹配诱饵
        hit = self._monitor.check_access(file_param)
        
        # 如果全路径不匹配，尝试只用文件名匹配
        if not hit:
            from pathlib import Path as PPath
            fname = PPath(file_param).name
            for reg in self._monitor.registry:
                if reg["type"] == "file" and PPath(reg["path"]).name == fname:
                    hit = {
                        "triggered": True,
                        "decoy_path": reg["path"],
                        "decoy_type": reg["type"],
                        "severity": reg["level"],
                        "detail": f"文件名匹配诱饵: {fname}",
                    }
                    break
        
        if hit:
            return {
                "triggered": True,
                "decoy_type": hit.get("decoy_type", "file"),
                "resource": hit.get("decoy_path", file_param),
                "risk_score": 1.0,
                "detail": hit.get("detail", f"触碰诱饵: {file_param}"),
            }

        return {
            "triggered": False,
            "decoy_type": "",
            "resource": "",
            "risk_score": 0.0,
            "detail": "",
        }

    def _extract_file_param(self, tool_name: str, params: Dict[str, Any]) -> Optional[str]:
        """从工具参数中提取文件路径。"""
        if tool_name == "read_document":
            return params.get("file_path")
        if tool_name == "upload_data":
            return params.get("data", "")
        return None

    @property
    def registry(self) -> List[Dict[str, Any]]:
        """获取当前所有诱饵资源列表。"""
        if self._monitor:
            return self._monitor.registry
        return []

    @property
    def is_initialized(self) -> bool:
        """诱饵系统是否已初始化。"""
        return self._initialized


def create_decoy_manager() -> DecoyManager:
    """创建并初始化诱饵管理器。"""
    manager = DecoyManager()
    manager.setup()
    return manager
