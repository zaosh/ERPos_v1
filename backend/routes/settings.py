"""
Public settings endpoint — exposes non-sensitive system_settings to the frontend.
Requires staff authentication (not fully public).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_staff
from models.user import User
from services import settings_service

router = APIRouter()


@router.get("/public")
async def get_public_settings(
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Returns UI-relevant settings needed by the frontend."""
    return {
        "exchange_fee_amount": await settings_service.get(db, "exchange_fee_amount") or "0",
        "exchange_window_days": str(await settings_service.get_int(db, "exchange_window_days", default=30)),
        "return_window_days": str(await settings_service.get_int(db, "return_window_days", default=14)),
        "store_name": await settings_service.get(db, "store_name") or "qstar",
        "tax_rate": await settings_service.get(db, "tax_rate") or "0",
    }
