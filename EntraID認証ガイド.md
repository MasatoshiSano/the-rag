# Entra ID × Amazon Cognito SAML 認証 — 他システム展開ガイド

> **目的:** saml-bedrock Cognito 共用方式による Entra ID 認証を、新規システムへ展開するための手順・参考実装をまとめたガイドです。  
> **対象読者:** 新システムに Entra ID 認証を導入したい開発者全般（言語・フレームワーク不問）  
> **更新日:** 2026-03-30

---

## 1. 概要

社内 DX システム群は **Microsoft Entra ID（旧 Azure AD）** を IdP（Identity Provider）、**Amazon Cognito** を認証ブローカーとして使用し、ブラウザアプリの認証を実現しています。

### ⚠️ 認証アーキテクチャ：外部 Cognito 共用方式

各システムは **独自の Cognito User Pool を持たず**、別環境で運用されている既存の Cognito User Pool（ドメイン: `saml-bedrock`）を **共用** しています。

| 項目 | 値 |
|---|---|
| **Cognito 管理元** | 別環境（`saml-bedrock`）の管理者 |
| **各システムの認証方式** | 共用 Cognito に追加された **App Client** を使用 |
| **SAML IdP（Melgit）** | 共用 Cognito 側で設定済み。各システム側での設定は不要 |
| **各システム側の責務** | App Client ID を受け取り、フロントエンド・API Gateway に設定するのみ |

> **なぜ共用するのか？**
> - Entra ID（Melgit）との SAML 連携設定は既に `saml-bedrock` 側で完了しているため、同一の IdP 設定を再利用できる
> - 追加システムごとに App Client を追加するだけでよく、SAML メタデータや属性マッピングの再設定が不要
> - 認証基盤の一元管理により、セキュリティポリシーの統一が容易

```
                         ┌─────────────────────────────────┐
                         │   別環境（saml-bedrock）         │
                         │                                 │
                         │  Cognito User Pool              │
                         │  ├─ SAML IdP: Melgit (設定済み) │
                         │  ├─ App Client A (別システム用)  │
                         │  └─ App Client B (本システム用)  │◄── 管理者に依頼して追加
                         │                                 │
                         └────────────┬────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │  導入先システム（例: GIZIRAKU）│ AWSアカウント:338658063532 │
         │                            │                            │
[ユーザー]                            │
   │                                  │
   │ ① ブラウザでアクセス             │
   ▼                                  │
[フロントエンド (SPA)]                │
   │                                  │
   │ ② 未認証 → Cognito Hosted UI へ │
   ▼                                  │
[Cognito Hosted UI (saml-bedrock)]────┘
   │
   │ ③ SAML リクエスト
   ▼
[Entra ID (SAML IdP: Melgit)]
   │ 社内アカウントでログイン
   │ ④ SAMLアサーション返却
   ▼
[Cognito Hosted UI (saml-bedrock)]
   │ ⑤ 認可コード発行
   ▼
[フロントエンド (SPA)]
   │ ⑥ 認可コード → トークン交換 (PKCE)
   ▼
[ID トークン・アクセストークン取得]
   │
   │ ⑦ API リクエスト (Authorization: Bearer <ID Token>)
   ▼
[API Gateway (本システム)]
   │
   │ ⑧ Cognito Authorizer でトークン検証
   │   （外部 Cognito の User Pool ARN を参照）
   ▼
[バックエンド Lambda (本システム)]
```

---

## 2. 登場コンポーネントと役割

| コンポーネント | 役割 | 管理元 |
|---|---|---|
| **Entra ID** | 社内ユーザー認証の実体（SAML IdP）。メール/パスワード・MFA を管理 | 社内 IT |
| **Cognito User Pool** | SAML フェデレーション受け口。トークン発行（JWT）を担当 | **別環境（saml-bedrock）** |
| **Cognito App Client** | 本システム用のクライアント。Cognito に追加依頼して取得 | **別環境（saml-bedrock）** |
| **Cognito Hosted UI** | ブラウザからアクセスする認証画面。OAuth 2.0 / OIDC エンドポイントを提供 | **別環境（saml-bedrock）** |
| **Cognito Authorizer** | API Gateway で JWT を検証（外部 Cognito の User Pool を参照） | **導入先システム** |
| **フロントエンド SPA** | PKCE フローを実装。ライブラリ不要で認証を実行 | **導入先システム** |

