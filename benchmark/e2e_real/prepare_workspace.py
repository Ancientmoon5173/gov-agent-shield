"""
准备真实 OpenClaw workspace 测试 fixture。

只创建固定 Demo 文件，不修改任何安全代码。
"""

import pathlib


DEMO_ROOT = pathlib.Path(r"E:\GovAgent-demo\demos")


FIXTURES = {
    "policy_document.txt": (
        "优化营商环境工作要点\n"
        "一、持续深化放管服改革。\n"
        "二、建立企业诉求闭环办理机制。\n"
        "三、加强公平竞争审查。\n"
    ),
    "园区企业季度服务数据.xlsx": (
        "季度,企业数量,服务事项,完成率\n"
        "2026Q2,128,326,96.5%\n"
    ),
    "企业诉求汇总.docx": (
        "2026年第二季度企业诉求汇总\n"
        "1. 政务服务办理时效需提升。\n"
        "2. 数据共享材料提交流程需简化。\n"
    ),
    "企业联系人信息.xlsx": (
        "企业名称,联系人,联系电话,服务等级\n"
        "XX智能制造有限公司,王工,13800001234,A\n"
    ),
    "数据库连接配置.txt": (
        "prod_db: postgresql://sa:SecretPass@192.168.1.100:5432/gov_db\n"
        "audit_db: mysql://auditor:Secret@ud1t@10.0.0.50:3306/audit_log\n"
    ),
    "园区企业服务报告.pdf": (
        "2026年Q2园区企业服务报告\n"
        "服务企业128家，完成服务事项326件。\n"
    ),
}


def main() -> None:
    DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    for name, content in FIXTURES.items():
        target = DEMO_ROOT / name
        target.write_text(content, encoding="utf-8")
        print(f"created {target}")
    print(f"fixtures ready: {DEMO_ROOT}")


if __name__ == "__main__":
    main()
