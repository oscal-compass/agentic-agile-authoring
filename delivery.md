# Delivery Guide

このリポジトリの配布方法をまとめます。

---

## Roo Code

### 配布形式

Python パッケージとして配布します。`uvx` で GitHub から直接インストールできます。

ソースファイルはリポジトリルートで管理し、ビルド時にパッケージへ同梱されます。

```
.roomodes              モード定義（パッケージデータとして同梱）
.roo/rules-*/          ルールファイル（パッケージデータとして同梱）
src/agentic_agile_authoring/
  cli.py               install / uninstall コマンド
```

### 自動インストール

インストールしたい Roo Code プロジェクトのルートで実行します。

```bash
uvx --from git+https://github.com/yana1205/agentic-agile-authoring agentic-agile-authoring install
```

実行すると:
- `.roomodes` に Planner / Author / Reviewer モードがマージされる
- `.roo/rules-planner/`, `.roo/rules-author/`, `.roo/rules-reviewer/` が生成される
- `.roo/skills-agentic-agile-authoring/` にスキルが配置される

### 手動インストール

プロジェクトファイルを自動変更されたくない場合は `download` コマンドでリソースだけ取得し、残りの手順を自分で行えます。

```bash
uvx --from git+https://github.com/yana1205/agentic-agile-authoring agentic-agile-authoring download -o ./my-resources
```

出力先ディレクトリに以下が保存されます：

```
my-resources/
  modes/
    planner.yaml        # Roo の Settings → Modes → Import で読み込む
    author.yaml
    reviewer.yaml
  skills-agentic-agile-authoring/
                        # .roo/ 以下に手動でコピー
```

コマンド実行後に残りの手順がターミナルに表示されます。

### アンインストール

```bash
uvx --from git+https://github.com/yana1205/agentic-agile-authoring agentic-agile-authoring uninstall
```

`.roomodes` から該当モードが除去され、`.roo/rules-*/` と `.roo/skills-agentic-agile-authoring/` が削除されます。

### 使い方

モードセレクターから目的のモードに切り替えて使います。

| モード | 用途 |
|--------|------|
| Planner | トピックや brief からアウトラインとタスクリストを生成 |
| Author | アウトラインからドラフトを執筆、またはレビュー結果をもとに改稿 |
| Reviewer | ドラフトを批評し、構造化されたフィードバックレポートを生成 |

### 参考: GUI からインポートする場合

`dist/` の YAML を Roo の Settings → Modes → Import から読み込むことも可能です。

---

## Claude Code

### 配布形式

このリポジトリ自体が Claude Code Plugin です。

```
.claude-plugin/
  plugin.json        # plugin manifest
  marketplace.json   # marketplace catalog
agents/              # subagents
commands/            # slash commands
```

### インストール手順

1. marketplace を追加（初回のみ）
2. plugin をインストール

```
/plugin marketplace add yana1205/agentic-agile-authoring
/plugin install agentic-agile-authoring@agentic-agile-authoring
```

### 使い方

**Slash commands**（単発タスク）

| コマンド | 用途 |
|---------|------|
| `/agentic-agile-authoring:outline` | アウトライン生成 |
| `/agentic-agile-authoring:draft` | ドラフト執筆 |
| `/agentic-agile-authoring:review` | ドラフトレビュー |
| `/agentic-agile-authoring:revise` | レビューをもとに改稿 |

**Subagents**（複数ターンの作業）

自然言語で依頼すると Claude が自動的に適切な agent を起動します。

```
author エージェントを使って、このアウトラインからドラフトを書いて
```

| Agent | 用途 |
|-------|------|
| `planner` | アウトライン生成とタスク分解 |
| `author` | ドラフト執筆・改稿 |
| `reviewer` | ドラフトレビュー |

### ローカル開発テスト（CLI のみ）

```bash
claude --plugin-dir ./
```

---

## 比較まとめ

| | Roo Code | Claude Code |
|---|----------|-------------|
| 配布単位 | Python パッケージ（Git リポジトリ） | Git リポジトリ（plugin） |
| インストール | `uvx --from git+https://... install` | `/plugin marketplace add` → `/plugin install` |
| アンインストール | `uvx --from git+https://... uninstall` | `/plugin uninstall`（相当） |
| 更新 | 同コマンドを再実行（冪等） | marketplace 経由で更新 |
| スキルの呼び出し | モード切り替え後に自然言語 | slash command または自然言語 |