---

## 3. 必要なパラメータ（設定値）

認証に必要な設定値は **4つのみ**。すべて **別環境（saml-bedrock）の管理者から提供** される値です。

| パラメータ名 | 説明 | 取得元 | 例 |
|---|---|---|---|
| `COGNITO_DOMAIN` | Cognito Hosted UI のドメイン | saml-bedrock 管理者 | `saml-bedrock.auth.ap-northeast-1.amazoncognito.com`（**確定**） |
| `COGNITO_CLIENT_ID` | **導入先システム用** App Client ID | saml-bedrock 管理者 | システムごとに異なる（追加依頼後に付与） |
| `COGNITO_REDIRECT_URI` | 認証後のリダイレクト先 URL（導入先の CloudFront URL） | 導入先システム管理者 | `https://（導入先 CloudFront ドメイン）/` |
| `COGNITO_IDP_NAME` | Cognito に登録済みの SAML IdP 名 | saml-bedrock 管理者 | `Melgit`（**確定**） |

> **確定している共通パラメータ（すべてのシステムで同じ値を使用）:**
>
> | パラメータ | 確定値 |
> |---|---|
> | Cognito ドメイン | `saml-bedrock.auth.ap-northeast-1.amazoncognito.com` |
> | User Pool ID | `ap-northeast-1_GlUBBVlrW` |
> | User Pool ARN | `arn:aws:cognito-idp:ap-northeast-1:387788281372:userpool/ap-northeast-1_GlUBBVlrW` |
> | IdP 名 | `Melgit` |
>
> **App Client ID のみシステムごとに異なります。** API Gateway の Cognito Authorizer には User Pool ARN をそのまま設定してください。

---

## 4. 認証フロー詳細（OAuth 2.0 Authorization Code + PKCE）

### ステップ 1 — 認証開始（ログインリダイレクト）

ブラウザを以下 URL へリダイレクトします。

```
GET https://{COGNITO_DOMAIN}/oauth2/authorize
  ?response_type=code
  &client_id={CLIENT_ID}
  &redirect_uri={REDIRECT_URI}
  &scope=openid email profile
  &identity_provider={IDP_NAME}         ← SAML IdP を直接指定（ログイン画面をスキップ）
  &code_challenge_method=S256
  &code_challenge={BASE64URL(SHA256(code_verifier))}
```

**PKCE（Proof Key for Code Exchange）の目的:**  
認可コードを傍受されても、`code_verifier` を持つ正規クライアントしかトークンを取得できないようにするセキュリティ機構。

#### code_verifier / code_challenge の生成手順

```
1. 32バイトのランダムデータを生成
2. Base64URL エンコードして code_verifier とする
3. SHA-256(code_verifier) を計算
4. その結果を Base64URL エンコードして code_challenge とする
```

各言語での実装例：

**Python**
```python
import os, hashlib, base64

def generate_code_verifier():
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode()

def generate_code_challenge(verifier: str):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
```

**JavaScript / TypeScript**
```typescript
async function generateCodeVerifier(): Promise<string> {
    const arr = new Uint8Array(32);
    crypto.getRandomValues(arr);
    return base64UrlEncode(arr);
}

async function generateCodeChallenge(verifier: string): Promise<string> {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    return base64UrlEncode(new Uint8Array(digest));
}
```

**C# / VB.NET**
```csharp
using System.Security.Cryptography;
using System.Text;

string GenerateCodeVerifier() {
    var bytes = RandomNumberGenerator.GetBytes(32);
    return Base64UrlEncode(bytes);
}

string GenerateCodeChallenge(string verifier) {
    var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(verifier));
    return Base64UrlEncode(bytes);
}
// Base64UrlEncode: Convert.ToBase64String(bytes).Replace('+','-').Replace('/','_').TrimEnd('=')
```

---

### ステップ 2 — 社内アカウントでログイン

- `identity_provider=Melgit` を指定することで、Cognito のログイン画面を経由せず **直接 Entra ID のログイン画面** に遷移します
- 社内メール・パスワード（および MFA）で認証後、Entra ID が SAML アサーションを Cognito へ送信
- Cognito が認可コード (`code`) を発行し、`REDIRECT_URI?code=xxxx` へリダイレクト

