# Setup

ローカル開発環境のセットアップ手順を記載する。本格的な環境変数や AWS / EntraID 設定は `external-setup-guide.md` および `EntraID認証ガイド.md` を参照。

## 前提

- Docker / Docker Compose v2
- 開発時のみ: Node.js 20+ / Python 3.11+

## 起動

```bash
# 環境変数を読み込み（AWS セッション等）
./scripts/refresh-aws-env.sh   # 既存スクリプトがある場合のみ

# サービス全体を起動
docker compose up --build
```

## 起動シーケンスと依存関係

`docker compose up` 実行時のサービス起動順:

```
qdrant (healthy になるまで待機) → backend (init_collections OK) → frontend
```

### Qdrant の起動待機について

`docker-compose.yml` では以下の理由で `backend` が `qdrant` の **healthy 状態**を待ってから起動するように構成している。

- `qdrant` は起動直後（`service_started` 直後）はまだ HTTP / gRPC リクエストを受け付けない瞬間がある
- `backend/app/main.py` の `init_collections()` はその瞬間に走ると失敗し、ログ警告を残してそのまま継続する
- 結果として「初回 `docker compose up` 時にコレクション初期化がスキップされ、最初の検索が空ヒットになる」レースが発生していた

これを避けるため、`qdrant` サービスに以下の healthcheck を設定し、`backend.depends_on.qdrant.condition` を `service_healthy` にしている。

```yaml
healthcheck:
  test: ["CMD-SHELL", "bash -c ':> /dev/tcp/127.0.0.1/6333' || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

`qdrant/qdrant:latest` イメージには `curl` / `wget` が同梱されていないため、bash の `/dev/tcp` 機能で `127.0.0.1:6333` に TCP 接続可能かを判定している。

### 確認方法

`backend` 起動完了後、ログに以下が出力されていれば初期化成功:

```
init_collections OK
```

`docker compose ps` で `qdrant` が `healthy` になってから `backend` が `Up` に遷移していることを確認できる。

```bash
docker compose ps
# NAME       STATUS
# qdrant     Up (healthy)
# backend    Up
# frontend   Up
```

## トラブルシュート

| 症状 | 原因 / 対処 |
|---|---|
| `backend` が起動直後に終了する | `qdrant` が healthy になる前に backend が起動しようとした旧構成の残骸。`docker compose down -v` で再起動 |
| 初回検索が空ヒット | `backend` の `init_collections OK` ログを確認。出ていない場合は `qdrant` の healthcheck 失敗を疑う |
