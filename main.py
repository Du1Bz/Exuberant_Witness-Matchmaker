import os
import json
import random
import threading
import copy
import asyncio
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
import discord
from discord import app_commands
from dotenv import load_dotenv
from messages import t, CMD_DESC

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
assert TOKEN, "DISCORD_TOKEN is not set in .env"

# データ保存用のフォルダ作成
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# 競技マップ・ルールリストを deck.json から読み込む
with open("deck.json", "r", encoding="utf-8") as f:
    FULL_DECK = json.load(f)

# === クールダウン設定 ===
RULE_COOLDOWN  = 3   # 直近N試合、同じルールベースをブロック
MAP_COOLDOWN   = 4   # 直近N試合、同じマップをブロック
EXACT_COOLDOWN = 7   # 直近N試合、まったく同じマップ・ルールの組み合わせをブロック
# 注意: EXACT_COOLDOWN を変更したら history の保持上限も連動して変わる（draw_match 参照）

# === 排他制御（同時実行の競合対策） ===
channel_locks: dict[int, asyncio.Lock] = {}

def get_channel_lock(channel_id: int) -> asyncio.Lock:
    if channel_id not in channel_locks:
        channel_locks[channel_id] = asyncio.Lock()
    return channel_locks[channel_id]

# Botの初期設定（スラッシュコマンド専用）
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# =============================================================================
# 翻訳機能 (Translator)
# =============================================================================

class GuiltySparkTranslator(app_commands.Translator):
    async def translate(
        self, 
        string: app_commands.locale_str, 
        locale: discord.Locale, 
        context: app_commands.TranslationContext
    ) -> str | None:
        """Discordがコマンドを各ユーザーの言語設定で表示する際に自動で呼び出される。"""
        
        # 👇 修正箇所: コマンド「名」やパラメータ「名」の翻訳リクエストはスキップ（正規表現エラー対策）
        if context.location in (
            app_commands.TranslationContextLocation.command_name,
            app_commands.TranslationContextLocation.parameter_name
        ):
            return None

        lang = "ja" if locale == discord.Locale.japanese else "en"
        key = string.message
        if key in CMD_DESC:
            return CMD_DESC[key].get(lang, CMD_DESC[key]["en"])
        return None


# =============================================================================
# 状態管理
# =============================================================================

def load_channel_state(channel_id: int) -> dict:
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        # 古いデータ構造からのマイグレーション用
        state.setdefault("priority_queue", [])
        state.setdefault("played_cards", [])
        return state

    return {
        "deck":           [],
        "priority_queue": [],
        "played_cards":   [],
        "history":        [],
        "last_results":   [],
        "snapshot":       {},
    }

def save_channel_state(channel_id: int, state: dict) -> None:
    """アトミック書き込み: 一時ファイルに書いてから os.replace() で置換する。"""
    path = f"{DATA_DIR}/{channel_id}.json"
    dir_ = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False,
                                    suffix=".tmp", encoding="utf-8") as tmp:
        json.dump(state, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, path)


# =============================================================================
# カード抽選ロジック
# =============================================================================

def get_base_rule(rule_name: str) -> str:
    """CTF_3cap と CTF_5cap を同じ 'CTF' として統合判定するためのヘルパー。"""
    return "CTF" if rule_name.startswith("CTF") else rule_name

def is_rule_on_cooldown(card: dict, recent_history: list) -> bool:
    card_base = get_base_rule(card["rule"])
    return any(card_base == get_base_rule(h["rule"]) for h in recent_history)

def is_map_on_cooldown(card: dict, recent_history: list) -> bool:
    return any(card["map"] == h["map"] for h in recent_history)

def is_exact_on_cooldown(card: dict, recent_history: list) -> bool:
    """deck.json にフィールドが追加されても壊れないよう、map と rule だけで比較する。"""
    return any(card["map"] == h["map"] and card["rule"] == h["rule"]
               for h in recent_history)