---

### ステップ 3 — 認可コードをトークンに交換

```
POST https://{COGNITO_DOMAIN}/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&client_id={CLIENT_ID}
&redirect_uri={REDIRECT_URI}
&code={認可コード}
&code_verifier={ステップ1で生成した code_verifier}
```

**レスポンス（JSON）:**
```json
{
  "id_token": "eyJ...",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

---

### ステップ 4 — API 呼び出し

取得した ID トークンを `Authorization` ヘッダーに付加します。

```
GET https://api.example.com/troubleshooting/history
Authorization: Bearer {id_token}
```

---

### ステップ 5 — トークンのリフレッシュ

ID トークンの有効期限（デフォルト1時間）が近づいたら、リフレッシュトークンで更新します。

```
POST https://{COGNITO_DOMAIN}/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
&client_id={CLIENT_ID}
&refresh_token={refresh_token}
```

> ℹ️ リフレッシュトークン自体は再発行されません。レスポンスには `id_token` と `access_token` のみ含まれます。

---

### ステップ 6 — ログアウト

```
GET https://{COGNITO_DOMAIN}/logout
  ?client_id={CLIENT_ID}
  &logout_uri={ログアウト後のリダイレクト先}
```

ローカルのトークン（sessionStorage 等）を削除した後、上記 URL へリダイレクトすることで Cognito セッションも終了します。

---

## 5. JWT トークン（ID Token）の構造

Cognito が発行する ID Token は JWT（JSON Web Token）形式で、Base64URL エンコードされた3つのパートからなります。

```
{header}.{payload}.{signature}
```

**ペイロードの主要クレーム（本システムの場合）:**

```json
{
  "sub": "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXX",   // ユーザー固有ID（DynamoDB のキーに使用）
  "email": "Yamada.Taro@xx.MitsubishiElectric.co.jp",
  "name": "Yamada Taro/山田 太郎(MELCO/姫事 ソ企)",
  "given_name": "太郎",
  "family_name": "山田",
  "nickname": "XX99999@ad.melco.co.jp",            // @ 前が社員番号
  "address": { "formatted": "三菱電機（株）/車本/姫事/高ソ/ソ企" },  // 所属組織
  "cognito:username": "melgit_xx99999@ad.melco.co.jp",
  "cognito:groups": ["ap-northeast-1_GlUBBVlrW_Melgit"],
  "iss": "https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_GlUBBVlrW",
  "aud": "34gsn6a80pqrqnanrg63d228up",              // = CLIENT_ID
  "exp": 1773889577,                                // 有効期限 (Unix時刻)
  "iat": 1773885977                                 // 発行時刻 (Unix時刻)
}
```

**クレームのデコード方法（言語共通）:**

```
1. JWT を "." で分割 → [header, payload, signature]
2. payload を Base64URL デコード
3. UTF-8 文字列として JSON パース

注意: atob() / Base64.decode() 等は Latin-1 で処理するため、
      日本語等のマルチバイト文字が含まれる場合は必ず UTF-8 で
      デコードすること（文字化け対策）。
```

---

## 6. サーバーサイドのトークン検証（Cognito Authorizer）

API Gateway は全リクエストの `Authorization: Bearer <token>` を **Cognito Authorizer** で検証します。

> **外部 Cognito 共用方式のポイント:**
> API Gateway の Cognito Authorizer に **saml-bedrock の User Pool ARN** を設定することで、外部 Cognito が発行したトークンを直接検証できます。

Cognito Authorizer は以下の手順で JWT を検証します。

```
① token の header を Base64URL デコード → kid（鍵ID）を取得
② token の payload を Base64URL デコード → iss（発行者URL）を取得
   ※ iss は saml-bedrock 側の Cognito User Pool URL になる
③ JWKS エンドポイントから公開鍵を取得
   URL: {iss}/.well-known/jwks.json
   例: https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_XXXXXXXXX/.well-known/jwks.json
