from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen

import pandas as pd
import yfinance as yf

JPX_LISTING_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
JPX_LISTING_DATA_URL = (
    "https://www.jpx.co.jp/markets/statistics-equities/misc/"
    "tvdivq0000001vg2-att/data_j.xls"
)
TARGET_MARKET_PREFIXES = ("プライム", "スタンダード", "グロース")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "JPX のプライム/スタンダード/グロース市場の内国株式を全件取得し、"
            "過去 6 か月の最高終値との差分を JSON に保存します。"
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="JSON を出力するディレクトリ。デフォルトはカレントディレクトリ。",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="yfinance に投げる 1 回あたりの銘柄数。デフォルトは 100。",
    )
    parser.add_argument(
        "--listing-url",
        default=JPX_LISTING_DATA_URL,
        help=(
            "JPX の上場銘柄一覧 URL。通常は既定値のままで問題ありません。"
        ),
    )
    args = parser.parse_args()
    if args.chunk_size < 1:
        parser.error("--chunk-size には 1 以上の整数を指定してください。")
    return args


def normalize_code(value: Any) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return text


def is_target_market(value: Any) -> bool:
    category = str(value).strip()
    normalized = category.replace("(", "（").replace(")", "）")
    return (
        "内国株式" in normalized
        and normalized.startswith(TARGET_MARKET_PREFIXES)
    )


def discover_listing_url() -> str:
    with urlopen(JPX_LISTING_PAGE_URL, timeout=30) as response:
        html = response.read().decode("utf-8", errors="ignore")

    patterns = (
        r'href="([^"]*data_j\.(?:xls|xlsx))"',
        r'href="([^"]*\.(?:xls|xlsx))"',
    )
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return urljoin(JPX_LISTING_PAGE_URL, match.group(1))

    raise RuntimeError("JPX の上場銘柄一覧ファイル URL を検出できませんでした。")


def read_listing_dataframe(url: str) -> pd.DataFrame:
    clean_url = url.split("?", 1)[0]
    suffix = Path(clean_url).suffix.lower()
    engine = None
    if suffix == ".xls":
        engine = "xlrd"
    elif suffix == ".xlsx":
        engine = "openpyxl"

    return pd.read_excel(url, dtype={"コード": str}, engine=engine)


def load_listed_issues(listing_url: str) -> tuple[pd.DataFrame, str]:
    candidates = [listing_url]
    if listing_url == JPX_LISTING_DATA_URL:
        try:
            discovered_url = discover_listing_url()
        except Exception:
            discovered_url = None
        if discovered_url and discovered_url not in candidates:
            candidates.append(discovered_url)

    errors: list[str] = []
    for candidate in candidates:
        try:
            df = read_listing_dataframe(candidate)
            return df, candidate
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    joined = "\n".join(errors)
    raise RuntimeError(f"JPX の上場銘柄一覧を読み込めませんでした。\n{joined}")


def build_issue_records(listed_issues: pd.DataFrame) -> list[dict[str, str]]:
    required_columns = {"コード", "銘柄名", "市場・商品区分"}
    missing_columns = required_columns.difference(listed_issues.columns)
    if missing_columns:
        joined = ", ".join(sorted(missing_columns))
        raise RuntimeError(f"JPX データの列が不足しています: {joined}")

    filtered = listed_issues.loc[
        listed_issues["市場・商品区分"].map(is_target_market),
        ["コード", "銘柄名", "市場・商品区分"],
    ].copy()
    filtered["コード"] = filtered["コード"].map(normalize_code)
    filtered["銘柄名"] = filtered["銘柄名"].astype(str).str.strip()
    filtered["市場・商品区分"] = filtered["市場・商品区分"].astype(str).str.strip()
    filtered = filtered[filtered["コード"] != ""]
    filtered["ticker"] = filtered["コード"] + ".T"
    filtered = filtered.drop_duplicates(subset=["ticker"]).sort_values(
        ["市場・商品区分", "コード"]
    )

    return [
        {
            "code": row["コード"],
            "name": row["銘柄名"],
            "market": row["市場・商品区分"],
            "ticker": row["ticker"],
        }
        for _, row in filtered.iterrows()
    ]


def chunk_records(
    records: list[dict[str, str]],
    chunk_size: int,
) -> list[list[dict[str, str]]]:
    return [
        records[index : index + chunk_size]
        for index in range(0, len(records), chunk_size)
    ]


