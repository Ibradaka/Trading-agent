from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, DECIMAL, ARRAY, UniqueConstraint, Index,
    func, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ, TIME
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    refresh_interval_minutes = Column(Integer, default=15)
    signal_threshold = Column(Integer, default=70)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    assets = relationship("WatchlistAsset", back_populates="watchlist", cascade="all, delete-orphan")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200))
    asset_type = Column(String(50))   # equity, commodity, index, crypto, forex
    exchange = Column(String(50))
    exchange_suffix = Column(String(10))  # .PA, .DE, .AS, etc.
    currency = Column(String(10))
    sector = Column(String(100))
    country = Column(String(50))
    isin = Column(String(12))
    is_pea_eligible = Column(Boolean, default=False)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    watchlists = relationship("WatchlistAsset", back_populates="asset")
    signals = relationship("Signal", back_populates="asset", cascade="all, delete-orphan")


class WatchlistAsset(Base):
    __tablename__ = "watchlist_assets"

    watchlist_id = Column(UUID(as_uuid=True), ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    target_buy_price = Column(DECIMAL(12, 4))
    target_sell_price = Column(DECIMAL(12, 4))
    added_at = Column(TIMESTAMPTZ, server_default=func.now())

    watchlist = relationship("Watchlist", back_populates="assets")
    asset = relationship("Asset", back_populates="watchlists")


class OHLCData(Base):
    """TimescaleDB hypertable — partitionnée par timestamp."""
    __tablename__ = "ohlc_data"

    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    timestamp = Column(TIMESTAMPTZ, primary_key=True)
    timeframe = Column(String(10), primary_key=True)  # 1d, 4h, 1h, 15m
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    adj_close = Column(Float)

    __table_args__ = (
        Index("ix_ohlc_asset_timestamp", "asset_id", "timestamp"),
    )


class TechnicalIndicators(Base):
    __tablename__ = "technical_indicators"

    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    timestamp = Column(TIMESTAMPTZ, primary_key=True)
    timeframe = Column(String(10), primary_key=True)

    # Trend
    ema20 = Column(Float)
    ema50 = Column(Float)
    ema200 = Column(Float)
    sma20 = Column(Float)
    sma50 = Column(Float)
    sma200 = Column(Float)

    # Momentum
    rsi = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    stoch_k = Column(Float)
    stoch_d = Column(Float)
    williams_r = Column(Float)

    # Volatility
    bb_upper = Column(Float)
    bb_middle = Column(Float)
    bb_lower = Column(Float)
    atr = Column(Float)

    # Volume
    obv = Column(Float)
    adx = Column(Float)


class DetectedPattern(Base):
    __tablename__ = "detected_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(TIMESTAMPTZ, nullable=False)
    pattern_name = Column(String(100), nullable=False)
    direction = Column(String(10))  # bullish, bearish, neutral
    strength = Column(Float)        # 0.0 – 1.0
    description = Column(Text)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())


class Signal(Base):
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(TIMESTAMPTZ, nullable=False)

    signal_type = Column(String(10), nullable=False)   # BUY, SELL, HOLD
    strength = Column(String(10))                       # strong, weak

    composite_score = Column(Float)
    technical_score = Column(Float)
    pattern_score = Column(Float)
    sentiment_score = Column(Float)
    macro_score = Column(Float)
    momentum_score = Column(Float)
    confidence = Column(Float)

    reasoning = Column(Text)
    risks = Column(JSONB)
    invalidation_conditions = Column(Text)
    horizon = Column(String(50))

    llm_raw_output = Column(JSONB)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    asset = relationship("Asset", back_populates="signals")
    outcome = relationship("SignalOutcome", back_populates="signal", uselist=False)


class SentimentCache(Base):
    __tablename__ = "sentiment_cache"

    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    timestamp = Column(TIMESTAMPTZ, primary_key=True)
    sentiment_score = Column(Float)
    key_themes = Column(JSONB)
    sources = Column(JSONB)
    expires_at = Column(TIMESTAMPTZ, nullable=False)


class MacroContext(Base):
    __tablename__ = "macro_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(TIMESTAMPTZ, nullable=False)
    indicator_name = Column(String(100), nullable=False)
    value = Column(Float)
    unit = Column(String(50))
    description = Column(Text)
    source = Column(String(50))
    expires_at = Column(TIMESTAMPTZ, nullable=False)


class SignalOutcome(Base):
    """Track accuracy des signaux après N jours."""
    __tablename__ = "signal_outcomes"

    signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True)
    outcome_checked_at = Column(TIMESTAMPTZ, primary_key=True)
    price_at_signal = Column(Float)
    price_at_check = Column(Float)
    actual_return_pct = Column(Float)
    was_correct = Column(Boolean)
    days_elapsed = Column(Integer)
    notes = Column(Text)

    signal = relationship("Signal", back_populates="outcome")


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    min_score = Column(Integer, default=75)
    signal_types = Column(ARRAY(String), default=["BUY", "SELL"])
    notify_telegram = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)
    quiet_hours_start = Column(TIME, default="20:00")
    quiet_hours_end = Column(TIME, default="08:00")
    cooldown_hours = Column(Integer, default=4)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