④ kid に一致する公開鍵（RSA）を選択
⑤ RS256 署名を検証
⑥ exp（有効期限）が現在時刻より未来であることを確認
⑦ aud（Audience）が本システムの App Client ID に一致することを確認
⑧ iss が "https://cognito-idp." で始まることを確認（外部発行者の拒否）
```

検証成功時、Cognito Authorizer は API Gateway に Allow ポリシーを返し、後続の Lambda Function へクレームを渡します。

---

## 7. バックエンドでのユーザー識別

バックエンド Lambda では `event.requestContext.authorizer` からユーザー情報を取得します。

> **外部 Cognito 共用時の注意:**
> Cognito Authorizer 経由の場合、`event.requestContext.authorizer.claims` にトークンのクレームが格納されます。

**Python での取得例:**
```python
def extract_user_claims(event: dict) -> dict:
    # Cognito Authorizer 経由（外部 Cognito 共用方式）
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    if claims:
        return {
            "sub": claims.get("sub", ""),
            "email": claims.get("email", ""),
            "username": claims.get("cognito:username", ""),
        }
    return {}

def handler(event, context):
    claims = extract_user_claims(event)
    user_id = claims["sub"]  # DynamoDB のパーティションキーとして使用
```

---

## 8. トークンの保存場所と有効期限

| トークン | 保存場所 | 有効期限 |
|---|---|---|
| ID Token | sessionStorage（ブラウザ） | 1時間（デフォルト） |
| Access Token | sessionStorage（ブラウザ） | 1時間（デフォルト） |
| Refresh Token | sessionStorage（ブラウザ） | 30日（デフォルト） |

- **sessionStorage** を使用しているため、**タブを閉じるとトークンは失われ**、再ログインが必要になります
- ID Token の有効期限 5分前に自動的にリフレッシュが実行されます

---

## 9. Cognito側の設定（saml-bedrock 管理者作業）

> **⚠️ 本セクションの設定は、saml-bedrock 環境の管理者が行う作業です。**
> **新システムのデプロイ担当者は、結果の App Client ID を受け取るだけです。**

本システム用の App Client を既存の Cognito User Pool（`saml-bedrock`）に追加してもらう必要があります。

### saml-bedrock 管理者への依頼内容

#### 1. App Client の追加

| 項目 | 設定値 |
|---|---|
| 許可されている OAuth フロー | Authorization code grant |
| 許可されているスコープ | openid, email, profile |
| コールバック URL | `https://（導入先 CloudFront URL）/` |
| サインアウト URL | `https://（導入先 CloudFront URL）/` |
| サポートする ID プロバイダー | Melgit（既存 SAML IdP） |
| クライアントシークレット | **なし**（パブリッククライアント） |

> ローカル開発時は `http://localhost:3000/` や `http://localhost:3001/` もコールバック URL に追加してもらう（使用ポートはシステムによって異なる）

#### 2. 管理者から受け取る値

| 値 | 用途 |
|---|---|
| App Client ID | フロントエンドの環境変数に設定（キー名はフレームワークによる） |
| User Pool ARN | API Gateway Cognito Authorizer に設定（確定値: `arn:aws:cognito-idp:ap-northeast-1:387788281372:userpool/ap-northeast-1_GlUBBVlrW`） |
| Cognito ドメイン | フロントエンドに設定（確定値: `saml-bedrock.auth.ap-northeast-1.amazoncognito.com`） |
| IdP 名 | フロントエンドに設定（確定値: `Melgit`） |

### SAML IdP（Entra ID）の設定 — 本システムでは不要

以下の SAML 属性マッピングは **saml-bedrock 側で既に設定済み** のため、本システムでの再設定は不要です。参考として記載します。

| Entra ID 属性 | Cognito クレーム |
|---|---|
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress` | `email` |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name` | `name` |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname` | `given_name` |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname` | `family_name` |
| （カスタム属性） | `nickname` → 社員番号@ドメイン |
| （カスタム属性） | `address` → 所属組織 |

---

## 10. セキュリティ上の注意点

| リスク | 対策 |
|---|---|
| 認可コードの傍受 | PKCE（S256）必須。code_verifier なしではトークン取得不可 |
| トークンの偽造 | RS256 署名 + JWKS による公開鍵検証 |
| 有効期限切れトークンの使用 | `exp` クレームを検証。期限切れは必ず拒否 |
| 外部 Cognito プールのなりすまし | `iss` が `https://cognito-idp.` で始まることを強制確認 |
| クライアント不一致 | `aud` を自システムの CLIENT_ID と照合 |
| XSS によるトークン窃取 | sessionStorage 使用（localStorage より若干安全）。Content-Security-Policy の設定を推奨 |

