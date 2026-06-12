import os
import json
import random
import threading
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
            
    # 新しいデータ構造: 山札、優先キュー、使用済み、履歴
    return {
        "deck": [], 
        "priority_queue": [],
        "played_cards": [],
        "history": [], 
        "last_results": []
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

    # クールダウン対象の履歴（ルールとマップ、完全一致で長さを変える）
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
    # 優先キューも山札も全滅（クールダウンで引けない）した場合、捨て札を山札に補充
    if not selected:
        # 引けなかった山札の残りを優先キューに退避
        priority_queue.extend(deck)
        deck.clear()

        # 捨て札（すでに遊んだカード）を新しい山札としてシャッフル補充
        deck = played_cards.copy()
        random.shuffle(deck)
        played_cards.clear()

        # 補充した状態でもう一度 STEP 1 & 2 を試行
        selected = extract_valid_card(priority_queue)
        if not selected:
            selected = extract_valid_card(deck)

    # === STEP 4: 最終フォールバック（絶対安全装置） ===
    # 理論上ほぼ起きないが、補充してもクールダウンを満たせない場合の緊急措置
    if not selected:
        if priority_queue:
            selected = priority_queue.pop(0)
        elif deck:
            selected = deck.pop(0)
        else:
            deck = FULL_DECK.copy()
            random.shuffle(deck)
            selected = deck.pop(0)

    # === 状態の更新 ===
    played_cards.append(selected) # 遊んだカードとして記録
    history.append(selected)      # クールダウン履歴に追加
    
    # 履歴は最大でも必要なクールダウン値分あれば十分
    max_history_needed = max(MAP_COOLDOWN, RULE_COOLDOWN, EXACT_COOLDOWN)
    if len(history) > max_history_needed:
        history.pop(0)

    # stateに保存し直す
    state["deck"] = deck
    state["priority_queue"] = priority_queue
    state["played_cards"] = played_cards
    state["history"] = history

    return selected

@bot.event
async def on_ready():
    await tree.sync()
    # ボットのステータスに「〜をプレイ中」を設定してAIらしさを演出
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
    state = load_channel_state(channel_id)
    
    results = []
    for _ in range(count):
        match = draw_match(state)
        results.append(match)
        
    state["last_results"] = results
    save_channel_state(channel_id, state)
    
    # 残データは「通常の山札」+「優先キュー」の合計
    remaining = len(state.get("deck", [])) + len(state.get("priority_queue", []))
    
    msg = f"🛸 **343 Guilty Spark がシミュレーションを選択しました** (残データ: {remaining}/{len(FULL_DECK)})\n"
    for i, m in enumerate(results):
        msg += f"\n【第 {i+1} 試合】🗺️ **{m['map']}** |  ⚔️ **{m['rule']}**"
        
    await interaction.response.send_message(msg)

@tree.command(name="redraw", description="直前のシミュレーションを引き直します")
async def redraw(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    state = load_channel_state(channel_id)
    
    last_results = state.get("last_results", [])
    if not last_results:
        await interaction.response.send_message("❌ 引き直すための直前のシミュレーションデータが見つかりません。", ephemeral=True)
        return
        
    # 1. 直前の選出を「クールダウン履歴」から消去
    for match in reversed(last_results):
        if state["history"] and state["history"][-1] == match:
            state["history"].pop()
            
    # 2. 直前の選出を「遊んだカード(played_cards)」から消去し、山札に戻す
    for match in last_results:
        if match in state.get("played_cards", []):
            state["played_cards"].remove(match)
        state["deck"].append(match)
        
    # 山札をシャッフル
    random.shuffle(state["deck"])
    
    # 引き直し処理
    count = len(last_results)
    results = []
    for _ in range(count):
        match = draw_match(state)
        results.append(match)
        
    state["last_results"] = results
    save_channel_state(channel_id, state)
    
    remaining = len(state.get("deck", [])) + len(state.get("priority_queue", []))
    
    msg = f"🔄 **直前のシミュレーションを山札に戻し、引き直しました** (残データ: {remaining}/{len(FULL_DECK)})\n"
    for i, m in enumerate(results):
        msg += f"\n【第 {i+1} 試合】🗺️ **{m['map']}** |  ⚔️ **{m['rule']}**"
        
    await interaction.response.send_message(msg)

@tree.command(name="reset", description="このチャンネルの山札をリセットして再シャッフルします")
async def reset(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        os.remove(path)
    await interaction.response.send_message("🔄 データインデックスをリフレッシュしました。このチャンネルの山札を再シャッフルします。")

@tree.command(name="deck", description="現在のインデックスに残っているシミュレーションデータを表示します")
async def deck(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    state = load_channel_state(channel_id)
    
    # 残っているカード ＝ 通常の山札 ＋ 優先キュー
    current_cards = state.get("deck", []) + state.get("priority_queue", [])
    remaining = len(current_cards)
    
    if remaining == 0 and not state.get("played_cards", []):
        cards = FULL_DECK
        msg = f"🗂️ **現在のインデックスは初期状態です** (残データ: {len(FULL_DECK)}/{len(FULL_DECK)})\n\n"
    else:
        cards = current_cards
        msg = f"🗂️ **現在のインデックスに残存しているシミュレーションデータです** (残データ: {remaining}/{len(FULL_DECK)})\n\n"
    
    sorted_cards = sorted(cards, key=lambda c: (c["map"], c["rule"]))
    lines = []
    for card in sorted_cards:
        lines.append(f"・🗺️ **{card['map']}** | ⚔️ **{card['rule']}**")
        
    msg += "\n".join(lines)
    
    await interaction.response.send_message(msg)

# --- Render用 ダミーWebサーバー ---
def run_dummy_server():
    class DummyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("I am the Monitor of Installation 04. I am functioning normally.".encode("utf-8"))

        def log_message(self, format, *args):
            return

    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"🌐 ダミーWebサーバーをポート {port} で起動しました。")
    server.serve_forever()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()
    
    bot.run(TOKEN)