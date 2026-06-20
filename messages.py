import discord

def get_lang(locale: discord.Locale) -> str:
    return "ja" if locale == discord.Locale.japanese else "en"

# =============================================================================
# コマンド説明文（Translator 用）
# =============================================================================
CMD_DESC = {
    "start": {
        "en": "Start a custom match and select a playlist",
        "ja": "カスタムを開始し、プレイリストを選択します",
    },
    "next": {
        "en": "Select a simulation",
        "ja": "シミュレーションを選択します",
    },
    "next.count": {
        "en": "Number of matches to draw (1–5, default: 1)",
        "ja": "選択する試合数（1〜5、デフォルト: 1）",
    },
    "backto": {
        "en": "Revert the simulation state to a specific snapshot ID",
        "ja": "指定したスナップショットIDの状態に巻き戻します",
    },
    "backto.id": {
        "en": "Snapshot ID to revert to",
        "ja": "戻り先のスナップショットID",
    },
    "redraw": {
        "en": "Redraw the previous simulation",
        "ja": "直前のシミュレーションを引き直します",
    },
    "reset": {
        "en": "Reset and reshuffle the deck for the current playlist",
        "ja": "現在のプレイリストの山札をリセットして再シャッフルします",
    },
    "deck": {
        "en": "Show remaining simulation data in the index (admin)",
        "ja": "現在のインデックスに残っているシミュレーションデータを表示します（運営用）",
    },
    "history": {
        "en": "Show recent simulation history (admin)",
        "ja": "直近のシミュレーション履歴を表示します（運営用）",
    },
    "status": {
        "en": "Check internal system state (admin)",
        "ja": "システムの内部状態を確認します（運営用）",
    },
}

