import os
import json
import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

@dataclass
class AuthorisedOverrideRequest:
    override_id: str
    dispatcher_name: str
    dispatcher_role: str
    return_id: str
    target_vehicle_id: str
    constraint_overridden: str
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
    """
    Persistent Dispatcher Authorised Override Manager.
    Persists all override audit logs to data/override_audit_store.json for auditability.
    """
    def __init__(self, store_path: Optional[str] = None):
        if store_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
            store_path = os.path.join(base_dir, "override_audit_store.json")
        self.store_path = store_path
        self._overrides: Dict[str, OverrideAuditRecord] = {}
        self._load_store()

    def _load_store(self):
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        rec = OverrideAuditRecord(**item)
                        self._overrides[rec.override_id] = rec
            except Exception as e:
                print(f"Warning: Could not load override store: {e}")

    def _save_store(self):
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            with open(self.store_path, 'w', encoding='utf-8') as f:
                json.dump([asdict(r) for r in self._overrides.values()], f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save override store: {e}")

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
        self._save_store()
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
