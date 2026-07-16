"""
审计报告生成器。
"""
from datetime import datetime
from typing import Dict, Any

class AuditReporter:
    def __init__(self, logger):
        self.logger = logger

    def generate_incident_report(self, session_id: str) -> Dict[str, Any]:
        events = self.logger.get_events_by_session(session_id)
        high_risk = [e for e in events if e["risk_level"] in ("HIGH", "CRITICAL")]
        return dict(session_id=session_id, generated_at=datetime.now().isoformat(), total_events=len(events), high_risk_count=len(high_risk), timeline=events, summary=f'会话 {session_id} 共触发 {len(events)} 条事件')

    def generate_summary(self):
        events = self.logger.get_recent_events(200)
        level_counts = {}
        for e in events:
            lv = e["risk_level"]
            level_counts[lv] = level_counts.get(lv, 0) + 1
        return dict(generated_at=datetime.now().isoformat(), total_events=len(events), level_distribution=level_counts)
