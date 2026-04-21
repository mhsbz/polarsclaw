"""Memory subsystem configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class PromotionWeights(BaseModel):
    """Weights used by the dreaming subsystem to score memory promotion."""

    frequency: float = Field(default=0.24, ge=0.0, le=1.0)
    relevance: float = Field(default=0.30, ge=0.0, le=1.0)
    diversity: float = Field(default=0.15, ge=0.0, le=1.0)
    recency: float = Field(default=0.15, ge=0.0, le=1.0)
    consolidation: float = Field(default=0.10, ge=0.0, le=1.0)
    conceptual: float = Field(default=0.06, ge=0.0, le=1.0)


class DreamingSchedule(BaseModel):
    """Cron schedules for the three dreaming tiers."""

    light: str = Field(default="0 * * * *", description="Light dreaming — hourly")
    rem: str = Field(default="0 2 * * *", description="REM dreaming — daily at 2 AM")
    deep: str = Field(default="0 3 * * 0", description="Deep dreaming — weekly Sunday 3 AM")


class MemoryConfig(BaseModel):
    """Full configuration for the PolarsClaw memory system."""

    enabled: bool = True
    workspace: Path = Field(default=Path("."), description="Directory for memory artefacts")

    # Embedding settings
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_provider: str = Field(default="local", description="'local' or 'openai'")
    embedding_dim: int = Field(default=384)

    # Chunking
    chunk_size: int = Field(default=512, description="Target chunk size in tokens")
    chunk_overlap: int = Field(default=64, description="Overlap between consecutive chunks in tokens")

    # Retrieval scoring
    vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    text_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    temporal_decay_days: int = Field(default=30)
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0, description="MMR diversity-relevance trade-off")

    # Promotion weights
    promotion_weights: PromotionWeights = Field(default_factory=PromotionWeights)

    # Dreaming schedules
    dreaming_schedule: DreamingSchedule = Field(default_factory=DreamingSchedule)

    # Flush / watch
    flush_token_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    watch_interval: float = Field(default=5.0, gt=0.0, description="File-watch polling interval in seconds")
