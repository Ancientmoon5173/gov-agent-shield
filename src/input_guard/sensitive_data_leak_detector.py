"""Sensitive Data Leak Detector."""
class SensitiveDataLeakDetector:
    SENSITIVE_DATA = ["工资","薪酬","奖金","绩效","居民","公民","个人","身份证","社保","合同","协议","员工","人事","档案","客户","供应商","合作伙伴","内部","机密","保密","秘密","财务","预算","审计","密钥","密码","凭证"]
    EXFIL_ACTIONS = ["发送","上传","导出","共享","同步","转交","提交","提供给","传输","外发","转发","泄露","窃取","备份"]
    EXTERNAL_TARGETS = ["外部","外网","邮箱","服务器","ftp","smtp","http","第三方","外部联系人","外部邮箱","外部服务器"]
    def scan(self, text):
        cats = (1 if any(p in text for p in self.SENSITIVE_DATA) else 0) \
             + (1 if any(a in text for a in self.EXFIL_ACTIONS) else 0) \
             + (1 if any(t in text for t in self.EXTERNAL_TARGETS) else 0)
        if cats >= 3:
            return {"risk_score": 0.9, "risk_level": "CRITICAL", "findings": [{"rule_name": "leak_data_exfil_all", "type": "data_exfiltration", "detail": "数据外泄:敏感数据+外发+外部目标", "score": 0.9}], "is_attack": True}
        elif cats >= 2:
            return {"risk_score": 0.7, "risk_level": "VERY_HIGH", "findings": [{"rule_name": "leak_data_exfil_partial", "type": "data_exfiltration", "detail": "可疑外发:部分组件匹配", "score": 0.7}], "is_attack": True}
        elif cats >= 1:
            return {"risk_score": 0.4, "risk_level": "MEDIUM", "findings": [{"rule_name": "leak_data_exfil_single", "type": "data_exfiltration", "detail": "单项外发指标", "score": 0.4}], "is_attack": False}
        return {"risk_score": 0.0, "risk_level": "LOW", "findings": [], "is_attack": False}