# shikiho-down

JPX の上場銘柄一覧と `yfinance` を使って、東証のプライム・スタンダード・グロース市場に属する内国株式の「過去 6 か月の最高終値」と「直近終値」の差分を JSON にまとめるための小さな Python ツールです。

あわせて、集計済み JSON から「6 か月高値から 40% 以上下落している銘柄」だけを抽出する補助スクリプトも入っています。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `nyan.py` | JPX の上場銘柄一覧を取得し、対象銘柄の過去 6 か月の終値データを `yfinance` から取得して集計 JSON を出力します。 |
| `output.py` | `nyan.py` の出力 JSON から、`diff_percent_from_highest <= -40` の銘柄だけを抜き出して別 JSON に保存します。 |
| `requirements.txt` | 実行に必要な Python パッケージ一覧です。 |
| `input.json` | `nyan.py` の出力例として置かれている全件データです。 |
| `output.json` | `output.py` による絞り込み結果の例です。 |

## 動作環境

- Python 3.9 以上を想定
- 確認環境: Python 3.10.13
- インターネット接続が必要
  - JPX の上場銘柄一覧
  - Yahoo Finance (`yfinance`)

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方

### 1. 全銘柄の集計 JSON を作る

```bash
python nyan.py --output-dir ./data
```

主なオプション:

- `--output-dir`: 出力先ディレクトリ。省略時はカレントディレクトリ。
- `--chunk-size`: `yfinance` にまとめて投げる銘柄数。省略時は `100`。
- `--listing-url`: JPX の上場銘柄一覧 URL。通常は省略で問題ありません。

出力ファイル名は実行時刻ベースで、`YYYYMMDD_HHMMSS.json` 形式になります。

```text
data/20260510_085243.json
```

### 2. 40% 以上下落している銘柄だけを抽出する

```bash
python output.py ./data/20260510_085243.json ./screened.json
```

引数を省略した場合は、入力に `input.json`、出力に `output.json` を使います。

```bash
python output.py
```

## `nyan.py` の出力内容

出力 JSON は次のような構造です。

```json
{
  "generated_at": "2026-05-10T08:52:43+09:00",
  "source": {
    "listing_url": "https://www.jpx.co.jp/...",
    "markets": ["プライム", "スタンダード", "グロース"]
  },
  "summary": {
    "requested": 3747,
    "succeeded": 3746,
    "failed": 1
  },
  "results": [
    {
      "code": "1301",
      "ticker": "1301.T",
      "name": "極洋",
      "market": "プライム（内国株式）",
      "current_close": 4485.0,
      "highest_close_6mo": 5440.0,
      "highest_close_date": "2026-02-27",
      "diff_percent_from_highest": -17.5551
    }
  ],
  "failures": [
    {
      "code": "9678",
      "ticker": "9678.T",
      "reason": "close price not found"
    }
  ]
}
```

主なキーの意味:

- `summary.requested`: 対象として処理しようとした銘柄数
- `summary.succeeded`: 正常に価格取得できた銘柄数
- `summary.failed`: 価格取得や加工に失敗した銘柄数
- `results`: 銘柄ごとの集計結果
- `failures`: 取得できなかった銘柄と失敗理由

`diff_percent_from_highest` は以下で計算されます。

```text
((直近終値 - 過去6か月の最高終値) / 過去6か月の最高終値) * 100
```

## `output.py` の出力内容

`output.py` は、入力 JSON から次の条件に一致する銘柄だけを抽出します。

- `diff_percent_from_highest <= -40`

出力は `code`、`name`、`diff_percent_from_highest` の 3 項目だけを持つ配列で、下落率が大きい順に並びます。

## 注意点

- `nyan.py` は JPX の既定 URL で取得できない場合、一覧ページを見て `data_j.xls` / `data_j.xlsx` を自動検出する作りです。
- 一部の銘柄は Yahoo Finance 側で価格が見つからず、`failures` に入ることがあります。
- `output.py` の抽出条件 `-40%` はコード内に固定されています。閾値を変えたい場合は `output.py` を修正してください。
