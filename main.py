from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yfinance as yf
from datetime import datetime
import re

app = FastAPI(title="Investment Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your Render domain in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Health check ──────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "service": "investment-api"}

# ── Price history for a symbol ────────────────────────────────
@app.get("/price/{symbol}")
def get_price(symbol: str):
    """
    Returns monthly price history + current price for a Yahoo Finance symbol.
    e.g. /price/HDFCBANK.NS  or  /price/RELIANCE.NS
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="7y", interval="1mo", auto_adjust=True)
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")

        history = {}
        for ts, row in hist.iterrows():
            month = ts.strftime("%Y-%m")
            if row["Close"] and row["Close"] > 0:
                history[month] = round(float(row["Close"]), 2)

        current = round(float(hist["Close"].dropna().iloc[-1]), 2)
        return {
            "symbol": symbol,
            "current": current,
            "history": history,
            "updated": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Bulk price fetch ──────────────────────────────────────────
class BulkRequest(BaseModel):
    symbols: list[str]

@app.post("/prices")
def get_prices(req: BulkRequest):
    """
    Bulk fetch prices for multiple symbols in one call.
    Returns {symbol: {current, history}} dict.
    """
    result = {}
    errors = []
    for sym in req.symbols:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="7y", interval="1mo", auto_adjust=True)
            if hist.empty:
                errors.append(sym)
                continue
            history = {}
            for ts, row in hist.iterrows():
                month = ts.strftime("%Y-%m")
                if row["Close"] and row["Close"] > 0:
                    history[month] = round(float(row["Close"]), 2)
            current = round(float(hist["Close"].dropna().iloc[-1]), 2)
            result[sym] = {"current": current, "history": history}
        except Exception as e:
            errors.append(sym)
    return {
        "prices": result,
        "errors": errors,
        "updated": datetime.utcnow().isoformat()
    }

# ── ISIN to symbol lookup ─────────────────────────────────────
@app.get("/lookup/isin/{isin}")
def lookup_isin(isin: str):
    """
    Looks up the NSE/BSE Yahoo Finance symbol for an Indian ISIN.
    e.g. /lookup/isin/INE001A01036  →  HDFCBANK.NS
    """
    if not re.match(r'^IN[A-Z0-9]{10}$', isin):
        raise HTTPException(status_code=400, detail="Invalid ISIN format")
    try:
        # yfinance search by ISIN
        result = yf.Search(isin, max_results=10)
        quotes = result.quotes if hasattr(result, 'quotes') else []
        
        # Prefer .NS (NSE), then .BO (BSE)
        ns = next((q for q in quotes if q.get("symbol", "").endswith(".NS")), None)
        bo = next((q for q in quotes if q.get("symbol", "").endswith(".BO")), None)
        best = ns or bo or (quotes[0] if quotes else None)

        if not best:
            raise HTTPException(status_code=404, detail=f"No symbol found for ISIN {isin}")

        return {
            "isin": isin,
            "yahoo": best.get("symbol", ""),
            "nse": ns["symbol"].replace(".NS", "") if ns else "",
            "bse": bo["symbol"].replace(".BO", "") if bo else "",
            "name": best.get("longname") or best.get("shortname", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Bulk ISIN lookup ──────────────────────────────────────────
class ISINRequest(BaseModel):
    isins: list[str]

@app.post("/lookup/isins")
def lookup_isins(req: ISINRequest):
    """
    Bulk ISIN → symbol lookup. Returns dict keyed by ISIN.
    """
    result = {}
    for isin in req.isins:
        if not re.match(r'^IN[A-Z0-9]{10}$', isin):
            result[isin] = {"error": "invalid"}
            continue
        try:
            search = yf.Search(isin, max_results=10)
            quotes = search.quotes if hasattr(search, 'quotes') else []
            ns = next((q for q in quotes if q.get("symbol", "").endswith(".NS")), None)
            bo = next((q for q in quotes if q.get("symbol", "").endswith(".BO")), None)
            best = ns or bo or (quotes[0] if quotes else None)
            if best:
                result[isin] = {
                    "yahoo": best.get("symbol", ""),
                    "nse": ns["symbol"].replace(".NS", "") if ns else "",
                    "bse": bo["symbol"].replace(".BO", "") if bo else "",
                    "name": best.get("longname") or best.get("shortname", ""),
                }
            else:
                result[isin] = {"error": "not found"}
        except Exception as e:
            result[isin] = {"error": str(e)}
    return {"results": result, "updated": datetime.utcnow().isoformat()}
