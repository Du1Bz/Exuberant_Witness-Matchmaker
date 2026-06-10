import os
import json
import random
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
import discord
from discord import app_commands
from discord.ext import commands
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

COOLDOWN_SIZE = 5

# Botの初期設定（スラッシュコマンド専用）
intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)

# チャンネルごとにデータを読み書き
def load_channel_state(channel_id):
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"deck": [], "history": [], "last_results": []}

def save_channel_state(channel_id, state):
    path = f"{DATA_DIR}/{channel_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def draw_match(state):
    deck = state["deck"]
    history = state["history"]

    if len(deck) == 0:
        deck = FULL_DECK.copy()
        random.shuffle(deck)

    selected = None
    temp_drawn = []
    last_match = history[-1] if len(history) > 0 else None

    while len(deck) > 0:
        card = deck.pop(0)
        card_rule_base = card["rule"].split('_')[0]
        last_rule_base = last_match["rule"].split('_')[0] if last_match else None
        
        is_recent_combo = card in history
        is_same_map = last_match and (card["map"] == last_match["map"])
        is_same_rule = last_rule_base and (card_rule_base == last_rule_base)
        
        if not is_recent_combo and not is_same_map and not is_same_rule:
            selected = card
            break
        else:
            temp_drawn.append(card)

    if not selected:
        for i, card in enumerate(temp_drawn):
            if card not in history:
                selected = temp_drawn.pop(i)
                break
                
    if not selected:
        selected = random.choice(FULL_DECK)
        if selected in temp_drawn:
            temp_drawn.remove(selected)

    deck.extend(temp_drawn)
    history.append(selected)
    if len(history) > COOLDOWN_SIZE:
        history.pop(0)

    state["deck"] = deck
    state["history"] = history
    return selected

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"🤖 {bot.user.name} がオンラインになりました！")

@bot.tree.command(name="next", description="シミュレーションを選択します")
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
        
    # 直前の選出結果を記録しておく
    state["last_results"] = results
    save_channel_state(channel_id, state)
    
    remaining = len(state["deck"]) if state["deck"] else len(FULL_DECK)
    
    msg = f"🛸 **343 Guilty Spark がシミュレーションを選択しました** (残データ: {remaining}/{len(FULL_DECK)})\n"
    for i, m in enumerate(results):
        msg += f"\n【第 {i+1} 試合】🗺️ **{m['map']}** |  ⚔️ **{m['rule']}**"
        
    await interaction.response.send_message(msg)

@bot.tree.command(name="redraw", description="直前のシミュレーションを引き直します")
async def redraw(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    state = load_channel_state(channel_id)
    
    # 直前のデータがあるか確認
    last_results = state.get("last_results", [])
    if not last_results:
        await interaction.response.send_message("❌ 引き直すための直前のシミュレーションデータが見つかりません。", ephemeral=True)
        return
        
    # 1. 直前の選出を「最近の履歴(history)」から消去（引き直しの判定で弾かれないようにするため）
    for match in last_results:
        if match in state["history"]:
            state["history"].remove(match)
            
    # 2. 直前の選出を山札(deck)に戻す
    if state["deck"] is None:
        state["deck"] = []
    for match in last_results:
        state["deck"].append(match)
        
    # 3. 山札を再シャッフル
    random.shuffle(state["deck"])
    
    # 4. 直前と同じ件数分を、新しく引き直す
    count = len(last_results)
    results = []
    for _ in range(count):
        match = draw_match(state)
        results.append(match)
        
    # 今回引き直した結果を新しく「直前の結果」として上書き保存
    state["last_results"] = results
    save_channel_state(channel_id, state)
    
    remaining = len(state["deck"]) if state["deck"] else len(FULL_DECK)
    
    msg = f"🔄 **直前のシミュレーションを山札に戻し、引き直しました** (残データ: {remaining}/{len(FULL_DECK)})\n"
    for i, m in enumerate(results):
        msg += f"\n【第 {i+1} 試合】🗺️ **{m['map']}** |  ⚔️ **{m['rule']}**"
        
    await interaction.response.send_message(msg)

@bot.tree.command(name="reset", description="このチャンネルの山札をリセットして再シャッフルします")
async def reset(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        os.remove(path)
    await interaction.response.send_message("🔄 データインデックスをリフレッシュしました。このチャンネルの山札を再シャッフルします。")

@bot.tree.command(name="deck", description="現在のインデックスに残っているシミュレーションデータを表示します")
async def deck(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    state = load_channel_state(channel_id)
    
    current_deck = state.get("deck", [])
    
    # 山札が空（初期状態、または引ききった直後）の場合は全カードとみなす
    if not current_deck:
        cards = FULL_DECK
        msg = f"🗂️ **現在のインデックスは初期状態です** (残データ: {len(FULL_DECK)}/{len(FULL_DECK)})\n\n"
    else:
        cards = current_deck
        msg = f"🗂️ **現在のインデックスに残存しているシミュレーションデータです (残データ: {len(current_deck)}/{len(FULL_DECK)})\n\n"
    
    # マップ名→ルール名のアルファベット順にソートして一覧表示
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