def draw_match(state: dict) -> dict:
    deck         = state.get("deck", [])
    priority_queue = state.get("priority_queue", [])
    played_cards = state.get("played_cards", [])
    history      = state.get("history", [])

    # 初期化: すべて空っぽなら新品の山札を作る
    if not deck and not priority_queue and not played_cards:
        deck = FULL_DECK.copy()
        random.shuffle(deck)

    # クールダウン対象の履歴スライス
    rule_recent  = history[-RULE_COOLDOWN:]
    map_recent   = history[-MAP_COOLDOWN:]
    exact_recent = history[-EXACT_COOLDOWN:]

    def extract_valid_card(card_list: list) -> dict | None:
        """リストの中からクールダウン条件を満たす最初のカードを引き抜く。"""
        for i, card in enumerate(card_list):
            if (not is_map_on_cooldown(card, map_recent)
                    and not is_rule_on_cooldown(card, rule_recent)
                    and not is_exact_on_cooldown(card, exact_recent)):
                return card_list.pop(i)
        return None

    selected = None

    # === STEP 1: 優先キュー（前回引けなかったカード）から最優先で探す ===
    selected = extract_valid_card(priority_queue)

    # === STEP 2: 通常の山札から探す ===
    if not selected:
        selected = extract_valid_card(deck)

    # === STEP 3: 詰み（補充タイミング）の処理 ===
    if not selected:
        priority_queue.extend(deck)
        deck.clear()
        deck = played_cards.copy()
        random.shuffle(deck)
        played_cards.clear()
        selected = extract_valid_card(priority_queue)
        if not selected:
            selected = extract_valid_card(deck)

    # === STEP 4: 最終フォールバック ===
    if not selected:
        if priority_queue:
            selected = priority_queue.pop(0)
        elif deck:
            selected = deck.pop(0)
        else:
            deck = FULL_DECK.copy()
            random.shuffle(deck)
            selected = deck.pop(0)

    played_cards.append(selected)
    history.append(selected)

    # history は EXACT_COOLDOWN 分だけ保持すれば十分（最大値）
    # EXACT_COOLDOWN を変更した場合はここも自動で追従する
    max_history = max(MAP_COOLDOWN, RULE_COOLDOWN, EXACT_COOLDOWN)
    if len(history) > max_history:
        history.pop(0)

    state["deck"]           = deck
    state["priority_queue"] = priority_queue
    state["played_cards"]   = played_cards
    state["history"]        = history

    return selected


# =============================================================================
# 共通ヘルパー
# =============================================================================

async def _check_busy(interaction: discord.Interaction, lock: asyncio.Lock) -> bool:
    """ロック中なら busy メッセージを返して True。空きなら False。"""
    if lock.locked():
        await interaction.response.send_message(
            t(interaction.locale, "err_busy"), ephemeral=True
        )
        return True
    return False


# =============================================================================
# Bot イベント
# =============================================================================

@bot.event
async def on_ready():
    # 翻訳クラスをCommandTreeに登録してコマンドを同期
    await tree.set_translator(GuiltySparkTranslator())
    await tree.sync()
    
    # 英語（デフォルト）のステータス表示を取得して設定
    activity_name = t(discord.Locale.american_english, "activity")
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name=activity_name),
    )
    print(t(discord.Locale.japanese, "on_ready_log", name=bot.user.name))


# =============================================================================
# スラッシュコマンド
# =============================================================================

