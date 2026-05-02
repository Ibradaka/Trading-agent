from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
import uuid
import asyncio

from app.database import get_session
from app.models.db import Asset, Position

router = APIRouter()

VALID_ACCOUNT_TYPES = {"PEA", "PEE", "CTO", "AUTRE"}


def _format_position(pos: Position, asset: Asset) -> dict:
    return {
        "id": str(pos.id),
        "asset_id": str(pos.asset_id),
        "ticker": asset.ticker,
        "asset_name": asset.name,
        "account_type": pos.account_type,
        "quantity": float(pos.quantity),
        "avg_price": float(pos.avg_price),
        "currency": asset.currency,
        "is_pea_eligible": asset.is_pea_eligible,
        "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
        "notes": pos.notes,
        "is_active": pos.is_active,
    }


class CreatePositionBody(BaseModel):
    ticker: str
    account_type: str
    quantity: float
    avg_price: float
    notes: Optional[str] = None


class UpdatePositionBody(BaseModel):
    account_type: Optional[str] = None
    quantity: Optional[float] = None
    avg_price: Optional[float] = None
    notes: Optional[str] = None


@router.get("/positions")
async def list_positions(db: AsyncSession = Depends(get_session)):
    """Retourne toutes les positions actives avec les infos de l'actif."""
    result = await db.execute(
        select(Position, Asset)
        .join(Asset, Asset.id == Position.asset_id)
        .where(Position.is_active == True)
        .order_by(Position.opened_at.desc())
    )
    rows = result.all()
    return [_format_position(pos, asset) for pos, asset in rows]


@router.post("/positions", status_code=201)
async def create_position(data: CreatePositionBody, db: AsyncSession = Depends(get_session)):
    """Crée une nouvelle position. Crée l'actif automatiquement s'il n'existe pas."""
    if data.account_type not in VALID_ACCOUNT_TYPES:
        raise HTTPException(400, f"account_type doit être parmi {sorted(VALID_ACCOUNT_TYPES)}")
    if data.quantity <= 0:
        raise HTTPException(400, "La quantité doit être positive")
    if data.avg_price <= 0:
        raise HTTPException(400, "Le prix moyen doit être positif")

    ticker_upper = data.ticker.upper().strip()

    result = await db.execute(select(Asset).where(Asset.ticker == ticker_upper))
    asset = result.scalar_one_or_none()

    if not asset:
        from app.routers.assets import validate_ticker, _fetch_ticker_info
        validation = await validate_ticker(ticker_upper)
        if not validation.valid:
            raise HTTPException(400, f"Ticker {ticker_upper} invalide : {validation.error}")
        info = await asyncio.to_thread(_fetch_ticker_info, ticker_upper)
        asset = Asset(
            id=uuid.uuid4(),
            ticker=ticker_upper,
            name=validation.name,
            asset_type=validation.asset_type,
            exchange=validation.exchange,
            currency=validation.currency,
            sector=validation.sector,
            country=validation.country,
            is_pea_eligible=validation.is_pea_eligible,
        )
        db.add(asset)
        await db.flush()

    pos = Position(
        id=uuid.uuid4(),
        asset_id=asset.id,
        account_type=data.account_type,
        quantity=data.quantity,
        avg_price=data.avg_price,
        notes=data.notes,
    )
    db.add(pos)
    await db.flush()
    return _format_position(pos, asset)


@router.patch("/positions/{position_id}")
async def update_position(
    position_id: UUID,
    data: UpdatePositionBody,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Position, Asset)
        .join(Asset, Asset.id == Position.asset_id)
        .where(Position.id == position_id, Position.is_active == True)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "Position introuvable")
    pos, asset = row

    if data.account_type is not None:
        if data.account_type not in VALID_ACCOUNT_TYPES:
            raise HTTPException(400, f"account_type doit être parmi {sorted(VALID_ACCOUNT_TYPES)}")
        pos.account_type = data.account_type
    if data.quantity is not None:
        pos.quantity = data.quantity
    if data.avg_price is not None:
        pos.avg_price = data.avg_price
    if data.notes is not None:
        pos.notes = data.notes

    return _format_position(pos, asset)


@router.delete("/positions/{position_id}")
async def delete_position(position_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Position).where(Position.id == position_id))
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(404, "Position introuvable")
    pos.is_active = False
    return {"deleted": True}