---

## 11. 参考：GIZIRAKU のファイル構成

```
GIZIRAKU/
├── frontend/
│   ├── src/amplify-config.ts          # OAuth 2.0 PKCE フロー設定（Amplify）
│   └── .env.production                # REACT_APP_COGNITO_* 環境変数
├── backend/
│   └── app/middleware/                 # バックエンド共通: クレーム取得ユーティリティ
├── cdk/
│   ├── lib/stacks/api_stack.py        # Cognito Authorizer（外部 User Pool ARN 参照）
│   └── cdk.json                       # cognito_client_id / cognito_domain / saml_idp_name
└── docs/
    └── EntraID認証ガイド.md            # 本ドキュメント
```

> **CDK の auth_stack.py について:**
> CDK で独自の Cognito User Pool を作成する `auth_stack.py` が存在しますが、外部 Cognito 共用方式では **使用しません**。
> API Gateway の Cognito Authorizer には、saml-bedrock の User Pool ARN を直接指定します。

---

## 12. 他言語・他システムから本 API を呼び出す場合

本システムの API は **Bearer トークン認証** を採用しています。**saml-bedrock** の Cognito User Pool に登録されたアプリであれば、任意の言語から呼び出せます。

### 手順

1. 上記フローで ID Token を取得（saml-bedrock の Cognito を使用）
2. すべての API リクエストに `Authorization: Bearer {id_token}` を付加
3. トークンが期限切れの場合はリフレッシュして再送

> **注意:** API Gateway の Cognito Authorizer は `aud`（App Client ID）を検証します。
> 本システムの API を呼ぶには、本システム用の App Client ID で取得したトークンが必要です。
> 別システムの App Client ID で取得したトークンでは認証に失敗します。

### 呼び出し例（curl）

```bash
# トークン取得
TOKEN=$(curl -s -X POST \
  "https://saml-bedrock.auth.ap-northeast-1.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&client_id={導入先システムの App Client ID}&redirect_uri=https://（導入先 CloudFront URL）/&code=xxxx&code_verifier=xxxx" \
  | jq -r .id_token)

# API 呼び出し
curl -H "Authorization: Bearer $TOKEN" \
  "https://（導入先 CloudFront URL）/api/（エンドポイント）"
```

### 呼び出し例（Python requests）

```python
import requests

headers = {"Authorization": f"Bearer {id_token}"}
resp = requests.get(
    "https://（導入先 CloudFront URL）/api/（エンドポイント）",
    headers=headers
)
data = resp.json()
```

---

## 13. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| ログイン後に空白ページ | リダイレクト URI が Cognito に未登録 | saml-bedrock 管理者に本システムのコールバック URL 追加を依頼 |
| `invalid_grant` エラー | code_verifier が不正または期限切れ | SPA の sessionStorage をクリアして再試行 |
| `401 Unauthorized`（トークン有効なのに発生） | **API Gateway が EDGE-type**（内部 CloudFront 持つ）で、ユーザーの CloudFront と組み合わせ二重 CloudFront 化。Authorization ヘッダー消失 | `aws apigateway update-rest-api --patch-operations op=replace,path=/endpointConfiguration/types/EDGE,value=REGIONAL` で endpoint を REGIONAL に変更。CloudFront cache invalidation で 401 キャッシュをクリア |
| `401 Unauthorized`（トークン期限切れ） | トークン有効期限切れ or 無効 | リフレッシュトークンで更新、または再ログイン |
| `403 Forbidden`（explicit deny） | Cognito Authorizer が検証失敗 | aud（App Client ID）と iss（Cognito プール URL）を確認。特に外部 Cognito の User Pool ARN が API Gateway に正しく設定されているか確認 |
| 名前が文字化け | JWT デコード時に Latin-1 で処理 | UTF-8 デコードを使用（本ドキュメント §5 参照） |
| App Client が見つからない | saml-bedrock 側で App Client 未作成 | saml-bedrock 管理者に本システム用 App Client の追加を依頼（§9 参照） |

