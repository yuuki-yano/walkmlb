# WalkMLB — MLBデータで目標歩数を決めるWebアプリ

FastAPI + SQLite のシンプルなWebアプリです。MLB Stats APIから試合と打者成績を取得・保存し、その日のヒット数、エラー数、ホームラン数などから目標歩数を算出します。

## 主要機能
- 指定日のMLB試合をインポート（試合、チーム合計、打者成績）
- 保存データの参照
- 指定日の目標歩数を計算（任意でチーム名でフィルタ）
- 簡易フロントエンド（/ でアクセス）

## エンドポイント
- POST /api/import?date=YYYY-MM-DD
- GET  /api/games?date=YYYY-MM-DD
- GET  /api/steps/goal?date=YYYY-MM-DD[&team=TEAM_NAME]

## ステップ目標のデフォルト計算式
- base 6000 歩
- + 100 × ヒット合計（teamStats.batting.hits）
- + 300 × ホームラン合計（teamStats.batting.homeRuns）
- - 50 × エラー合計（teamStats.fielding.errors）

環境変数で調整可能（.env）
```
WALK_BASE=6000
WALK_PER_HIT=100
WALK_PER_HR=300
WALK_PER_ERROR=50

# 選手ごとのイベントで計算（詳細ページのボタン）
WALK_PER_HIT_PLAYER=-100
WALK_PER_HR_PLAYER=-300
WALK_PER_ERROR_PLAYER=50
```

## ローカル実行（Docker・WSL推奨）
1) Docker Desktop と WSL2 を準備
2) ビルド＆起動（ホットリロード対応）
3) ブラウザで http://localhost:8000/
	- トップページから日付を選び「インポート」→「目標歩数」
