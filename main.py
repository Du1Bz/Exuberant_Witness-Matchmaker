import os
import json
import random
import threading
import copy
import asyncio
from http.server import SimpleHTTPRequestHandler, HTTPServer
import discord
from discord import app_commands
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# データ保存用のフォルダ作成
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# 競技マップ・ルールリストを deck.json から読み込む
with open("deck.json", "r", encoding="utf-8") as f:
    FULL_DECK = json.load(f)

# === クールダウン設定 ===
RULE_COOLDOWN = 3          # 直近N試合、同じルールベースをブロック
MAP_COOLDOWN = 4           # 直近N試合、同じマップをブロック
EXACT_COOLDOWN = 7         # 直近N試合、まったく同じマップ・ルールの組み合わせをブロック

# === 排他制御（同時実行の競合対策） ===
channel_locks = {}
def get_channel_lock(channel_id):
    if channel_id not in channel_locks:
        channel_locks[channel_id] = asyncio.Lock()
    return channel_locks[channel_id]

# Botの初期設定（スラッシュコマンド専用）
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# チャンネルごとにデータを読み書き
def load_channel_state(channel_id):
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
            # 古いデータ構造からのマイグレーション用
            if "priority_queue" not in state: state["priority_queue"] = []
            if "played_cards" not in state: state["played_cards"] = []
            return state
            
    # 新しいデータ構造: 山札、優先キュー、使用済み、履歴、スナップショット
    return {
        "deck": [], 
        "priority_queue": [],
        "played_cards": [],
        "history": [], 
        "last_results": [],
        "snapshot": {}
    }

def save_channel_state(channel_id, state):
    path = f"{DATA_DIR}/{channel_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_base_rule(rule_name):
    """CTF_3cap と CTF_5cap を同じ 'CTF' として統合判定するためのヘルパー"""
    return "CTF" if rule_name.startswith("CTF") else rule_name

def is_rule_on_cooldown(card, recent_history):
    """直近の履歴の中で、同じルールベースが使われているか"""
    card_base = get_base_rule(card["rule"])
    return any(card_base == get_base_rule(h["rule"]) for h in recent_history)

def is_map_on_cooldown(card, recent_history):
    """直近の履歴の中で、同じマップが使われているか"""
    return any(card["map"] == h["map"] for h in recent_history)

def draw_match(state):
    deck = state.get("deck", [])
    priority_queue = state.get("priority_queue", [])
    played_cards = state.get("played_cards", [])
    history = state.get("history", [])

    # 初期化: すべて空っぽなら新品の山札を作る
    if not deck and not priority_queue and not played_cards:
        deck = FULL_DECK.copy()
        random.shuffle(deck)

    # クールダウン対象の履歴
    rule_recent = history[-RULE_COOLDOWN:] if len(history) >= RULE_COOLDOWN else history
    map_recent = history[-MAP_COOLDOWN:] if len(history) >= MAP_COOLDOWN else history
    exact_recent = history[-EXACT_COOLDOWN:] if len(history) >= EXACT_COOLDOWN else history

    def extract_valid_card(card_list):
        """リストの中からクールダウン条件を満たす最初のカードを引き抜く"""
        for i, card in enumerate(card_list):
            if (not is_map_on_cooldown(card, map_recent) and 
                not is_rule_on_cooldown(card, rule_recent) and 
                card not in exact_recent):
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
    
    max_history_needed = max(MAP_COOLDOWN, RULE_COOLDOWN, EXACT_COOLDOWN)
    if len(history) > max_history_needed:
        history.pop(0)

    state["deck"] = deck
    state["priority_queue"] = priority_queue
    state["played_cards"] = played_cards
    state["history"] = history

    return selected

@bot.event
async def on_ready():
    await tree.sync()
    activity = discord.Game(name="シミュレーションを監視")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f"🤖 {bot.user.name} がオンラインになりました！")

