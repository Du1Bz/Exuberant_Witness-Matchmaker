import discord

# サポートするロケール
def get_lang(locale: discord.Locale) -> str:
    """discord.Locale から言語コードを返す。日本語以外はすべて英語。"""
    return "ja" if locale == discord.Locale.japanese else "en"

# =============================================================================
# コマンド説明文（Translator 用）
# キー = コマンド名またはパラメータ名
# =============================================================================
CMD_DESC = {
    "next": {
        "en": "Select a simulation",
        "ja": "シミュレーションを選択します",
    },
    "next.count": {
        "en": "Number of matches to draw (1–5, default: 1)",
        "ja": "選択する試合数（1〜5、デフォルト: 1）",
    },
    "redraw": {
        "en": "Redraw the previous simulation",
        "ja": "直前のシミュレーションを引き直します",
    },
    "reset": {
        "en": "Reset and reshuffle the deck for this channel",
        "ja": "このチャンネルの山札をリセットして再シャッフルします",
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
    # /next
    "next_header": {
        "en": "🛸 **Exuberant Witness has selected a simulation** (remaining: {remaining}/{total})",
        "ja": "🛸 **Exuberant Witness がシミュレーションを選択しました** (残データ: {remaining}/{total})",
    },
    "match_line": {
        "en": "\n[Match {i}] 🗺️ **{map}** | ⚔️ **{rule}**",
        "ja": "\n【第 {i} 試合】🗺️ **{map}** | ⚔️ **{rule}**",
    },
    # /redraw
    "redraw_header": {
        "en": "🔄 **Redrawn** (remaining: {remaining}/{total})",
        "ja": "🔄 **引き直しました** (残データ: {remaining}/{total})",
    },
    # /reset
    "reset_done": {
        "en": "🔄 Data index refreshed. The deck for this channel has been reshuffled.",
        "ja": "🔄 データインデックスをリフレッシュしました。このチャンネルの山札を再シャッフルします。",
    },
    # /deck
    "deck_header": {
        "en": "🗂️ **Simulation Data Status**",
        "ja": "🗂️ **シミュレーションデータ状況**",
    },
    "deck_section": {
        "en": "\n📚 **Deck ({count} cards)**\n",
        "ja": "\n📚 **山札 ({count}枚)**\n",
    },
    "pq_section": {
        "en": "\n⏳ **Priority Queue ({count} cards)**\n",
        "ja": "\n⏳ **優先キュー ({count}枚)**\n",
    },
    "none": {
        "en": "None\n",
        "ja": "なし\n",
    },
    # /history
    "history_empty": {
        "en": "📜 **Recent Simulation History**\n\nNo history yet.",
        "ja": "📜 **直近のシミュレーション履歴**\n\n履歴がありません。",
    },
    "history_header": {
        "en": "📜 **Last {count} matches**\n\n",
        "ja": "📜 **直近 {count} 試合の履歴**\n\n",
    },
    # /status
    "status_header": {
        "en": "📊 **Exuberant Witness Internal Status**\n\n",
        "ja": "📊 **Exuberant Witness 内部ステータス**\n\n",
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
        "en": "🗑️ Trash (used): **{count}** cards\n\n",
        "ja": "🗑️ トラッシュ（使用済み）: **{count}** 枚\n\n",
    },
    "status_history": {
        "en": "📜 History retained: **{count}** matches\n",
        "ja": "📜 履歴保持数: **{count}** 試合\n",
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
    """ロケールに応じたメッセージを返す。"""
    lang = get_lang(locale)
    text = _MSG[key][lang]
    return text.format(**kwargs) if kwargs else text