@tree.command(
    name="next",
    description=app_commands.locale_str("next"),
)
@app_commands.describe(count=app_commands.locale_str("next.count"))
@app_commands.rename(count="count")
async def cmd_next(interaction: discord.Interaction, count: int = 1):
    locale = interaction.locale

    if count < 1 or count > 5:
        await interaction.response.send_message(
            t(locale, "err_count_range"), ephemeral=True
        )
        return

    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            state = load_channel_state(channel_id)

            state["snapshot"] = {
                "deck":           copy.deepcopy(state.get("deck", [])),
                "priority_queue": copy.deepcopy(state.get("priority_queue", [])),
                "played_cards":   copy.deepcopy(state.get("played_cards", [])),
                "history":        copy.deepcopy(state.get("history", [])),
            }

            results = [draw_match(state) for _ in range(count)]
            state["last_results"] = results
            save_channel_state(channel_id, state)
            remaining = len(state.get("deck", [])) + len(state.get("priority_queue", []))

            msg = t(locale, "next_header", remaining=remaining, total=len(FULL_DECK))
            for i, m in enumerate(results, 1):
                msg += t(locale, "match_line", i=i, map=m["map"], rule=m["rule"])

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /next: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(
    name="redraw",
    description=app_commands.locale_str("redraw"),
)
async def cmd_redraw(interaction: discord.Interaction):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            snapshot     = state.get("snapshot")
            last_results = state.get("last_results", [])

            if not snapshot:
                await interaction.followup.send(
                    t(locale, "err_no_snapshot"), ephemeral=True
                )
                return
            if not last_results:
                await interaction.followup.send(
                    t(locale, "err_no_last_results"), ephemeral=True
                )
                return

            state["deck"]           = copy.deepcopy(snapshot["deck"])
            state["priority_queue"] = copy.deepcopy(snapshot["priority_queue"])
            state["played_cards"]   = copy.deepcopy(snapshot["played_cards"])
            state["history"]        = copy.deepcopy(snapshot["history"])

            results = [draw_match(state) for _ in range(len(last_results))]
            state["last_results"] = results
            save_channel_state(channel_id, state)
            remaining = len(state.get("deck", [])) + len(state.get("priority_queue", []))

            msg = t(locale, "redraw_header", remaining=remaining, total=len(FULL_DECK))
            for i, m in enumerate(results, 1):
                msg += t(locale, "match_line", i=i, map=m["map"], rule=m["rule"])

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /redraw: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(
    name="reset",
    description=app_commands.locale_str("reset"),
)
async def cmd_reset(interaction: discord.Interaction):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            path = f"{DATA_DIR}/{channel_id}.json"
            if os.path.exists(path):
                os.remove(path)

        await interaction.followup.send(t(locale, "reset_done"))

    except Exception as e:
        print(f"Error in /reset: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(
    name="deck",
    description=app_commands.locale_str("deck"),
)
async def cmd_deck(interaction: discord.Interaction):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=True)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            deck_cards = state.get("deck", [])
            pq_cards   = state.get("priority_queue", [])

            # 初期状態（まだ1回も引いていない）はフルデッキを表示
            if not deck_cards and not pq_cards and not state.get("played_cards", []):
                deck_cards = FULL_DECK.copy()

            msg  = t(locale, "deck_header") + "\n"
            msg += t(locale, "deck_section", count=len(deck_cards))
            if deck_cards:
                for c in sorted(deck_cards, key=lambda x: (x["map"], x["rule"])):
                    msg += f"・🗺️ {c['map']} | ⚔️ {c['rule']}\n"
            else:
                msg += t(locale, "none")

            msg += t(locale, "pq_section", count=len(pq_cards))
            if pq_cards:
                for c in sorted(pq_cards, key=lambda x: (x["map"], x["rule"])):
                    msg += f"・🗺️ {c['map']} | ⚔️ {c['rule']}\n"
            else:
                msg += t(locale, "none")

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /deck: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(
    name="history",
    description=app_commands.locale_str("history"),
)
async def cmd_history(interaction: discord.Interaction):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=True)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            history_list = state.get("history", [])

            if not history_list:
                msg = t(locale, "history_empty")
            else:
                msg = t(locale, "history_header", count=len(history_list))
                for i, m in enumerate(history_list, 1):
                    msg += f"{i}. 🗺️ **{m['map']}** | ⚔️ **{m['rule']}**\n"

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /history: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(
    name="status",
    description=app_commands.locale_str("status"),
)
async def cmd_status(interaction: discord.Interaction):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=True)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            deck_count   = len(state.get("deck", []))
            pq_count     = len(state.get("priority_queue", []))
            played_count = len(state.get("played_cards", []))

            # 未使用状態はフルデッキ相当として表示
            if deck_count == 0 and pq_count == 0 and played_count == 0:
                deck_count = len(FULL_DECK)

            history_count = len(state.get("history", []))

            msg  = t(locale, "status_header")
            msg += t(locale, "status_deck",    count=deck_count)
            msg += t(locale, "status_pq",      count=pq_count)
            msg += t(locale, "status_trash",   count=played_count)
            msg += t(locale, "status_history", count=history_count)

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /status: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


# =============================================================================
# Render用 ダミーWebサーバー
# =============================================================================

def run_dummy_server():
    class DummyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"I am 031 Exuberant Witness. The matchmaker is online.")

        def log_message(self, format, *args):
            pass  # アクセスログを抑制

    port = int(os.getenv("PORT", 10000))
    HTTPServer(("0.0.0.0", port), DummyHandler).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    bot.run(TOKEN)