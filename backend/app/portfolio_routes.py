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


class TransactionBody(BaseModel):
    holding_id: str = Field(min_length=1, max_length=64)
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: Literal["buy", "sell", "dividend"]
    units: float = Field(0, ge=0, le=1e12)
    amount: float = Field(gt=0, le=1e11)


class TxImportBody(BaseModel):
    transactions: list[TransactionBody] = Field(max_length=5000)


def match_holding(name: str, holdings: list) -> Optional[str]:
    """Links a statement line to a holding: same symbol/name, or a near-exact fund name."""
    key = (name or "").strip().lower()
    for h in holdings:
        if key and key in (h["name"].strip().lower(), (h["symbol"] or "").lower(), (h["isin"] or "").lower()):
            return h["id"]
    wanted = portfolio._tokens(name)
    best, score = None, 0.0
    for h in holdings:
        have = portfolio._tokens(h["name"])
        if not wanted or not have or ("direct" in wanted) != ("direct" in have):
            continue
        s = len(wanted & have) / len(wanted | have)
        if s > score:
            best, score = h["id"], s
    return best if score >= 0.85 else None


def _holding_dict(h: Holding) -> dict:
    return {"id": h.id, "kind": h.kind, "name": h.name, "symbol": h.symbol or "", "isin": h.isin or "",
            "units": h.units, "avg_cost": h.avg_cost, "buy_date": h.buy_date, "last_price": h.last_price,
            "price_date": h.price_date, "price_source": h.price_source, "category": h.category or "equity"}


def load_profile(db) -> dict:
    row = db.get(InvestorProfile, 1)
    data = json.loads(row.data) if row and row.data else {}
    return {**ProfileBody().model_dump(), **data, "set": bool(row)}


def _transactions(db) -> dict:
    from app.db.models import PortfolioTransaction
    grouped: dict = {}
    for t in db.query(PortfolioTransaction).order_by(PortfolioTransaction.day).all():
        grouped.setdefault(t.holding_id, []).append({"id": t.id, "day": t.day, "kind": t.kind, "units": t.units, "amount": t.amount})
    return grouped


def _add_xirr(summary: dict, tx: dict) -> None:
    """True yearly return per holding and for the whole portfolio (only where transactions exist)."""
    all_flows = []
    for h in summary["holdings"]:
        rows = tx.get(h["id"], [])
        h["transactions"] = len(rows)
        rate = portfolio.holding_xirr(rows, h["value"]) if rows else None
        h["xirr_pct"] = round(rate * 100, 2) if rate is not None else None
        if rows:
            for t in rows:
                d = portfolio._to_date(t["day"])
                if d:
                    all_flows.append((d, -t["amount"] if t["kind"] == "buy" else t["amount"]))
            from datetime import date as _date
            all_flows.append((_date.today(), h["value"]))
    rate = portfolio.xirr(all_flows)
    summary["xirr_pct"] = round(rate * 100, 2) if rate is not None else None
    summary["xirr_note"] = ("True yearly return of the holdings that have transactions, including SIP timing."
                            if rate is not None else "Add or import your transactions to see the true yearly return.")


def portfolio_snapshot() -> dict:
    """Used by the API and by the chat skill (so the model explains real numbers)."""
    with SessionLocal() as db:
        holdings = [_holding_dict(h) for h in db.query(Holding).all()]
        profile = load_profile(db)
        tx = _transactions(db)
    summary = portfolio.summarize(holdings)
    _add_xirr(summary, tx)
    return {"profile": profile, "summary": summary, "suggestions": portfolio.advise(profile, summary),
            "disclaimer": portfolio.DISCLAIMER}


def record_history(summary: dict, day: Optional[str] = None) -> None:
    """One row per day: the latest refresh of the day wins."""
    from datetime import date as _date
    from app.db.models import PortfolioHistory
    if not summary.get("count"):
        return
    day = day or _date.today().isoformat()
    with SessionLocal() as db:
        row = db.get(PortfolioHistory, day) or PortfolioHistory(day=day, value=0, invested=0)
        row.value, row.invested = summary["value"], summary["invested"]
        db.merge(row); db.commit()


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
            from app.db.models import PortfolioTransaction
            db.query(PortfolioTransaction).filter(PortfolioTransaction.holding_id == holding_id).delete()
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
                from app.db.models import PortfolioTransaction
                db.query(PortfolioTransaction).delete()
                db.query(Holding).delete()
            for h in body.holdings:
                db.add(Holding(id=str(uuid.uuid4()), **h.model_dump()))
            db.commit()
        return portfolio_snapshot()

    @router.get("/transactions/{holding_id}")
    def list_transactions(holding_id: str):
        unlocked()
        with SessionLocal() as db:
            return _transactions(db).get(holding_id, [])

    @router.post("/transactions")
    def add_transaction(body: TransactionBody):
        unlocked()
        from app.db.models import PortfolioTransaction
        with SessionLocal() as db:
            if db.get(Holding, body.holding_id) is None:
                raise HTTPException(404, "Holding not found.")
            db.add(PortfolioTransaction(id=str(uuid.uuid4()), **body.model_dump())); db.commit()
        return portfolio_snapshot()

    @router.post("/transactions/{tx_id}/delete")
    def delete_transaction(tx_id: str, body: PinBody):
        unlocked()
        require_pin(body.pin, "Enter your PIN to delete this transaction.")
        from app.db.models import PortfolioTransaction
        with SessionLocal() as db:
            row = db.get(PortfolioTransaction, tx_id)
            if row is None:
                raise HTTPException(404, "Transaction not found.")
            db.delete(row); db.commit()
        return portfolio_snapshot()

    @router.post("/transactions/import/preview")
    async def preview_transactions(request: Request):
        """Reads a statement CSV and links each line to a holding. Nothing is saved here."""
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
            parsed = portfolio.parse_transactions_csv(text)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        with SessionLocal() as db:
            holdings = [_holding_dict(h) for h in db.query(Holding).all()]
        names = {h["id"]: h["name"] for h in holdings}
        for t in parsed["transactions"]:
            t["holding_id"] = match_holding(t["name"], holdings)
            t["holding_name"] = names.get(t["holding_id"])
        parsed["unmatched"] = sorted({t["name"] for t in parsed["transactions"] if not t["holding_id"]})
        return parsed

    @router.post("/transactions/import")
    def import_transactions(body: TxImportBody):
        unlocked()
        from app.db.models import PortfolioTransaction
        with SessionLocal() as db:
            known = {h.id for h in db.query(Holding).all()}
            existing = {(t.holding_id, t.day, t.kind, round(t.amount, 2)) for t in db.query(PortfolioTransaction).all()}
            added = 0
            for t in body.transactions:
                key = (t.holding_id, t.day, t.kind, round(t.amount, 2))
                if t.holding_id in known and key not in existing:     # importing twice adds nothing twice
                    db.add(PortfolioTransaction(id=str(uuid.uuid4()), **t.model_dump()))
                    existing.add(key); added += 1
            db.commit()
        return {**portfolio_snapshot(), "added": added}

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
        snap = portfolio_snapshot()
        record_history(snap["summary"])
        return {**snap, "updated": len(result["prices"]), "errors": result["errors"]}

    @router.post("/project")
    def projection(body: ProjectBody):
        unlocked()
        try:
            return portfolio.project(body.monthly, body.years, body.lumpsum, body.category)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    return router
