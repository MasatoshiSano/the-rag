# RAG Phantom セットアップガイド

## 初回セットアップ時の Volume 権限設定

バックエンドコンテナは UID 1000 の non-root ユーザー（`appuser`）で実行されます。
`docker-compose.yml` の `backend` サービスには `user: "1000:1000"` が指定されているため、
ホスト側のマウントディレクトリの所有権を合わせる必要があります。

### 方法1: 既存ディレクトリの所有権を変更する

すでに `./backend/data` や `./uploads` が root 所有で作成されている場合:

```bash
sudo chown -R 1000:1000 ./backend/data ./uploads
```

### 方法2: 初回起動前に空ディレクトリを作成しておく

`docker compose up` を初めて実行する前に、ホスト側で空ディレクトリを作っておくと、
作業ユーザーの UID で作成されるためそのまま書き込めます（多くの開発環境では UID=1000）:

```bash
mkdir -p ./backend/data ./uploads
```

UID が 1000 と異なるホストでは、`docker-compose.yml` の `user` 指定を
ホストの UID:GID に合わせて変更するか、上記 `chown` を実行してください。

### 確認

権限が正しく設定されていれば、以下のコマンドでバックエンドが正常に起動します:

```bash
docker compose up -d backend
docker compose logs -f backend
```

`PermissionError: [Errno 13] Permission denied: '/app/data/...'` 等のエラーが出る場合は、
Volume の所有権設定を再確認してください。

## 関連ドキュメント

- `docs/api-guide.md`: API 利用ガイド
- `docs/external-setup-guide.md`: 外部連携（GitHub/Gitea）セットアップ
