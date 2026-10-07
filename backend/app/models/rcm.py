"""RCM data model (PostgreSQL-compatible; portable to SQLite for local development).

All patient data is synthetic: patients carry only an opaque ID, birth year, sex and state.
No names, dates of birth, addresses, member IDs or other direct identifiers are stored.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def Money():  # noqa: N802 - column type factory
    return Numeric(12, 2, asdecimal=False)


class ClaimStatus:
    PENDING = "pending"  # submitted/accepted, awaiting adjudication
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    DENIED = "denied"
    REJECTED = "rejected"  # failed front-end edits, not yet corrected
    APPEALED = "appealed"  # denied and under appeal

    ALL = (PENDING, PAID, PARTIALLY_PAID, DENIED, REJECTED, APPEALED)
    ADJUDICATED = (PAID, PARTIALLY_PAID, DENIED, APPEALED)


class Payer(Base):
    __tablename__ = "payers"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    payer_type: Mapped[str] = mapped_column(String(32))  # medicare | medicaid | medicare_advantage | commercial
    timely_filing_days: Mapped[int] = mapped_column(Integer)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    claims: Mapped[list[Claim]] = relationship(back_populates="payer")


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    specialty: Mapped[str] = mapped_column(String(64))
    provider_type: Mapped[str] = mapped_column(String(32))  # professional | facility
    state: Mapped[str] = mapped_column(String(2))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    claims: Mapped[list[Claim]] = relationship(back_populates="provider")


class PatientSynthetic(Base):
    __tablename__ = "patients_synthetic"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    birth_year: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(1))
    state: Mapped[str] = mapped_column(String(2))
    primary_payer_id: Mapped[str] = mapped_column(ForeignKey("payers.id"))


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients_synthetic.id"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True)
    payer_id: Mapped[str] = mapped_column(ForeignKey("payers.id"), index=True)
    claim_type: Mapped[str] = mapped_column(String(16))  # professional | institutional

    service_date: Mapped[date] = mapped_column(Date)
    claim_date: Mapped[date] = mapped_column(Date, index=True)  # first submission date
    adjudication_date: Mapped[date | None] = mapped_column(Date)
    closed_date: Mapped[date | None] = mapped_column(Date)  # balance reached zero

    # Procedure / diagnosis
    cpt_code: Mapped[str] = mapped_column(String(8))
    cpt_description: Mapped[str] = mapped_column(String(160))
    modifier: Mapped[str | None] = mapped_column(String(4))
    units: Mapped[int] = mapped_column(Integer, default=1)
    icd10_code: Mapped[str] = mapped_column(String(10))
    icd10_description: Mapped[str] = mapped_column(String(160))
    place_of_service: Mapped[str] = mapped_column(String(2))
    authorization_number: Mapped[str | None] = mapped_column(String(32))
    requires_authorization: Mapped[bool] = mapped_column(Boolean, default=False)

    # Financials
    billed_amount: Mapped[float] = mapped_column(Money())
    allowed_amount: Mapped[float] = mapped_column(Money(), default=0)
    paid_amount: Mapped[float] = mapped_column(Money(), default=0)  # payer payments
    patient_responsibility: Mapped[float] = mapped_column(Money(), default=0)
    patient_paid_amount: Mapped[float] = mapped_column(Money(), default=0)
    contractual_adjustment: Mapped[float] = mapped_column(Money(), default=0)
    writeoff_amount: Mapped[float] = mapped_column(Money(), default=0)
    balance: Mapped[float] = mapped_column(Money(), default=0)  # outstanding AR

    # Status / quality flags
    status: Mapped[str] = mapped_column(String(16), index=True)
    denial_reason_code: Mapped[str | None] = mapped_column(String(8))  # CARC
    denial_reason: Mapped[str | None] = mapped_column(String(200))
    denial_category: Mapped[str | None] = mapped_column(String(32))
    rejection_reason: Mapped[str | None] = mapped_column(String(200))
    submission_count: Mapped[int] = mapped_column(Integer, default=1)
    was_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    was_denied: Mapped[bool] = mapped_column(Boolean, default=False)
    first_pass_paid: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    payer: Mapped[Payer] = relationship(back_populates="claims")
    provider: Mapped[Provider] = relationship(back_populates="claims")
    payments: Mapped[list[Payment]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    denials: Mapped[list[Denial]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    history: Mapped[list[ClaimStatusHistory]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ClaimStatusHistory.status_date"
    )

    __table_args__ = (
        Index("ix_claims_payer_date", "payer_id", "claim_date"),
        Index("ix_claims_provider_date", "provider_id", "claim_date"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    source: Mapped[str] = mapped_column(String(16))  # payer | patient
    amount: Mapped[float] = mapped_column(Money())
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    method: Mapped[str] = mapped_column(String(16))  # EFT | check | card
    trace_number: Mapped[str | None] = mapped_column(String(32))  # ERA/EFT reassociation trace (TRN02)

    claim: Mapped[Claim] = relationship(back_populates="payments")


class Denial(Base):
    __tablename__ = "denials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    carc_code: Mapped[str] = mapped_column(String(8), index=True)
    group_code: Mapped[str] = mapped_column(String(2))  # CO | PR | OA | PI
    rarc_code: Mapped[str | None] = mapped_column(String(8))
    description: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), index=True)
    denied_amount: Mapped[float] = mapped_column(Money())
    denial_date: Mapped[date] = mapped_column(Date, index=True)
    preventable: Mapped[bool] = mapped_column(Boolean)
    appeal_status: Mapped[str] = mapped_column(String(16))  # not_appealed | pending | overturned | upheld
    appeal_date: Mapped[date | None] = mapped_column(Date)
    resolution_date: Mapped[date | None] = mapped_column(Date)

    claim: Mapped[Claim] = relationship(back_populates="denials")


class ClaimStatusHistory(Base):
    __tablename__ = "claim_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    status_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)

    claim: Mapped[Claim] = relationship(back_populates="history")


class KPISnapshot(Base):
    """Monthly KPI values computed by the analytics engine (for fast trend charts and audit)."""

    __tablename__ = "kpi_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    total_claims: Mapped[int] = mapped_column(Integer)
    total_billed: Mapped[float] = mapped_column(Money())
    total_paid: Mapped[float] = mapped_column(Money())
    denial_rate: Mapped[float | None] = mapped_column(Float)
    clean_claim_rate: Mapped[float | None] = mapped_column(Float)
    first_pass_resolution_rate: Mapped[float | None] = mapped_column(Float)
    net_collection_rate: Mapped[float | None] = mapped_column(Float)
    days_in_ar: Mapped[float | None] = mapped_column(Float)
    outstanding_ar: Mapped[float] = mapped_column(Money())
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("period", name="uq_kpi_snapshots_period"),)


class DatasetMetadata(Base):
    """Key/value facts about the loaded dataset (e.g. its as-of date and generator seed)."""

    __tablename__ = "dataset_metadata"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
