from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import datetime

@dataclass
class AuthorisedOverrideRequest:
    override_id: str
    dispatcher_name: str
    dispatcher_role: str
    return_id: str
    target_vehicle_id: str
    constraint_overridden: str  # e.g., "MAX_ROUTE_DEVIATION", "SHIFT_OVERTIME_TOLERANCE", "DIMENSION_FIT"
    reason: str
    timestamp: str

@dataclass
class OverrideAuditRecord:
    override_id: str
    dispatcher_name: str
    dispatcher_role: str
    return_id: str
    target_vehicle_id: str
    constraint_overridden: str
    reason: str
    timestamp: str
    operational_impact: str

class OverrideManager:
    def __init__(self):
        self._overrides: Dict[str, OverrideAuditRecord] = {}

    def add_override(self, req: AuthorisedOverrideRequest, impact_summary: str) -> OverrideAuditRecord:
        record = OverrideAuditRecord(
            override_id=req.override_id,
            dispatcher_name=req.dispatcher_name,
            dispatcher_role=req.dispatcher_role,
            return_id=req.return_id,
            target_vehicle_id=req.target_vehicle_id,
            constraint_overridden=req.constraint_overridden,
            reason=req.reason,
            timestamp=req.timestamp or datetime.datetime.now().isoformat(),
            operational_impact=impact_summary
        )
        self._overrides[req.override_id] = record
        return record

    def get_overrides(self) -> List[OverrideAuditRecord]:
        return list(self._overrides.values())

    def is_return_overridden(self, return_id: str) -> Optional[OverrideAuditRecord]:
        for rec in self._overrides.values():
            if rec.return_id == return_id:
                return rec
        return None

# Global override manager instance
override_manager = OverrideManager()
