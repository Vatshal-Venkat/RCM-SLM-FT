"""Schema creation and bulk data loading."""

from __future__ import annotations

import logging

from sqlalchemy import Engine, insert

from app.models.rcm import (
    Base,
    Claim,
    ClaimStatusHistory,
    DatasetMetadata,
    Denial,
    Payer,
    PatientSynthetic,
    Payment,
    Provider,
)

logger = logging.getLogger(__name__)

# Insert order respects foreign keys.
_LOAD_ORDER = [
    ("payers", Payer), ("providers", Provider), ("patients_synthetic", PatientSynthetic), ("claims", Claim),
    ("payments", Payment), ("denials", Denial), ("claim_status_history", ClaimStatusHistory),
    ("dataset_metadata", DatasetMetadata),
]


def create_schema(engine: Engine, reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def load_rows(engine: Engine, data: dict[str, list[dict]], batch_size: int = 2000) -> dict[str, int]:
    counts = {}
    with engine.begin() as conn:
        for table, model in _LOAD_ORDER:
            rows = data.get(table, [])
            for i in range(0, len(rows), batch_size):
                conn.execute(insert(model), rows[i : i + batch_size])
            counts[table] = len(rows)
            logger.info("Loaded %d rows into %s", len(rows), table)
    return counts