@tree.command(name="next", description="シミュレーションを選択します")
@app_commands.describe(count="選択する試合数（1〜5、デフォルト: 1）")
async def next(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 5:
        await interaction.response.send_message("💡 一度に要請できるのは 1〜5 試合までです。", ephemeral=True)
        return

    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    # ロック取得前に、すでにロック中であれば弾く（連打対策）
    if lock.locked():
        await interaction.response.send_message("⏳ 現在、別の要請を処理中です。少し待ってから再度お試しください。", ephemeral=True)
        return

    # Discordの3秒タイムアウト回避
    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            
            # --- スナップショットの作成 (実行前の状態を完全保存) ---
            state["snapshot"] = {
                "deck": copy.deepcopy(state.get("deck", [])),
                "priority_queue": copy.deepcopy(state.get("priority_queue", [])),
                "played_cards": copy.deepcopy(state.get("played_cards", [])),
                "history": copy.deepcopy(state.get("history", []))
            }
            
            results = []
            for _ in range(count):
                match = draw_match(state)
                results.append(match)
                
            state["last_results"] = results
            save_channel_state(channel_id, state)
            remaining = len(state.get("deck", [])) + len(state.get("priority_queue", []))

        msg = f"🛸 **343 Guilty Spark がシミュレーションを選択しました** (残データ: {remaining}/{len(FULL_DECK)})\n"
        for i, m in enumerate(results):
            msg += f"\n【第 {i+1} 試合】🗺️ **{m['map']}** |  ⚔️ **{m['rule']}**"
            
        await interaction.followup.send(msg)
        
    except Exception as e:
        print(f"Error in /next: {e}")
        await interaction.followup.send("❌ 処理中にエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)


@tree.command(name="redraw", description="直前のシミュレーションを引き直します")
async def redraw(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if lock.locked():
        await interaction.response.send_message("⏳ 現在、別の要請を処理中です。少し待ってから再度お試しください。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            
            snapshot = state.get("snapshot")
            last_results = state.get("last_results", [])
            
            if not snapshot:
                await interaction.followup.send("❌ 引き直すためのスナップショットが見つかりません。", ephemeral=True)
                return
            if not last_results:
                await interaction.followup.send("❌ 直前の結果が見つからないため引き直せません。", ephemeral=True)
                return
                
            count = len(last_results)
            
            # --- スナップショットの完全復元 ---
            state["deck"] = copy.deepcopy(snapshot["deck"])
            state["priority_queue"] = copy.deepcopy(snapshot["priority_queue"])
            state["played_cards"] = copy.deepcopy(snapshot["played_cards"])
            state["history"] = copy.deepcopy(snapshot["history"])
            
            # 再抽選
            results = []
            for _ in range(count):
                match = draw_match(state)
                results.append(match)
                
            state["last_results"] = results
            save_channel_state(channel_id, state)
            remaining = len(state.get("deck", [])) + len(state.get("priority_queue", []))
            
        msg = f"🔄 **引き直しました** (残データ: {remaining}/{len(FULL_DECK)})\n"
        for i, m in enumerate(results):
            msg += f"\n【第 {i+1} 試合】🗺️ **{m['map']}** |  ⚔️ **{m['rule']}**"
        
        await interaction.followup.send(msg)
        
    except Exception as e:
        print(f"Error in /redraw: {e}")
        await interaction.followup.send("❌ 処理中にエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)


@tree.command(name="reset", description="このチャンネルの山札をリセットして再シャッフルします")
async def reset(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if lock.locked():
        await interaction.response.send_message("⏳ 現在、別の要請を処理中です。少し待ってから再度お試しください。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            path = f"{DATA_DIR}/{channel_id}.json"
            if os.path.exists(path):
                os.remove(path)
                
        await interaction.followup.send("🔄 データインデックスをリフレッシュしました。このチャンネルの山札を再シャッフルします。")
        
    except Exception as e:
        print(f"Error in /reset: {e}")
        await interaction.followup.send("❌ 処理中にエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)


@tree.command(name="deck", description="現在のインデックスに残っているシミュレーションデータを表示します(運営用)")
async def deck(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if lock.locked():
        await interaction.response.send_message("⏳ 現在、別の要請を処理中です。少し待ってから再度お試しください。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            
        deck_cards = state.get("deck", [])
        pq_cards = state.get("priority_queue", [])
        
        # 初期状態チェック
        if not deck_cards and not pq_cards and not state.get("played_cards", []):
            deck_cards = FULL_DECK.copy()
            
        msg = f"🗂️ **シミュレーションデータ状況**\n"
        
        # 山札セクション
        msg += f"\n📚 **山札 ({len(deck_cards)}枚)**\n"
        if deck_cards:
            for c in sorted(deck_cards, key=lambda x: (x["map"], x["rule"])):
                msg += f"・🗺️ {c['map']} | ⚔️ {c['rule']}\n"
        else:
            msg += "なし\n"
            
        # 優先キューセクション
        msg += f"\n⏳ **優先キュー ({len(pq_cards)}枚)**\n"
        if pq_cards:
            for c in sorted(pq_cards, key=lambda x: (x["map"], x["rule"])):
                msg += f"・🗺️ {c['map']} | ⚔️ {c['rule']}\n"
        else:
            msg += "なし\n"
            
        await interaction.followup.send(msg)
        
    except Exception as e:
        print(f"Error in /deck: {e}")
        await interaction.followup.send("❌ 処理中にエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)


@tree.command(name="history", description="直近のシミュレーション履歴を表示します(運営用)")
async def history(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if lock.locked():
        await interaction.response.send_message("⏳ 現在、別の要請を処理中です。少し待ってから再度お試しください。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            
        history_list = state.get("history", [])
        
        if not history_list:
            msg = "📜 **直近のシミュレーション履歴**\n\n履歴がありません。"
        else:
            msg = f"📜 **直近 {len(history_list)} 試合の履歴**\n\n"
            for i, m in enumerate(history_list, 1):
                msg += f"{i}. 🗺️ **{m['map']}** | ⚔️ **{m['rule']}**\n"
                
        await interaction.followup.send(msg)
        
    except Exception as e:
        print(f"Error in /history: {e}")
        await interaction.followup.send("❌ 処理中にエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)


@tree.command(name="status", description="システムの内部状態(各デッキの残り枚数など)を確認します(運営用)")
async def status(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if lock.locked():
        await interaction.response.send_message("⏳ 現在、別の要請を処理中です。少し待ってから再度お試しください。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            
        deck_count = len(state.get("deck", []))
        pq_count = len(state.get("priority_queue", []))
        played_count = len(state.get("played_cards", []))
        
        if deck_count == 0 and pq_count == 0 and played_count == 0:
            deck_count = len(FULL_DECK)
            
        history_count = len(state.get("history", []))
        
        msg = "📊 **Guilty Spark 内部ステータス**\n\n"
        msg += f"📚 山札: **{deck_count}** 枚\n"
        msg += f"⏳ 優先キュー: **{pq_count}** 枚\n"
        msg += f"🗑️ トラッシュ(使用済み): **{played_count}** 枚\n\n"
        msg += f"📜 履歴保持数: **{history_count}** 試合\n"
        
        await interaction.followup.send(msg)
        
    except Exception as e:
        print(f"Error in /status: {e}")
        await interaction.followup.send("❌ 処理中にエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)


# --- Render用 ダミーWebサーバー ---
def run_dummy_server():
    class DummyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("I am the Monitor of Installation 04.".encode("utf-8"))
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()
    bot.run(TOKEN)