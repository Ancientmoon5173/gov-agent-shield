"""
诱饵生成器。

创建模拟的敏感文件、目录和 Token，引诱攻击者触碰。
"""

import json
from pathlib import Path
from typing import List, Dict, Any


class DecoyGenerator:
    """诱饵资源生成器。"""

    def __init__(self, decoy_dir: Path):
        self.decoy_dir = Path(decoy_dir)
        self.decoy_dir.mkdir(parents=True, exist_ok=True)
        self._registry: List[Dict[str, Any]] = []

    def create_fake_contract(self, name: str = "内部合同.docx") -> Path:
        """创建一个模拟的合同文件。"""
        file_path = self.decoy_dir / name
        content = (
            f"【机密】{name}\n\n"
            f"甲方：XX市政府信息中心\n"
            f"乙方：XX科技有限公司\n\n"
            f"合同金额：8,500,000.00 元\n"
            f"项目周期：2026年8月-2027年8月\n\n"
            f"备注：本文件为诱饵文件，任何未经授权的访问将被记录。"
        )
        file_path.write_text(content, encoding="utf-8")
        self._register("file", str(file_path), "HIGH")
        return file_path

    def create_fake_key(self, name: str = "api_keys.txt") -> Path:
        """创建一个模拟的密钥文件。"""
        file_path = self.decoy_dir / name
        content = (
            f"# 系统 API 密钥（诱饵）\n\n"
            f"DATABASE_URL=postgresql://admin:decoy_password@internal-db/prod\n"
            f"AWS_SECRET_KEY=AKIA{ 'X' * 20 }\n"
            f"INTERNAL_API_KEY=sk-{'x' * 48 }\n"
        )
        file_path.write_text(content, encoding="utf-8")
        self._register("file", str(file_path), "CRITICAL")
        return file_path

    def create_fake_dir(self, name: str = "财务数据") -> Path:
        """创建一个模拟的敏感目录。"""
        dir_path = self.decoy_dir / name
        dir_path.mkdir(parents=True, exist_ok=True)

        # 在目录内放一些诱饵文件
        files = {
            "工资表.xlsx": "姓名,部门,基本工资,绩效工资,实发工资\n张三,技术部,15000,5000,18500\n",
            "预算审批.pdf.txt": "2026年度信息化建设预算\n总预算：12,000,000元\n已审批：8,500,000元\n",
        }
        for fname, content in files.items():
            (dir_path / fname).write_text(content, encoding="utf-8")

        self._register("directory", str(dir_path), "HIGH")
        return dir_path

    def _register(self, resource_type: str, path: str, level: str) -> None:
        """注册一个诱饵资源到监控列表。"""
        self._registry.append({
            "type": resource_type,
            "path": path,
            "level": level,
        })

    @property
    def registry(self) -> List[Dict[str, Any]]:
        """获取所有已注册的诱饵资源列表。"""
        return self._registry.copy()

    def setup_default_decoy(self) -> None:
        """创建一组默认的诱饵资源。"""
        self.create_fake_contract()
        self.create_fake_key()
        self.create_fake_dir()
