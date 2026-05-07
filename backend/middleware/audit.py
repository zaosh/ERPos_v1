from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from models.audit import AuditLog

_AUDIT_PII_KEYS = {"phone", "first_name", "last_name", "email"}


def _mask_pii(values: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not values:
        return values
    result = {}
    for k, v in values.items():
        if k in _AUDIT_PII_KEYS and v:
            if k == "phone" and isinstance(v, str) and len(v) >= 4:
                result[k] = "***" + v[-4:]
            elif isinstance(v, str) and v:
                result[k] = v[0] + "***"
            else:
                result[k] = "***"
        else:
            result[k] = v
    return result


async def write_audit_log(
    db: AsyncSession,
    table_name: str,
    record_id: int,
    action: str,
    user_id: Optional[int] = None,
    old_values: Optional[dict[str, Any]] = None,
    new_values: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        old_values=_mask_pii(old_values),
        new_values=_mask_pii(new_values),
        user_id=user_id,
        ip_address=ip_address,
    )
    db.add(entry)