def download_history(tickers: list[str]) -> pd.DataFrame:
    target = tickers[0] if len(tickers) == 1 else tickers
    return yf.download(
        tickers=target,
        period="6mo",
        interval="1d",
        progress=False,
        group_by="ticker",
        threads=True,
        auto_adjust=False,
    )


def extract_close_prices(history: pd.DataFrame, ticker: str) -> pd.Series:
    if history.empty:
        return pd.Series(dtype="float64")

    if isinstance(history.columns, pd.MultiIndex):
        level0 = set(history.columns.get_level_values(0))
        level1 = set(history.columns.get_level_values(1))
        if ticker in level0 and "Close" in level1:
            return history[ticker]["Close"].dropna()
        if "Close" in level0 and ticker in level1:
            return history["Close"][ticker].dropna()
        return pd.Series(dtype="float64")

    if "Close" not in history.columns:
        return pd.Series(dtype="float64")
    return history["Close"].dropna()


def build_price_summary(record: dict[str, str], close_prices: pd.Series) -> dict[str, Any]:
    current_price = float(close_prices.iloc[-1])
    highest_price = float(close_prices.max())
    highest_index = close_prices.idxmax()

    if hasattr(highest_index, "date"):
        highest_date = highest_index.date().isoformat()
    else:
        highest_date = str(highest_index)

    diff_percent = None
    if highest_price != 0:
        diff_percent = round(
            ((current_price - highest_price) / highest_price) * 100,
            4,
        )

    return {
        "code": record["code"],
        "ticker": record["ticker"],
        "name": record["name"],
        "market": record["market"],
        "current_close": round(current_price, 4),
        "highest_close_6mo": round(highest_price, 4),
        "highest_close_date": highest_date,
        "diff_percent_from_highest": diff_percent,
    }


def collect_market_data(
    records: list[dict[str, str]],
    chunk_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    chunks = chunk_records(records, chunk_size)

    for index, chunk in enumerate(chunks, start=1):
        tickers = [record["ticker"] for record in chunk]
        print(
            f"[{index}/{len(chunks)}] "
            f"{len(tickers)} 銘柄のヒストリカルデータを取得しています..."
        )

        try:
            history = download_history(tickers)
        except Exception as exc:
            for record in chunk:
                failures.append(
                    {
                        "code": record["code"],
                        "ticker": record["ticker"],
                        "reason": f"download failed: {exc}",
                    }
                )
            continue

        for record in chunk:
            try:
                close_prices = extract_close_prices(history, record["ticker"])
                if close_prices.empty:
                    failures.append(
                        {
                            "code": record["code"],
                            "ticker": record["ticker"],
                            "reason": "close price not found",
                        }
                    )
                    continue
                results.append(build_price_summary(record, close_prices))
            except Exception as exc:
                failures.append(
                    {
                        "code": record["code"],
                        "ticker": record["ticker"],
                        "reason": f"processing failed: {exc}",
                    }
                )

    return results, failures


def build_output_payload(
    listing_source_url: str,
    records: list[dict[str, str]],
    results: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "generated_at": generated_at,
        "source": {
            "listing_url": listing_source_url,
            "markets": list(TARGET_MARKET_PREFIXES),
        },
        "summary": {
            "requested": len(records),
            "succeeded": len(results),
            "failed": len(failures),
        },
        "results": results,
        "failures": failures,
    }


def write_output_json(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{timestamp}.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    args = parse_args()

    listed_issues, listing_source_url = load_listed_issues(args.listing_url)
    issue_records = build_issue_records(listed_issues)
    print(f"対象銘柄数: {len(issue_records)}")

    results, failures = collect_market_data(
        records=issue_records,
        chunk_size=args.chunk_size,
    )
    results.sort(key=lambda item: item["code"])

    payload = build_output_payload(
        listing_source_url=listing_source_url,
        records=issue_records,
        results=results,
        failures=failures,
    )
    output_path = write_output_json(payload, args.output_dir)

    print(f"JSON を出力しました: {output_path}")
    print(
        "取得結果 "
        f"成功: {len(results)} 件 / "
        f"失敗: {len(failures)} 件"
    )


if __name__ == "__main__":
    main()
