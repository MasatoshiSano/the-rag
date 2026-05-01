#!/usr/bin/env bash
# AWS 認証情報を ~/.aws/login/cache/ から読み込み、
# プロジェクトルートの .env を更新するスクリプト。
#
# 使い方:
#   bash scripts/refresh-aws-env.sh
#   docker compose up -d
#
# Cursor の AWS ログインセッションが更新されるたびに実行してください。

set -euo pipefail

CACHE_DIR="$HOME/.aws/login/cache"
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"

# キャッシュファイルを取得（最新の JSON ファイル）
CACHE_FILE=$(ls -t "$CACHE_DIR"/*.json 2>/dev/null | head -1)
if [[ -z "$CACHE_FILE" ]]; then
  echo "[ERROR] 認証キャッシュが見つかりません: $CACHE_DIR"
  exit 1
fi

# 認証情報を抽出
ACCESS_KEY=$(python3 -c "import json; d=json.load(open('$CACHE_FILE')); print(d['accessToken']['accessKeyId'])")
SECRET_KEY=$(python3 -c "import json; d=json.load(open('$CACHE_FILE')); print(d['accessToken']['secretAccessKey'])")
SESSION_TOKEN=$(python3 -c "import json; d=json.load(open('$CACHE_FILE')); print(d['accessToken']['sessionToken'])")
EXPIRES_AT=$(python3 -c "import json; d=json.load(open('$CACHE_FILE')); print(d['accessToken']['expiresAt'])")

echo "[INFO] 認証情報を更新します (有効期限: $EXPIRES_AT)"

# .env を生成または更新
# 既存の .env に AWS 認証情報セクションがあれば上書き、なければ追記
ENV_CONTENT=$(cat "$ENV_FILE" 2>/dev/null | grep -v "^AWS_ACCESS_KEY_ID=" | grep -v "^AWS_SECRET_ACCESS_KEY=" | grep -v "^AWS_SESSION_TOKEN=" | grep -v "^AWS_DEFAULT_REGION=" | grep -v "^# AWS Session" || true)

cat > "$ENV_FILE" <<EOF
# AWS Session (自動生成 - refresh-aws-env.sh で更新。有効期限: $EXPIRES_AT)
AWS_ACCESS_KEY_ID=$ACCESS_KEY
AWS_SECRET_ACCESS_KEY=$SECRET_KEY
AWS_SESSION_TOKEN=$SESSION_TOKEN
AWS_DEFAULT_REGION=ap-northeast-1

$ENV_CONTENT
EOF

echo "[OK] .env を更新しました: $ENV_FILE"
echo "[INFO] 次のコマンドでシステムを起動してください:"
echo "       docker compose up -d"
