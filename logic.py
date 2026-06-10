import json
import random
import os

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

STATE_FILE = "bot_state.json"
COOLDOWN_SIZE = 5

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"deck": [], "history": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def draw_match():
    state = load_state()
    deck = state["deck"]
    history = state["history"]

    if len(deck) == 0:
        deck = FULL_DECK.copy()
        random.shuffle(deck)

    selected = None
    temp_drawn = []
    
    # 直近の試合データを取得（連続防止チェック用）
    last_match = history[-1] if len(history) > 0 else None

    # 山札から条件に合うものを探す
    while len(deck) > 0:
        card = deck.pop(0)
        
        # 連続ルールの判定用（CTF_3cap と CTF_5cap は同じ「CTF」として扱う）
        card_rule_base = card["rule"].split('_')[0]
        last_rule_base = last_match["rule"].split('_')[0] if last_match else None
        
        # 3つの禁止条件
        is_recent_combo = card in history # 直近5試合でやった完全一致カブり
        is_same_map = last_match and (card["map"] == last_match["map"]) # マップ2連続
        is_same_rule = last_rule_base and (card_rule_base == last_rule_base) # ルール2連続
        
        # すべてのフィルターをクリアしたら採用
        if not is_recent_combo and not is_same_map and not is_same_rule:
            selected = card
            break
        else:
            temp_drawn.append(card)

    # 厳格なチェックで山札が全滅した場合（山札の残りがSlayerしかない時などの救済措置）
    if not selected:
        for i, card in enumerate(temp_drawn):
            if card not in history: # せめて直近5試合の完全カブりだけは避ける
                selected = temp_drawn.pop(i)
                break
                
    # それでもダメならランダムフォールバック（通常は発生しない）
    if not selected:
        selected = random.choice(FULL_DECK)
        if selected in temp_drawn:
            temp_drawn.remove(selected)

    # 引かなかったカードを山札の底に戻す
    deck.extend(temp_drawn)

    # 履歴を更新
    history.append(selected)
    if len(history) > COOLDOWN_SIZE:
        history.pop(0)

    state["deck"] = deck
    state["history"] = history
    save_state(state)

    return selected

if __name__ == "__main__":
    print("🎲 ランダム選出のテスト（連続防止Ver）を開始します 🎲\n")
    # テスト開始前に古い状態をリセットする
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        
    for i in range(22):
        match = draw_match()
        print(f"[{i+1}試合目] 🗺️ {match['map']} / ⚔️ {match['rule']}")