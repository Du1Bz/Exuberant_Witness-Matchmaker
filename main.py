import os
import json
import random
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
import discord
from discord.ext import commands
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# データ保存用のフォルダ作成
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# 競技マップ・ルールリスト
FULL_DECK = [
    {"map": "Aquarius",  "rule": "CTF_5cap"},
    {"map": "Empyrean",  "rule": "CTF_3cap"},
    {"map": "Fortress",  "rule": "CTF_3cap"},
    {"map": "Lattice",   "rule": "King of the Hill"},
    {"map": "Lattice",   "rule": "Oddball"},
    {"map": "Live Fire", "rule": "King of the Hill"},
    {"map": "Live Fire", "rule": "Oddball"},
    {"map": "Live Fire", "rule": "Slayer"},
    {"map": "Live Fire", "rule": "Strongholds"},
    {"map": "Origin",    "rule": "CTF_3cap"},
    {"map": "Origin",    "rule": "Slayer"},
    {"map": "Recharge",  "rule": "King of the Hill"},
    {"map": "Recharge",  "rule": "Oddball"},
    {"map": "Recharge",  "rule": "Slayer"},
    {"map": "Recharge",  "rule": "Strongholds"},
    {"map": "Solitude",  "rule": "King of the Hill"},
    {"map": "Solitude",  "rule": "Slayer"},
    {"map": "Streets",   "rule": "Oddball"},
    {"map": "Streets",   "rule": "Slayer"},
    {"map": "Vacancy",   "rule": "King of the Hill"},
    {"map": "Vacancy",   "rule": "Oddball"},
    {"map": "Vacancy",   "rule": "Slayer"}
]

COOLDOWN_SIZE = 5

# Botの初期設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 変更前：load_guild_state / save_guild_state
# 変更後：load_channel_state / save_channel_state にして、引数を channel_id に

def load_channel_state(channel_id):
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"deck": [], "history": []}

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
    print(f"🤖 {bot.user.name} がオンラインになりました！")

@bot.command()
async def next(ctx, count: int = 1):
    if count < 1 or count > 5:
        await ctx.send("💡 一度に要請できるのは 1〜5 試合までです。")
        return

    # ★ここを guild.id から channel.id に変更！
    channel_id = ctx.channel.id
    state = load_channel_state(channel_id)
    
    results = []
    for _ in range(count):
        match = draw_match(state)
        results.append(match)
        
    save_channel_state(channel_id, state)
    
    remaining = len(state["deck"]) if state["deck"] else len(FULL_DECK)
    
    msg = f"🛸 **343 Guilty Spark がシミュレーションを選択しました** (残データ: {remaining}/{len(FULL_DECK)})\n"
    for i, m in enumerate(results):
        msg += f"\n【第 {i+1} 試合】🗺️ **{m['map']}** |  ⚔️ **{m['rule']}**"
        
    await ctx.send(msg)

@bot.command()
async def reset(ctx):
    # ★ここも guild.id から channel.id に変更！
    channel_id = ctx.channel.id
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        os.remove(path)
    await ctx.send("🔄 データインデックスをリフレッシュしました。このチャンネルの山札を再シャッフルします。")

# --- Render用 ダミーWebサーバー ---
def run_dummy_server():
    class DummyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("I am the Monitor of Installation 04. I am functioning normally.".encode("utf-8"))

        # ログがターミナルを埋め尽くさないようにミュート
        def log_message(self, format, *args):
            return

    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"🌐 ダミーWebサーバーをポート {port} で起動しました。")
    server.serve_forever()

if __name__ == "__main__":
    # Webサーバーを別スレッドでバックグラウンド起動
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()
    
    # Discord Botの起動
    bot.run(TOKEN)