from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey

from app.database import Base


class User(Base):
    """One retailer account. MVP scope: single shop per user, no team
    accounts yet (spec's "3 viewer accounts" is a fast-follow, not core)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    shop_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SKU(Base):
    """Current-state snapshot per SKU (on-hand stock, reorder point,
    last sale date) - updated on every CSV upload, not accumulated."""
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sku_code = Column(String, nullable=False)
    name = Column(String, default="")
    on_hand = Column(Float, default=0)
    reorder_point = Column(Float, default=0)
    last_sale_date = Column(Date, nullable=True)


class SaleRecord(Base):
    """One row of transactional sales history per SKU per date, parsed
    from an uploaded CSV."""
    __tablename__ = "sale_records"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    upload_id = Column(Integer, ForeignKey("uploads.id"), nullable=False)
    sku_code = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    quantity = Column(Float, default=0)
    revenue = Column(Float, default=0)


class Upload(Base):
    """Audit trail of every CSV a retailer has uploaded, including ones
    that were rejected - so a retailer (or support) can see what
    happened to a specific file, not just the current dashboard state."""
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, default="")
    row_count = Column(Integer, default=0)
    status = Column(String, default="")  # OK | REJECTED | FLAGGED
    message = Column(String, default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
