import yfinance as yf
from datetime import datetime, timedelta


def compare_with_highest_price(ticker_symbol: str):
    """
    過去半年の最高値と現在価格を比較し、
    差分率（%）を表示する
    """

    ticker = yf.Ticker(ticker_symbol)

    end_date = datetime.today()
    start_date = end_date - timedelta(days=180)

    # 過去半年分の履歴取得
    df = ticker.history(start=start_date, end=end_date)

    if df.empty:
        print(f"データ取得失敗: {ticker_symbol}")
        return

    close_prices = df["Close"].dropna()

    # 現在価格（最新営業日）
    current_price = close_prices.iloc[-1]

    # 半年間の最高終値
    highest_price = close_prices.max()

    # 最高値の日付
    highest_date = close_prices.idxmax().date()

    # 差分率（最高値基準）
    diff_percent = (
        (current_price - highest_price)
        / highest_price
    ) * 100

    print(f"銘柄: {ticker_symbol}")
    print(
        f"半年最高値 ({highest_date}): "
        f"{highest_price:.2f}円"
    )
    print(f"現在価格: {current_price:.2f}円")
    print(f"最高値との差分: {diff_percent:+.2f}%")


if __name__ == "__main__":
    # 例: トヨタ
    compare_with_highest_price("7203.T")