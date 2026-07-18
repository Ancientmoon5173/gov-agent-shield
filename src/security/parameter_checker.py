"""
参数风险检测模块。

检测工具调用参数中的风险因子：
- 文件名含敏感关键词
- 路径穿越攻击
- 批量查询
- 身份证完整暴露
- 目标地址异常
"""

import re
from typing import Dict, Any

from .tool_risk_config import get_tool_risk_rules


class ParameterChecker:
    """参数风险检测器。"""

    def check(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        检测工具调用的参数风险。

        Returns:
            {
                "risk_score": float,    # 参数风险增量
                "findings": [str],      # 检测发现列表
            }
        """
        rules = get_tool_risk_rules(tool_name)
        if not rules:
            return {"risk_score": 0.0, "findings": []}

        risk = 0.0
        findings = []

        if tool_name == "read_document":
            result = self._check_read_document(params, rules)
            risk += result["risk_score"]
            findings.extend(result["findings"])

        elif tool_name == "query_citizen_info":
            result = self._check_query_citizen(params, rules)
            risk += result["risk_score"]
            findings.extend(result["findings"])

        elif tool_name == "upload_data":
            result = self._check_upload_data(params, rules)
            risk += result["risk_score"]
            findings.extend(result["findings"])

        return {"risk_score": min(risk, 1.0), "findings": findings}

    def _check_read_document(self, params: Dict[str, Any], rules: dict) -> Dict:
        """检测 read_document 的参数。"""
        risk = 0.0
        findings = []
        file_path = str(params.get("file_path", ""))

        if not file_path:
            return {"risk_score": 0.0, "findings": []}

        # 1. 路径穿越检测
        for pattern in rules.get("path_traversal_patterns", []):
            if pattern in file_path:
                risk += rules.get("traversal_penalty", 0.5)
                findings.append(f"路径穿越尝试: {file_path}")
                break

        # 2. 敏感关键词检测
        for keyword in rules.get("sensitive_keywords", []):
            if keyword.lower() in file_path.lower():
                risk += rules.get("keyword_penalty", 0.3)
                findings.append(f"文件名含敏感词: {keyword}")
                break

        return {"risk_score": min(risk, 1.0), "findings": findings}

    def _check_query_citizen(self, params: Dict[str, Any], rules: dict) -> Dict:
        """检测 query_citizen_info 的参数。"""
        risk = 0.0
        findings = []
        name = str(params.get("name", ""))
        id_number = str(params.get("id_number", ""))

        # 1. 批量查询检测
        for keyword in rules.get("batch_keywords", []):
            if keyword.lower() in name.lower() or keyword in name:
                risk += rules.get("batch_penalty", 0.3)
                findings.append(f"批量查询嫌疑: name={name}")
                break

        # 2. 完整身份证检测
        id_pattern = rules.get("full_id_pattern", "")
        if id_pattern and id_number:
            if re.match(id_pattern, id_number):
                risk += rules.get("full_id_penalty", 0.2)
                findings.append("身份证号码完整未脱敏")

        return {"risk_score": min(risk, 1.0), "findings": findings}

    def _check_upload_data(self, params: Dict[str, Any], rules: dict) -> Dict:
        """检测 upload_data 的参数。"""
        risk = 0.0
        findings = []
        target = str(params.get("target", ""))

        if not target:
            return {"risk_score": 0.0, "findings": []}

        for pattern in rules.get("external_target_patterns", []):
            if pattern in target.lower():
                risk += rules.get("target_penalty", 0.2)
                findings.append(f"外部目标地址: {target}")
                break

        return {"risk_score": min(risk, 1.0), "findings": findings}


def create_parameter_checker() -> ParameterChecker:
    """创建参数检测器实例。"""
    return ParameterChecker()
