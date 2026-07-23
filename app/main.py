import logging
import pandas as pd
import yfinance as yf

from fastapi import FastAPI, HTTPException, Query
from datetime import datetime, timezone
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://green-tree-0da954a10.3.azurestaticapps.net",
    # agrega otros orígenes si tu frontend está en otra URL (por ejemplo, Vercel o Netlify)
]

app = FastAPI(
    title="GitHub CSV Folder Info API",
    description="API que devuelve información de la carpeta 'dataFolder' en GitHub y permite descargar archivos",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # permitir todos los métodos
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

OUTPUT_FILE = Path("stock_prices.csv")

TICKERS = {
    "Microsoft": "MSFT",
    "Apple": "AAPL",
    "Amazon": "AMZN",
    "NVIDIA": "NVDA",
}

def get_stock_prices(period: str = "4mo") -> list[dict]:
    """
    Descarga precios diarios de cierre desde Yahoo Finance
    y devuelve una lista de diccionarios.
    """

    tickers_list = list(TICKERS.values())

    data = yf.download(
        tickers=tickers_list,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    if data.empty:
        raise ValueError("Yahoo Finance no devolvió información.")

    rows = []

    for company, ticker in TICKERS.items():

        # Cuando se descargan varios tickers, yfinance normalmente
        # devuelve columnas multinivel.
        if not isinstance(data.columns, pd.MultiIndex):
            logger.warning("La respuesta no contiene columnas multinivel.")
            continue

        available_tickers = data.columns.get_level_values(0)

        if ticker not in available_tickers:
            logger.warning("No se encontraron datos para %s", ticker)
            continue

        ticker_df = data[ticker].copy()

        if "Close" not in ticker_df.columns:
            logger.warning(
                "No se encontró la columna Close para %s",
                ticker,
            )
            continue

        ticker_df = ticker_df.reset_index()

        for _, row in ticker_df.iterrows():
            close_price = row.get("Close")
            date_value = row.get("Date")

            if pd.isna(close_price) or pd.isna(date_value):
                continue

            rows.append(
                {
                    "date": date_value.strftime("%Y-%m-%d"),
                    "company": company,
                    "ticker": ticker,
                    "close": round(float(close_price), 4),
                }
            )

    if not rows:
        raise ValueError(
            "No fue posible procesar precios para los tickers solicitados."
        )

    return rows

@app.get("/")
def read_root():
    return {"Message":"API funcionando correctamente"}

@app.get("/stock-prices")
def download_stock_prices(
    period: str = Query(
        default="4mo",
        description="Periodo solicitado a Yahoo Finance, por ejemplo: 5d, 1mo, 4mo, 1y o 5y.",
    ),
    save_csv: bool = Query(
        default=False,
        description="Indica si también debe guardarse el resultado en un CSV.",
    ),
) -> dict:
    """
    Descarga precios de cierre y los devuelve como JSON.
    """

    try:
        prices = get_stock_prices(period=period)

        response = {
            "status": "success",
            "period": period,
            "rows": len(prices),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tickers": TICKERS,
            "data": prices,
        }

        if save_csv:
            final_df = pd.DataFrame(prices)
            final_df.to_csv(OUTPUT_FILE, index=False)

            response["file_saved"] = True
            response["file"] = str(OUTPUT_FILE)
        else:
            response["file_saved"] = False

        return response

    except ValueError as error:
        logger.warning("No se pudieron obtener precios: %s", error)

        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception("Error descargando precios bursátiles")

        raise HTTPException(
            status_code=500,
            detail="Ocurrió un error al descargar los precios bursátiles.",
        ) from error