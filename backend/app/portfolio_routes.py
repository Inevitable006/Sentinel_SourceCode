"""Portfolio Advisor API. Read and analyse only: no bank/broker access, no orders."""
import json
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import portfolio
from app.core.vault import vault
from app.db.database import SessionLocal
from app.db.models import Holding, InvestorProfile

MAX_IMPORT_BYTES = 2 * 1024 * 1024


class ProfileBody(BaseModel):
    risk: Literal["conservative", "moderate", "aggressive"] = "moderate"
    horizon_years: float = Field(5, gt=0, le=50)
    monthly_amount: float = Field(0, ge=0, le=10_000_000)
    monthly_expenses: float = Field(0, ge=0, le=10_000_000)
    emergency_fund: float = Field(0, ge=0, le=1_000_000_000)
    goal: str = Field("", max_length=300)


class HoldingBody(BaseModel):
    kind: Literal["mf", "stock", "other"]
    name: str = Field(min_length=1, max_length=200)
    symbol: str = Field("", max_length=40)
    isin: str = Field("", max_length=20)
    units: float = Field(gt=0, le=1e12)
    avg_cost: float = Field(ge=0, le=1e9)
    buy_date: Optional[str] = Field(None, max_length=20)
    category: Literal["equity", "debt", "hybrid", "gold"] = "equity"


class ImportBody(BaseModel):
    holdings: list[HoldingBody] = Field(max_length=500)
    replace: bool = False
    pin: Optional[str] = None


class ProjectBody(BaseModel):
    monthly: float = Field(0, ge=0, le=10_000_000)
    lumpsum: float = Field(0, ge=0, le=1_000_000_000)
    years: float = Field(gt=0, le=50)
    category: Literal["equity", "debt", "hybrid", "gold"] = "equity"


class PinBody(BaseModel):
    pin: Optional[str] = None


def _holding_dict(h: Holding) -> dict:
    return {"id": h.id, "kind": h.kind, "name": h.name, "symbol": h.symbol or "", "isin": h.isin or "",
            "units": h.units, "avg_cost": h.avg_cost, "buy_date": h.buy_date, "last_price": h.last_price,
            "price_date": h.price_date, "price_source": h.price_source, "category": h.category or "equity"}


def load_profile(db) -> dict:
    row = db.get(InvestorProfile, 1)
    data = json.loads(row.data) if row and row.data else {}
    return {**ProfileBody().model_dump(), **data, "set": bool(row)}


def portfolio_snapshot() -> dict:
    """Used by the API and by the chat skill (so the model explains real numbers)."""
    with SessionLocal() as db:
        holdings = [_holding_dict(h) for h in db.query(Holding).all()]
        profile = load_profile(db)
    summary = portfolio.summarize(holdings)
    return {"profile": profile, "summary": summary, "suggestions": portfolio.advise(profile, summary),
            "disclaimer": portfolio.DISCLAIMER}


def create_portfolio_router(verify_session_token, require_pin):
    router = APIRouter(prefix="/api/portfolio", dependencies=[Depends(verify_session_token)])

    def unlocked():
        if not vault.is_unlocked():
            raise HTTPException(423, "Unlock Sentinel first.")

    @router.get("")
    def overview():
        unlocked()
        return portfolio_snapshot()

    @router.post("/profile")
    def set_profile(body: ProfileBody):
        unlocked()
        with SessionLocal() as db:
            row = db.get(InvestorProfile, 1) or InvestorProfile(id=1)
            row.data = body.model_dump_json()
            db.merge(row); db.commit()
        return portfolio_snapshot()

    @router.post("/holdings")
    def add(body: HoldingBody):
        unlocked()
        with SessionLocal() as db:
            db.add(Holding(id=str(uuid.uuid4()), **body.model_dump())); db.commit()
        return portfolio_snapshot()

    @router.post("/holdings/{holding_id}/update")
    def update(holding_id: str, body: HoldingBody):
        unlocked()
        with SessionLocal() as db:
            row = db.get(Holding, holding_id)
            if row is None:
                raise HTTPException(404, "Holding not found.")
            for k, v in body.model_dump().items():
                setattr(row, k, v)
            db.commit()
        return portfolio_snapshot()

    @router.post("/holdings/{holding_id}/delete")
    def delete(holding_id: str, body: PinBody):
        unlocked()
        require_pin(body.pin, "Enter your PIN to delete this holding.")
        with SessionLocal() as db:
            row = db.get(Holding, holding_id)
            if row is None:
                raise HTTPException(404, "Holding not found.")
            db.delete(row); db.commit()
        return portfolio_snapshot()

    @router.post("/import/preview")
    async def preview(request: Request):
        """Reads a CSV export and shows what would be imported. Nothing is saved here."""
        unlocked()
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_IMPORT_BYTES:
                raise HTTPException(413, "File too large (limit 2 MB).")
        try:
            text = bytes(data).decode("utf-8-sig")
        except UnicodeDecodeError:
            text = bytes(data).decode("latin-1")
        try:
            return portfolio.parse_holdings_csv(text)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @router.post("/import")
    def import_holdings(body: ImportBody):
        unlocked()
        if body.replace:
            require_pin(body.pin, "Enter your PIN to replace all holdings.")
        with SessionLocal() as db:
            if body.replace:
                db.query(Holding).delete()
            for h in body.holdings:
                db.add(Holding(id=str(uuid.uuid4()), **h.model_dump()))
            db.commit()
        return portfolio_snapshot()

    @router.post("/refresh-prices")
    async def refresh():
        unlocked()
        with SessionLocal() as db:
            holdings = [_holding_dict(h) for h in db.query(Holding).all()]
        result = await portfolio.fetch_prices(holdings)
        with SessionLocal() as db:
            for hid, p in result["prices"].items():
                row = db.get(Holding, hid)
                if row is not None:
                    row.last_price, row.price_date, row.price_source = p["price"], p["date"], p["source"]
            db.commit()
        return {**portfolio_snapshot(), "updated": len(result["prices"]), "errors": result["errors"]}

    @router.post("/project")
    def projection(body: ProjectBody):
        unlocked()
        try:
            return portfolio.project(body.monthly, body.years, body.lumpsum, body.category)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    return router
