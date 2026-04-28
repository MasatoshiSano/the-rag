---
title: "Git BashでDockerコマンドの /app/ パスが壊れる原因と対策 — MSYS_NO_PATHCONV=1で回避する"
emoji: "🐛"
type: "tech"
topics: ["Git Bash", "Docker", "WSL", "Windows", "DevOps"]
published: true
category: "Debugging"
date: "2026-04-28"
description: "Git Bash(MSYS2)が/app/をC:/Program Files/Git/app/に自動変換してDockerコマンドが壊れる問題の原因と、MSYS_NO_PATHCONV=1による回避方法を解説"
---

## やりたかったこと

WSL Docker内のコンテナに対して、`docker exec` でファイルパッチを当てたい。

```bash
wsl docker exec backend sed -i 's|/app/old|/app/new|' /app/services/rag.py
```

## ❌ 何が起きたか

Git Bash (MSYS2) が `/app/` を `C:/Program Files/Git/app/` に自動変換してしまい、sedコマンドが壊れた。

エラーメッセージ例：
```
sed: can't read C:/Program Files/Git/app/services/rag.py: No such file or directory
```

コマンドラインに表示される実行内容と異なり、デバッグが非常にやりにくい。

## なぜこうなるのか

MSYS2（Git Bash の基盤）には、**Unixパスを自動的にWindowsパスに変換する機能**がある。これはWindows環境でのファイルアクセス互換性を高めるための設計だ。

具体例：
- `/usr/bin` → `C:/Program Files/Git/usr/bin`
- `/opt/tool` → `C:/Program Files/Git/opt/tool`
- `/app/` → `C:/Program Files/Git/app/`

問題は、コマンドの**引数**に含まれる `/` で始まる文字列もこの変換の対象になること。特に Docker コマンドでコンテナ内パスを指定する場合、意図しない変換が発生してしまう。

## ✅ 解決：MSYS_NO_PATHCONV=1

環境変数 `MSYS_NO_PATHCONV=1` をコマンドの先頭に付けることで、MSYS2 のパス自動変換を無効にできる。

```bash
MSYS_NO_PATHCONV=1 wsl docker exec backend sed -i 's|/app/old|/app/new|' /app/services/rag.py
```

実行結果：
- MSYS2 による自動変換が無効化される
- `/app/` は Unixパスのままコンテナに渡される
- sed が正常に動作する

## 比較表

| 状況 | コマンド | 結果 |
|------|---------|------|
| 未対策 | `wsl docker exec backend sed -i 's\|/app/old\|/app/new\|' /app/services/rag.py` | ✗ パス変換により失敗 |
| 対策済み | `MSYS_NO_PATHCONV=1 wsl docker exec backend sed -i 's\|/app/old\|/app/new\|' /app/services/rag.py` | ✓ 正常に実行 |

## 他の使用例

この問題は Docker に限らず、Unixパスを含む様々なコマンドで発生する可能性がある：

```bash
# ファイルコピー
MSYS_NO_PATHCONV=1 wsl docker cp /app/config.json backend:/app/config.json

# シェルスクリプト実行
MSYS_NO_PATHCONV=1 wsl docker exec backend bash -c 'cat /app/file.txt'

# マウントパス指定
MSYS_NO_PATHCONV=1 docker run -v /data:/data my-image
```

## バイブコーディング（開発時の脳内ルール）

**Git BashからDockerコンテナ内のファイルを操作する際は必ず `MSYS_NO_PATHCONV=1` プレフィックスを付けること。**

Unixパスを含む引数がMSYS2により自動変換されるため、このプレフィックスなしでは予期しない動作が発生する。特にコンテナ内の `/app/` や `/usr/` といった絶対パスを扱う場合に必須。

## まとめ

- Git Bash (MSYS2) はUnixパスを Windows パスに自動変換する
- コマンド引数内の `/` で始まる文字列も対象になる
- Docker コマンドではこの変換が邪魔になる
- `MSYS_NO_PATHCONV=1` で変換を無効化できる
- 開発時はこれをルールとして組み込むこと

開発効率を上げるために、エイリアスやスクリプト化も有効：

```bash
# .bashrc に追加
alias docker-exec='MSYS_NO_PATHCONV=1 wsl docker exec'
alias docker-cp='MSYS_NO_PATHCONV=1 wsl docker cp'
```

この小さな知識がデバッグ時間を大幅に削減できる。
