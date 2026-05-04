from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from datetime import datetime
import re

app = FastAPI(title="Investment Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "service": "investment-api"}

@app.get("/price/{symbol}")
def get_price(symbol: str):
    """Single symbol price history. e.g. /price/HDFCBANK.NS"""
    try:
        hist = yf.Ticker(symbol).history(period="7y", interval="1mo", auto_adjust=True)
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        history = {}
        for ts, row in hist.iterrows():
            if row["Close"] and row["Close"] > 0:
                history[ts.strftime("%Y-%m")] = round(float(row["Close"]), 2)
        current = round(float(hist["Close"].dropna().iloc[-1]), 2)
        return {"symbol": symbol, "current": current, "history": history,
                "updated": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/prices")
async def get_prices(request: Request):
    """Bulk price fetch. Body: {"symbols": ["HDFCBANK.NS", ...]}"""
    body = await request.json()
    symbols = body.get("symbols", [])
    result, errors = {}, []
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period="7y", interval="1mo", auto_adjust=True)
            if hist.empty:
                errors.append(sym)
                continue
            history = {}
            for ts, row in hist.iterrows():
                if row["Close"] and row["Close"] > 0:
                    history[ts.strftime("%Y-%m")] = round(float(row["Close"]), 2)
            result[sym] = {
                "current": round(float(hist["Close"].dropna().iloc[-1]), 2),
                "history": history
            }
        except Exception:
            errors.append(sym)
    return {"prices": result, "errors": errors, "updated": datetime.utcnow().isoformat()}

@app.get("/lookup/isin/{isin}")
def lookup_isin(isin: str):
    """Single ISIN to Yahoo symbol. e.g. /lookup/isin/INE001A01036"""
    if not re.match(r'^IN[A-Z0-9]{10}$', isin):
        raise HTTPException(status_code=400, detail="Invalid ISIN")
    try:
        search = yf.Search(isin, max_results=10)
        quotes = getattr(search, 'quotes', [])
        ns = next((q for q in quotes if q.get("symbol", "").endswith(".NS")), None)
        bo = next((q for q in quotes if q.get("symbol", "").endswith(".BO")), None)
        best = ns or bo or (quotes[0] if quotes else None)
        if not best:
            raise HTTPException(status_code=404, detail=f"No symbol for {isin}")
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

@app.post("/lookup/isins")
async def lookup_isins(request: Request):
    """Bulk ISIN lookup. Body: {"isins": ["INE001A01036", ...]}"""
    body = await request.json()
    isins = body.get("isins", [])
    result = {}
    for isin in isins:
        if not re.match(r'^IN[A-Z0-9]{10}$', isin):
            result[isin] = {"error": "invalid"}
            continue
        try:
            search = yf.Search(isin, max_results=10)
            quotes = getattr(search, 'quotes', [])
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