# =============================================================================
# レスポンスメッセージ
# =============================================================================
_MSG = {
    # /start
    "start_prompt": {
        "en": "Please select a playlist to use:",
        "ja": "利用するプレイリストを選択してください:",
    },
    "start_timeout": {
        "en": "⏳ The selection has timed out. Please run `/start` again.",
        "ja": "⏳ 選択時間が終了したためキャンセルされました。もう一度 `/start` を実行してください。",
    },
    "btn_ranked": {
        "en": "Ranked Arena",
        "ja": "Ranked Arena",
    },
    "btn_ga": {
        "en": "GA (Gentleman's Agreement)",
        "ja": "GA (Gentleman's Agreement)",
    },
    "btn_cancel": {
        "en": "Cancel",
        "ja": "キャンセル",
    },
    "start_save_info": {
        "en": "─────────────────────\nSave data found for **[{pl_name}]**.\nLast played: {last_played}\nRemaining deck: {remaining} cards\n─────────────────────",
        "ja": "─────────────────────\n**[{pl_name}]** のセーブデータが見つかりました。\n最終プレイ: {last_played}\n残りデッキ: {remaining} 枚\n─────────────────────",
    },
    "never_played": {
        "en": "Never",
        "ja": "未プレイ",
    },
    "btn_resume": {
        "en": "Resume from save",
        "ja": "続きから始める",
    },
    "btn_reset": {
        "en": "Reset and start over",
        "ja": "リセットして最初から",
    },
    "start_resumed": {
        "en": "✅ Resumed from save data. You can now use `/next`.",
        "ja": "✅ 続きから再開しました。`/next` で試合を開始できます。",
    },
    "start_reset_done": {
        "en": "🔄 Reset the deck. You can now use `/next`.",
        "ja": "🔄 山札をリセットしました。`/next` で新しい試合を開始できます。",
    },
    "start_canceled": {
        "en": "❌ Operation canceled.",
        "ja": "❌ 操作をキャンセルしました。",
    },
    # /next
    "next_header": {
        "en": "🛸 **[{pl_name}] Simulation selected** (ID: {id}) | Remaining: {remaining}/{total}",
        "ja": "🛸 **[{pl_name}] シミュレーションを選択** (ID: {id}) | 残データ: {remaining}/{total}",
    },
    "match_line": {
        "en": "\n[Match {i}] 🗺️ **{map}** | ⚔️ **{rule}**",
        "ja": "\n【第 {i} 試合】🗺️ **{map}** | ⚔️ **{rule}**",
    },
    # /backto
    "backto_success": {
        "en": "⏪ Reverted to Snapshot ID **{id}** and reshuffled the deck. (Remaining: {remaining}/{total})",
        "ja": "⏪ スナップショット ID **{id}** の状態に巻き戻し、山札を再シャッフルしました。(残データ: {remaining}/{total})",
    },
    "err_invalid_snapshot": {
        "en": "❌ Invalid Snapshot ID. Snapshot not found or too old.",
        "ja": "❌ 無効なスナップショットIDです。見つからないか、古すぎて破棄されています。",
    },
    # /redraw
    "redraw_header": {
        "en": "🔄 **[{pl_name}] Redrawn** (ID: {id}) | Remaining: {remaining}/{total}",
        "ja": "🔄 **[{pl_name}] 引き直しました** (ID: {id}) | 残データ: {remaining}/{total}",
    },
    # /reset
    "reset_done": {
        "en": "🔄 Data index refreshed. The deck for [{pl_name}] has been reshuffled.",
        "ja": "🔄 データインデックスをリフレッシュしました。[{pl_name}] の山札を再シャッフルします。",
    },
    # /deck
    "deck_header": {
        "en": "🗂️ **Simulation Data Status [{pl_name}]**",
        "ja": "🗂️ **シミュレーションデータ状況 [{pl_name}]**",
    },
    "deck_section": {
        "en": "\n📚 **Deck ({count} cards)**\n",
        "ja": "\n📚 **山札 ({count}枚)**\n",
    },
    "pq_section": {
        "en": "\n⏳ **Priority Queue ({count} cards)**\n",
        "ja": "\n⏳ **優先キュー ({count}枚)**\n",
    },
    "deck_excluded": {
        "en": "\n🚫 **Excluded Slayers ({count} cards)**\n",
        "ja": "\n🚫 **除外プール（お留守番スレイヤー） ({count}枚)**\n",
    },
    "none": {
        "en": "None\n",
        "ja": "なし\n",
    },
    # /history
    "history_empty": {
        "en": "📜 **[{pl_name}] Recent History**\n\nNo history yet.",
        "ja": "📜 **[{pl_name}] 直近のシミュレーション履歴**\n\n履歴がありません。",
    },
    "history_header": {
        "en": "📜 **[{pl_name}] Last {count} matches**\n\n",
        "ja": "📜 **[{pl_name}] 直近 {count} 試合の履歴**\n\n",
    },
    # /status
    "status_header": {
        "en": "📊 **Internal Status** | Current Playlist: **{pl_name}**\n\n",
        "ja": "📊 **内部ステータス** | 現在のプレイリスト: **{pl_name}**\n\n",
    },
    "status_deck": {
        "en": "📚 Deck: **{count}** cards\n",
        "ja": "📚 山札: **{count}** 枚\n",
    },
    "status_pq": {
        "en": "⏳ Priority Queue: **{count}** cards\n",
        "ja": "⏳ 優先キュー: **{count}** 枚\n",
    },
    "status_trash": {
        "en": "🗑️ Trash (used): **{count}** cards\n",
        "ja": "🗑️ トラッシュ（使用済み）: **{count}** 枚\n",
    },
    "status_excluded": {
        "en": "🚫 Excluded Pool: **{count}** cards\n\n",
        "ja": "🚫 除外プール（お留守番）: **{count}** 枚\n\n",
    },
    "status_history": {
        "en": "📜 History retained: **{count}** matches\n",
        "ja": "📜 履歴保持数: **{count}** 試合\n",
    },
    "status_snapshots": {
        "en": "📸 Snapshots retained: **{count}**\n",
        "ja": "📸 スナップショット保持数: **{count}**\n",
    },
    # エラー・共通
    "err_count_range": {
        "en": "💡 You can request 1–5 matches at a time.",
        "ja": "💡 一度に要請できるのは 1〜5 試合までです。",
    },
    "err_busy": {
        "en": "⏳ Another request is being processed. Please wait a moment.",
        "ja": "⏳ 現在、別の要請を処理中です。少し待ってから再度お試しください。",
    },
    "err_no_snapshot": {
        "en": "❌ No snapshot found to redraw from.",
        "ja": "❌ 引き直すためのスナップショットが見つかりません。",
    },
    "err_no_last_results": {
        "en": "❌ No previous results found. Cannot redraw.",
        "ja": "❌ 直前の結果が見つからないため引き直せません。",
    },
    "err_generic": {
        "en": "❌ An error occurred. Please try again later.",
        "ja": "❌ 処理中にエラーが発生しました。時間を置いて再度お試しください。",
    },
    # on_ready
    "activity": {
        "en": "Selecting Maps & Modes",
        "ja": "マップ＆モードを選出中",
    },
    "on_ready_log": {
        "en": "🤖 {name} is now online!",
        "ja": "🤖 {name} がオンラインになりました！",
    },
}

def t(locale: discord.Locale, key: str, **kwargs) -> str:
    lang = get_lang(locale)
    text = _MSG[key][lang]
    return text.format(**kwargs) if kwargs else text