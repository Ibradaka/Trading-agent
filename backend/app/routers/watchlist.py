from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
import uuid

from app.database import get_session
from app.models.db import Watchlist, Asset, WatchlistAsset

router = APIRouter()


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    refresh_interval_minutes: int = Field(default=15, ge=1, le=1440)
    signal_threshold: int = Field(default=70, ge=0, le=100)


class WatchlistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    refresh_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    signal_threshold: Optional[int] = Field(default=None, ge=0, le=100)
    is_active: Optional[bool] = None


class WatchlistAssetAdd(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    notes: Optional[str] = None
    target_buy_price: Optional[float] = None
    target_sell_price: Optional[float] = None


class WatchlistAssetUpdate(BaseModel):
    notes: Optional[str] = None
    target_buy_price: Optional[float] = None
    target_sell_price: Optional[float] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_watchlists(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Watchlist).order_by(Watchlist.created_at))
    watchlists = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "name": w.name,
            "description": w.description,
            "refresh_interval_minutes": w.refresh_interval_minutes,
            "signal_threshold": w.signal_threshold,
            "is_active": w.is_active,
            "created_at": w.created_at.isoformat(),
        }
        for w in watchlists
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_watchlist(data: WatchlistCreate, db: AsyncSession = Depends(get_session)):
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name=data.name,
        description=data.description,
        refresh_interval_minutes=data.refresh_interval_minutes,
        signal_threshold=data.signal_threshold,
    )
    db.add(watchlist)
    await db.flush()
    return {"id": str(watchlist.id), "name": watchlist.name}


@router.get("/{watchlist_id}")
async def get_watchlist(watchlist_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    watchlist = result.scalar_one_or_none()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Récupérer les actifs liés
    assets_result = await db.execute(
        select(Asset, WatchlistAsset)
        .join(WatchlistAsset, WatchlistAsset.asset_id == Asset.id)
        .where(WatchlistAsset.watchlist_id == watchlist_id)
        .order_by(Asset.ticker)
    )
    assets = assets_result.all()

    return {
        "id": str(watchlist.id),
        "name": watchlist.name,
        "description": watchlist.description,
        "refresh_interval_minutes": watchlist.refresh_interval_minutes,
        "signal_threshold": watchlist.signal_threshold,
        "is_active": watchlist.is_active,
        "assets": [
            {
                "ticker": a.ticker,
                "name": a.name,
                "asset_type": a.asset_type,
                "is_pea_eligible": a.is_pea_eligible,
                "currency": a.currency,
                "is_active": wa.is_active,
                "notes": wa.notes,
                "target_buy_price": float(wa.target_buy_price) if wa.target_buy_price else None,
                "target_sell_price": float(wa.target_sell_price) if wa.target_sell_price else None,
            }
            for a, wa in assets
        ],
    }


@router.patch("/{watchlist_id}")
async def update_watchlist(
    watchlist_id: UUID, data: WatchlistUpdate, db: AsyncSession = Depends(get_session)
):
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    watchlist = result.scalar_one_or_none()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(watchlist, field, value)
    return {"id": str(watchlist.id), "updated": True}


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(watchlist_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    watchlist = result.scalar_one_or_none()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    await db.delete(watchlist)


@router.post("/{watchlist_id}/assets", status_code=status.HTTP_201_CREATED)
async def add_asset_to_watchlist(
    watchlist_id: UUID, data: WatchlistAssetAdd, db: AsyncSession = Depends(get_session)
):
    """Ajoute un actif à une watchlist (l'actif doit déjà exister dans la table assets)."""
    # Vérifie watchlist
    wl_result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    if not wl_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Vérifie actif
    asset_result = await db.execute(select(Asset).where(Asset.ticker == data.ticker.upper()))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {data.ticker} not found — validate it first via /api/assets/validate")

    # Vérifie doublon
    existing = await db.execute(
        select(WatchlistAsset).where(
            WatchlistAsset.watchlist_id == watchlist_id,
            WatchlistAsset.asset_id == asset.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"{data.ticker} already in this watchlist")

    link = WatchlistAsset(
        watchlist_id=watchlist_id,
        asset_id=asset.id,
        notes=data.notes,
        target_buy_price=data.target_buy_price,
        target_sell_price=data.target_sell_price,
    )
    db.add(link)
    return {"ticker": asset.ticker, "added": True}


@router.delete("/{watchlist_id}/assets/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_asset_from_watchlist(
    watchlist_id: UUID, ticker: str, db: AsyncSession = Depends(get_session)
):
    asset_result = await db.execute(select(Asset).where(Asset.ticker == ticker.upper()))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    await db.execute(
        delete(WatchlistAsset).where(
            WatchlistAsset.watchlist_id == watchlist_id,
            WatchlistAsset.asset_id == asset.id,
        )
    )


@router.patch("/{watchlist_id}/assets/{ticker}")
async def update_watchlist_asset(
    watchlist_id: UUID, ticker: str, data: WatchlistAssetUpdate, db: AsyncSession = Depends(get_session)
):
    asset_result = await db.execute(select(Asset).where(Asset.ticker == ticker.upper()))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    wa_result = await db.execute(
        select(WatchlistAsset).where(
            WatchlistAsset.watchlist_id == watchlist_id,
            WatchlistAsset.asset_id == asset.id,
        )
    )
    wa = wa_result.scalar_one_or_none()
    if not wa:
        raise HTTPException(status_code=404, detail="Asset not in this watchlist")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(wa, field, value)
    return {"ticker": ticker, "updated": True}