#### CloudFront 二重化の診断方法

`401 Unauthorized` が返される場合、ブラウザの開発者ツール → Network タブで response headers の `via` ヘッダーを確認してください。

```
via: 1.1 <ID1>.cloudfront.net (CloudFront)
via: 1.1 <ID2>.cloudfront.net (CloudFront)
```

**2つの CloudFront エントリーがある場合** = API Gateway が EDGE-type（内部 CloudFront 持つ）。ユーザーの CloudFront との二重化により Authorization ヘッダーが消失しています。

**解決策:**
1. API Gateway endpoint を EDGE → REGIONAL に変更
2. CloudFront の `/api/*` キャッシュをクリア（`create-invalidation`）

---
---

## 14. 新システムへの認証展開手順

新システムに saml-bedrock Cognito 認証を導入するための手順をまとめます。

### STEP 1: saml-bedrock 管理者への依頼

§9 に記載の内容で App Client の追加を依頼し、以下を受け取る：
- **App Client ID**（システムごとに異なる唯一の値）
- User Pool ARN は確定済みのため不要（`arn:aws:cognito-idp:ap-northeast-1:387788281372:userpool/ap-northeast-1_GlUBBVlrW`）

### STEP 2: フロントエンド環境変数の設定

フレームワークに応じた環境変数ファイルを設定する。

**React (Create React App) の場合 — `.env.production`:**
```
REACT_APP_USER_POOL_ID=ap-northeast-1_GlUBBVlrW
REACT_APP_USER_POOL_CLIENT_ID=（受け取った App Client ID）
REACT_APP_COGNITO_DOMAIN=saml-bedrock.auth.ap-northeast-1.amazoncognito.com
REACT_APP_COGNITO_IDP_NAME=Melgit
REACT_APP_FRONTEND_URL=https://（導入先 CloudFront URL）
```

**Next.js の場合 — `.env.production`:**
```
NEXT_PUBLIC_USER_POOL_ID=ap-northeast-1_GlUBBVlrW
NEXT_PUBLIC_USER_POOL_CLIENT_ID=（受け取った App Client ID）
NEXT_PUBLIC_COGNITO_DOMAIN=saml-bedrock.auth.ap-northeast-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_IDP_NAME=Melgit
NEXT_PUBLIC_FRONTEND_URL=https://（導入先 CloudFront URL）
```

**Vanilla JS の場合 — `js/auth-config.js`（SLYZE 方式）:**
```javascript
const AUTH_CONFIG = {
  COGNITO_DOMAIN: 'https://saml-bedrock.auth.ap-northeast-1.amazoncognito.com',
  CLIENT_ID: '（受け取った App Client ID）',
  USER_POOL_ID: 'ap-northeast-1_GlUBBVlrW',
  IDP_NAME: 'Melgit',
  REDIRECT_URI: 'https://（導入先 CloudFront URL）/',
};
```

### STEP 3: API Gateway の Cognito Authorizer 設定

API Gateway に Cognito Authorizer を追加する。**User Pool ARN は確定済みの値をそのまま使用してください。**

**AWS CLI での設定:**
```bash
aws apigateway create-authorizer \
  --rest-api-id （API Gateway ID） \
  --name CognitoAuthorizer \
  --type COGNITO_USER_POOLS \
  --provider-arns "arn:aws:cognito-idp:ap-northeast-1:387788281372:userpool/ap-northeast-1_GlUBBVlrW" \
  --identity-source "method.request.header.Authorization"
```

**CDK (Python) での設定:**
```python
external_user_pool = cognito.UserPool.from_user_pool_arn(
    self, "ExternalUserPool",
    user_pool_arn="arn:aws:cognito-idp:ap-northeast-1:387788281372:userpool/ap-northeast-1_GlUBBVlrW"
)
```

### STEP 4: フロントエンドのビルド・デプロイ

```bash
# ビルド（フレームワークによって異なる）
npm run build

# S3 にデプロイ（バケット名・リージョンはシステムごとに確認）
aws s3 sync build/ s3://（導入先の S3 バケット名）/ --delete --region （バケットのリージョン）

# CloudFront キャッシュ無効化
aws cloudfront create-invalidation --distribution-id （Distribution ID） --paths "/*"
```