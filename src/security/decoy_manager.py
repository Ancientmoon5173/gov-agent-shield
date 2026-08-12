"""
诱饵管理器（DecoyManager）。

主动防御模块：在系统中布置模拟的敏感资源，
当 Agent 触碰这些资源时生成高可信风险事件。

这不是传统 Honeypot，而是 SecurityOrchestrator 中的一个风险信号源。
诱饵检测结果进入 RiskScorer 统一评分，不直接阻断。
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from src.config import DATA_DIR, DECOY_ROUTE_MAPPING_PATH, DECOY_ROUTE_CONFIG
from src.decoy_monitor import DecoyGenerator, DecoyMonitor
from src.security.decoy_copy_generator import (
    DecoyCopyGenerator,
    create_decoy_copy_generator,
)
from src.security.file_access import extract_file_references


class DecoyManager:
    """
    诱饵管理器。

    职责：
    1. setup_decoys() — 初始化默认诱饵资源
    2. check_access() — 检查工具调用是否命中诱饵
    3. 返回风险事件供 RiskScorer 融合
    """

    def __init__(self, copy_generator: Optional[DecoyCopyGenerator] = None):
        self._generator = None
        self._monitor = None
        self._initialized = False
        self._route_config = dict(DECOY_ROUTE_CONFIG)
        self._route_mapping = self._load_route_mapping()
        self._route_cooldown: Dict[str, float] = {}
        self.copy_generator = copy_generator or create_decoy_copy_generator()

    def _load_route_mapping(self) -> Dict[str, Any]:
        path = Path(DECOY_ROUTE_MAPPING_PATH)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

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

        # 通用文件引用提取：专有字段 + command 字符串
        candidates = self._extract_file_params(params)
        if not candidates:
            # 兜底：任何参数文本中出现诱饵文件名也视为触碰
            candidates = self._file_name_candidates_from_text(params)

        for file_param in candidates:
            hit = self._monitor.check_access(file_param)

            # 全路径不匹配时，尝试文件名匹配
            if not hit:
                fname = Path(file_param).name
                for reg in self._monitor.registry:
                    if (
                        reg["type"] == "file"
                        and Path(reg["path"]).name == fname
                    ):
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

    def _extract_file_params(self, params: Dict[str, Any]) -> List[str]:
        """提取所有候选文件引用（通用解析，不依赖工具名）。"""
        return extract_file_references(params)

    def _file_name_candidates_from_text(self, params: Dict[str, Any]) -> List[str]:
        """当参数中没有显式路径时，扫描文本中的诱饵文件名。"""
        text = self._collect_text(params)
        if not text:
            return []
        hits = []
        for reg in self._monitor.registry:
            if reg["type"] != "file":
                continue
            name = Path(reg["path"]).name
            if name and name in text:
                hits.append(name)
        return hits

    def _collect_text(self, params: Dict[str, Any]) -> str:
        """递归收集参数中的所有字符串文本。"""
        parts: List[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                for v in value.values():
                    walk(v)
            elif isinstance(value, (list, tuple)):
                for v in value:
                    walk(v)

        walk(params or {})
        return " ".join(parts)

    def build_route(
        self,
        session_id: str,
        tool_name: str,
        params: Dict[str, Any],
        asset_context: Dict[str, Any],
        risk_score: float,
    ) -> Dict[str, Any]:
        """
        Shadow Decoy 路由决策（方案 A）。

        仅在高风险会话 + 敏感资产命中 + 允许工具类型时产生
        执行目标重定向建议；默认 dry-run，只审计不改写。
        """
        empty = {
            "matched": False,
            "enabled": False,
            "dry_run": self._route_config.get("dry_run", True),
            "original_target": "",
            "redirect_target": "",
            "reason": "",
            "policy_id": "",
        }

        if not self._route_config.get("enabled", True):
            return empty

        redirect_tools = self._route_config.get(
            "redirect_tools", ["read_document", "list_directory", "search_files"]
        )
        if tool_name not in redirect_tools:
            return empty

        original_target = self._extract_file_param(tool_name, params)
        if not original_target:
            return empty
        original_target = str(original_target)

        if not asset_context.get("matched"):
            return empty

        asset_type = str(asset_context.get("asset_type", ""))
        sensitivity = str(asset_context.get("sensitivity", "LOW"))
        mapping = self._find_mapping(asset_type, sensitivity)
        if not mapping:
            return empty

        min_risk = float(self._route_config.get("min_risk_score", 0.7))
        if float(risk_score) < min_risk:
            return empty

        cooldown_key = f"{session_id}:{asset_type}"
        now = time.time()
        last = self._route_cooldown.get(cooldown_key, 0.0)
        cooldown = int(self._route_config.get("cooldown_seconds", 300))
        if now - last < cooldown:
            return empty
        self._route_cooldown[cooldown_key] = now

        filename = Path(original_target).name
        template = str(mapping.get("template", "{filename}"))
        engine_root = str(
            self._route_mapping.get("engine_decoy_root", "/engine/decoy/")
        )
        redirect_target = engine_root + template.format(filename=filename)

        # 安全约束：重定向目标必须位于引擎诱饵根目录内，且禁止路径穿越
        if not redirect_target.startswith(engine_root):
            return empty
        if ".." in redirect_target.split("/"):
            return empty

        dry_run = bool(self._route_config.get("dry_run", True))
        result = {
            "matched": True,
            "enabled": not dry_run,
            "dry_run": dry_run,
            "original_target": original_target,
            "redirect_target": redirect_target,
            "reason": f"高风险会话访问敏感资产: {asset_type}",
            "policy_id": f"decoy_route:{asset_type}",
        }

        # C-2a：实际启用时生成会话级诱饵副本并预埋数据溯源令牌
        if not dry_run:
            copy = self.copy_generator.create_copy(
                session_id=session_id,
                asset_type=asset_type,
                filename=filename,
                original_target=original_target,
            )
            if copy.get("created"):
                result["redirect_target"] = copy["copy_path"]
                result["token"] = copy["token"]
                result["copy_id"] = copy["copy_id"]
                result["inject_mode"] = copy["inject_mode"]
            else:
                # fail-safe：副本部署失败则不重定向，避免误指向缺失文件
                result["matched"] = False
                result["enabled"] = False
                result["redirect_target"] = ""
                result["deployment_missing"] = True
                result["deployment_reason"] = copy.get(
                    "reason", "decoy_copy_failed"
                )

        return result

    def _find_mapping(
        self, asset_type: str, sensitivity: str
    ) -> Optional[Dict[str, Any]]:
        mappings = self._route_mapping.get("mappings", [])
        for mapping in mappings:
            if mapping.get("asset_type") != asset_type:
                continue
            min_sensitivity = str(mapping.get("min_sensitivity", "HIGH"))
            if self._sensitivity_rank(sensitivity) < self._sensitivity_rank(
                min_sensitivity
            ):
                continue
            return mapping
        return None

    def _sensitivity_rank(self, level: str) -> int:
        return {
            "LOW": 0,
            "MEDIUM": 1,
            "SENSITIVE": 2,
            "HIGH": 3,
            "CRITICAL": 4,
        }.get(level.upper(), 0)

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
