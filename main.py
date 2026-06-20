import os
import json
import random
import threading
import copy
import asyncio
import tempfile
from datetime import datetime, timezone, timedelta
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

# === プレイリスト表示名 ===
PL_NAMES = {
    "ranked_arena": "Ranked Arena",
    "ga": "GA(Gentleman's Agreement)"
}

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
# ヘルパー関数
# =============================================================================

def get_jst_time_str(iso_str: str, locale: discord.Locale) -> str:
    if not iso_str:
        return t(locale, "never_played")
    try:
        dt = datetime.fromisoformat(iso_str)
        jst = dt.astimezone(timezone(timedelta(hours=9)))
        return jst.strftime("%Y/%m/%d %H:%M")
    except:
        return t(locale, "never_played")

def get_excluded_slayer_count(settings: dict, cards: list) -> int:
    active_slayer_count = settings.get("active_slayer_count")
    if active_slayer_count is None:
        return 0
    all_slayers = sum(1 for c in cards if c["rule"] == "Slayer")
    return max(0, all_slayers - active_slayer_count)

def get_total_active_cards(settings: dict, cards: list) -> int:
    return len(cards) - get_excluded_slayer_count(settings, cards)


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

def get_initial_playlist_state() -> dict:
    return {
        "deck":           [],
        "priority_queue": [],
        "played_cards":   [],
        "history":        [],
        "slayer_pool":    [],
        "snapshots":      [],
        "snapshot_counter": 0,
        "last_results":   [],
        "last_played_at": None,
    }

def load_channel_state(channel_id: int) -> dict:
    path = f"{DATA_DIR}/{channel_id}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        
        # 古いデータ構造（playlistsキーを持たない単一デッキ構造）はリセットして作り直す
        if "playlists" not in state:
            state = {
                "current_playlist": "ranked_arena",
                "playlists": {}
            }
    else:
        state = {
            "current_playlist": "ranked_arena",
            "playlists": {}
        }
    
    # 欠落しているプレイリストがあれば初期状態を埋める
    for pl_key in FULL_DECK.keys():
        if pl_key not in state["playlists"]:
            state["playlists"][pl_key] = get_initial_playlist_state()
            
    return state

def save_channel_state(channel_id: int, state: dict) -> None:
    path = f"{DATA_DIR}/{channel_id}.json"
    dir_ = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False,
                                    suffix=".tmp", encoding="utf-8") as tmp:
        json.dump(state, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, path)

def create_snapshot(pl_state: dict) -> int:
    """現在の状態のスナップショットを作成し、そのIDを返す"""
    pl_state["snapshot_counter"] = pl_state.get("snapshot_counter", 0) + 1
    snap_id = pl_state["snapshot_counter"]
    
    snap_data = {
        "deck":           copy.deepcopy(pl_state.get("deck", [])),
        "priority_queue": copy.deepcopy(pl_state.get("priority_queue", [])),
        "played_cards":   copy.deepcopy(pl_state.get("played_cards", [])),
        "history":        copy.deepcopy(pl_state.get("history", [])),
        "slayer_pool":    copy.deepcopy(pl_state.get("slayer_pool", [])),
    }
    
    snapshots = pl_state.get("snapshots", [])
    snapshots.append({"id": snap_id, "state": snap_data})
    
    # 直近50件を保持
    if len(snapshots) > 50:
        snapshots.pop(0)
        
    pl_state["snapshots"] = snapshots
    return snap_id

def restore_snapshot(pl_state: dict, snap_state: dict) -> None:
    """スナップショットの状態を復元し、山札をシャッフルする"""
    pl_state["deck"]           = copy.deepcopy(snap_state["deck"])
    pl_state["priority_queue"] = copy.deepcopy(snap_state["priority_queue"])
    pl_state["played_cards"]   = copy.deepcopy(snap_state["played_cards"])
    pl_state["history"]        = copy.deepcopy(snap_state["history"])
    pl_state["slayer_pool"]    = copy.deepcopy(snap_state["slayer_pool"])
    random.shuffle(pl_state["deck"])

def backto_snapshot(pl_state: dict, snapshot_id: int) -> bool:
    """指定ID自体に紐づくスナップショット（=そのIDの抽選が起こる直前の状態）へ復元する。
    /redraw が「直前の抽選を取り消して引き直す」ために使う低レベル処理。"""
    target_snapshot = next((s for s in pl_state.get("snapshots", []) if s["id"] == snapshot_id), None)
    if not target_snapshot:
        return False

    restore_snapshot(pl_state, target_snapshot["state"])

    # 指定ID以降の未来のスナップショットを破棄
    pl_state["snapshots"] = [s for s in pl_state["snapshots"] if s["id"] <= snapshot_id]
    return True

def backto_user_id(pl_state: dict, user_id: int) -> str:
    """/backto コマンド用：ユーザーが見ているID（=そのIDの抽選結果が表示された直後の状態）へ戻る。
    データ上は「user_id+1」のスナップショット（=次の抽選の直前の状態）と同じ内容になる。
    戻り値: "restored"（巻き戻した） / "already_current"（既にその状態） / "not_found"（無効なID）"""
    snapshots = pl_state.get("snapshots", [])

    if not any(s["id"] == user_id for s in snapshots):
        return "not_found"

    next_id = user_id + 1
    if any(s["id"] == next_id for s in snapshots):
        backto_snapshot(pl_state, next_id)
        return "restored"
    else:
        # user_id が現在の最新の抽選＝既にその直後の状態にいる（変更不要）
        pl_state["snapshots"] = [s for s in snapshots if s["id"] <= user_id]
        return "already_current"


# =============================================================================
# カード抽選ロジック
# =============================================================================

def get_base_rule(rule_name: str) -> str:
    return "CTF" if rule_name.startswith("CTF") else rule_name

def is_rule_on_cooldown(card: dict, recent_history: list) -> bool:
    card_base = get_base_rule(card["rule"])
    return any(card_base == get_base_rule(h["rule"]) for h in recent_history)

def is_map_on_cooldown(card: dict, recent_history: list) -> bool:
    return any(card["map"] == h["map"] for h in recent_history)

def is_exact_on_cooldown(card: dict, recent_history: list) -> bool:
    return any(card["map"] == h["map"] and card["rule"] == h["rule"]
               for h in recent_history)

def get_cooldown_remaining(card: dict, history: list, settings: dict) -> tuple[int, int, int]:
    map_rem = 0
    rule_rem = 0
    exact_rem = 0
    card_rule_base = get_base_rule(card["rule"])

    map_cd = settings.get("map_cooldown") or 0
    rule_cd = settings.get("rule_cooldown") or 0
    exact_cd = settings.get("exact_cooldown") or 0

    for i, h in enumerate(reversed(history), 1):
        if map_rem == 0 and card["map"] == h["map"]:
            map_rem = max(0, map_cd - i + 1)
        if rule_rem == 0 and card_rule_base == get_base_rule(h["rule"]):
            rule_rem = max(0, rule_cd - i + 1)
        if exact_rem == 0 and card["map"] == h["map"] and card["rule"] == h["rule"]:
            exact_rem = max(0, exact_cd - i + 1)
        if map_rem > 0 and rule_rem > 0 and exact_rem > 0:
            break
    return map_rem, rule_rem, exact_rem

def draw_match(pl_state: dict, settings: dict, all_cards: list) -> dict:
    deck           = pl_state.get("deck", [])
    priority_queue = pl_state.get("priority_queue", [])
    played_cards   = pl_state.get("played_cards", [])
    history        = pl_state.get("history", [])
    slayer_pool    = pl_state.get("slayer_pool", [])

    rule_cd = settings.get("rule_cooldown")
    map_cd  = settings.get("map_cooldown")
    exact_cd= settings.get("exact_cooldown")
    active_slayer_count = settings.get("active_slayer_count")

    # 初期化: すべて空っぽなら新品の山札を作る
    if not deck and not priority_queue and not played_cards:
        all_slayers = [c for c in all_cards if c["rule"] == "Slayer"]
        random.shuffle(all_slayers)
        
        if active_slayer_count is not None:
            chosen_slayers = all_slayers[:active_slayer_count]
            slayer_pool    = all_slayers[active_slayer_count:]
        else:
            chosen_slayers = all_slayers
            slayer_pool    = []

        all_objectives = [c for c in all_cards if c["rule"] != "Slayer"]
        deck = all_objectives + chosen_slayers
        random.shuffle(deck)

    # クールダウン対象の履歴スライス
    rule_recent  = history[-rule_cd:] if rule_cd else []
    map_recent   = history[-map_cd:] if map_cd else []
    exact_recent = history[-exact_cd:] if exact_cd else []

    def extract_valid_card(card_list: list) -> dict | None:
        valid_idx = next(
            (i for i, card in enumerate(card_list)
             if not (map_cd and is_map_on_cooldown(card, map_recent))
             and not (rule_cd and is_rule_on_cooldown(card, rule_recent))
             and not (exact_cd and is_exact_on_cooldown(card, exact_recent))),
            None
        )
        if valid_idx is not None:
            return card_list.pop(valid_idx)
        return None

    # === STEP 1 & 2: 優先キューまたは山札から引く ===
    selected = extract_valid_card(priority_queue) or extract_valid_card(deck)

    # === STEP 3: 詰み（補充タイミング）の処理 ===
    if not selected:
        priority_queue.extend(deck)
        deck.clear()
        
        recycled_objectives = [c for c in played_cards if c["rule"] != "Slayer"]
        played_slayers      = [c for c in played_cards if c["rule"] == "Slayer"]
        
        if active_slayer_count is not None:
            pq_slayer_count = sum(1 for c in priority_queue if c["rule"] == "Slayer")
            needed_slayer_count = max(0, active_slayer_count - pq_slayer_count)
            slayer_candidates = list(slayer_pool) + list(played_slayers)
            chosen_slayers = slayer_candidates[:needed_slayer_count]
            slayer_pool    = slayer_candidates[needed_slayer_count:]
        else:
            chosen_slayers = list(slayer_pool) + list(played_slayers)
            slayer_pool = []
        
        deck = recycled_objectives + chosen_slayers
        random.shuffle(deck)
        played_cards.clear()

        selected = extract_valid_card(priority_queue) or extract_valid_card(deck)

    # === STEP 4: クールダウンを段階的に緩めて再試行 ===
    if not selected:
        max_cd = max([cd for cd in (rule_cd, map_cd, exact_cd) if cd is not None] or [0])
        for relax in range(1, max_cd + 1):
            rr = [] if not rule_cd or rule_cd <= relax else history[-(rule_cd - relax):]
            mr = [] if not map_cd or map_cd <= relax else history[-(map_cd - relax):]
            er = [] if not exact_cd or exact_cd <= relax else history[-(exact_cd - relax):]

            def is_valid_relaxed(card):
                return not (map_cd and is_map_on_cooldown(card, mr)) \
                   and not (rule_cd and is_rule_on_cooldown(card, rr)) \
                   and not (exact_cd and is_exact_on_cooldown(card, er))

            valid_idx = next((i for i, c in enumerate(priority_queue) if is_valid_relaxed(c)), None)
            if valid_idx is not None:
                selected = priority_queue.pop(valid_idx)
                break

            valid_idx = next((i for i, c in enumerate(deck) if is_valid_relaxed(c)), None)
            if valid_idx is not None:
                selected = deck.pop(valid_idx)
                break

    # === STEP 5: 最終フォールバック ===
    if not selected:
        selected = priority_queue.pop(0) if priority_queue else deck.pop(0)

    # 履歴とトラッシュへ格納
    played_cards.append(selected)
    history.append(selected)

    max_history = max([cd for cd in (rule_cd, map_cd, exact_cd) if cd is not None] or [0])
    keep_len = max(max_history, 15) # 表示用にある程度履歴を残す
    if len(history) > keep_len:
        history.pop(0)

    pl_state.update({
        "deck": deck,
        "priority_queue": priority_queue,
        "played_cards": played_cards,
        "history": history,
        "slayer_pool": slayer_pool
    })

    return selected


# =============================================================================
# 共通ヘルパー
# =============================================================================

async def _check_busy(interaction: discord.Interaction, lock: asyncio.Lock) -> bool:
    if lock.locked():
        await interaction.response.send_message(
            t(interaction.locale, "err_busy"), ephemeral=True
        )
        return True
    return False


# =============================================================================
# UI View クラス (/start用)
# =============================================================================

class StartView(discord.ui.View):
    def __init__(self, channel_id: int, locale: discord.Locale):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.locale = locale
        self.add_item(PlaylistButton("ranked_arena", t(locale, "btn_ranked"), discord.ButtonStyle.primary))
        self.add_item(PlaylistButton("ga", t(locale, "btn_ga"), discord.ButtonStyle.success))
        self.add_item(CancelButton(t(locale, "btn_cancel")))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if hasattr(self, 'message'):
                await self.message.edit(content=t(self.locale, "start_timeout"), view=self)
        except Exception as e:
            print(f"Error in StartView.on_timeout: {e}")

class PlaylistButton(discord.ui.Button):
    def __init__(self, pl_id: str, label: str, style: discord.ButtonStyle):
        super().__init__(style=style, label=label, custom_id=f"pl_{pl_id}")
        self.pl_id = pl_id

    async def callback(self, interaction: discord.Interaction):
        view: StartView = self.view
        locale = view.locale
        channel_id = view.channel_id
        lock = get_channel_lock(channel_id)

        if await _check_busy(interaction, lock):
            return

        async with lock:
            state = load_channel_state(channel_id)
            pl_state = state["playlists"][self.pl_id]

            last_played = get_jst_time_str(pl_state.get("last_played_at"), locale)
            remaining = len(pl_state.get("deck", [])) + len(pl_state.get("priority_queue", []))

            if remaining == 0 and not pl_state.get("played_cards", []):
                settings = FULL_DECK[self.pl_id]["settings"]
                cards = FULL_DECK[self.pl_id]["cards"]
                remaining = get_total_active_cards(settings, cards)

        pl_name_display = PL_NAMES.get(self.pl_id, self.label)
        msg = t(locale, "start_save_info", pl_name=pl_name_display, last_played=last_played, remaining=remaining)

        view.stop()
        next_view = ActionView(channel_id, self.pl_id, locale)
        await interaction.response.edit_message(content=msg, view=next_view)
        next_view.message = interaction.message

class ActionView(discord.ui.View):
    def __init__(self, channel_id: int, pl_id: str, locale: discord.Locale):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.pl_id = pl_id
        self.locale = locale
        
        self.add_item(ResumeButton(t(locale, "btn_resume")))
        self.add_item(ResetButton(t(locale, "btn_reset")))
        self.add_item(CancelButton(t(locale, "btn_cancel")))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if hasattr(self, 'message'):
                await self.message.edit(content=t(self.locale, "start_timeout"), view=self)
        except Exception as e:
            print(f"Error in ActionView.on_timeout: {e}")

class ResumeButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label)

    async def callback(self, interaction: discord.Interaction):
        view: ActionView = self.view
        channel_id = view.channel_id
        lock = get_channel_lock(channel_id)

        if await _check_busy(interaction, lock):
            return

        view.stop()
        async with lock:
            state = load_channel_state(channel_id)
            state["current_playlist"] = view.pl_id
            save_channel_state(channel_id, state)

        await interaction.response.edit_message(content=t(view.locale, "start_resumed"), view=None)

class ResetButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.danger, label=label)

    async def callback(self, interaction: discord.Interaction):
        view: ActionView = self.view
        channel_id = view.channel_id
        lock = get_channel_lock(channel_id)

        if await _check_busy(interaction, lock):
            return

        view.stop()
        async with lock:
            state = load_channel_state(channel_id)
            state["current_playlist"] = view.pl_id
            pl_state = state["playlists"][view.pl_id]

            # デッキ・履歴を初期化（スナップショットは保持）
            pl_state["deck"] = []
            pl_state["priority_queue"] = []
            pl_state["played_cards"] = []
            pl_state["history"] = []
            pl_state["slayer_pool"] = []
            pl_state["last_results"] = []

            save_channel_state(channel_id, state)

        await interaction.response.edit_message(content=t(view.locale, "start_reset_done"), view=None)

class CancelButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.stop()
        await interaction.response.edit_message(content=t(view.locale, "start_canceled"), view=None)


# =============================================================================
# Bot イベント
# =============================================================================

@bot.event
async def on_ready():
    await tree.set_translator(GuiltySparkTranslator())
    await tree.sync()
    
    activity_name = t(discord.Locale.american_english, "activity")
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name=activity_name),
    )
    print(t(discord.Locale.japanese, "on_ready_log", name=bot.user.name))


# =============================================================================
# スラッシュコマンド
# =============================================================================

@tree.command(name="start", description=app_commands.locale_str("start"))
async def cmd_start(interaction: discord.Interaction):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    view = StartView(channel_id, locale)
    await interaction.response.send_message(t(locale, "start_prompt"), view=view, ephemeral=False)
    view.message = await interaction.original_response()


@tree.command(name="next", description=app_commands.locale_str("next"))
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
            current_pl = state.get("current_playlist", "ranked_arena")
            pl_state = state["playlists"][current_pl]
            settings = FULL_DECK[current_pl]["settings"]
            cards = FULL_DECK[current_pl]["cards"]

            snap_id = create_snapshot(pl_state)
            
            results = [draw_match(pl_state, settings, cards) for _ in range(count)]
            pl_state["last_results"] = results
            pl_state["last_played_at"] = datetime.now(timezone.utc).isoformat()
            
            save_channel_state(channel_id, state)
            
            total_active_cards = get_total_active_cards(settings, cards)
            remaining = len(pl_state.get("deck", [])) + len(pl_state.get("priority_queue", []))

            pl_name = PL_NAMES.get(current_pl, current_pl)
            msg = t(locale, "next_header", pl_name=pl_name, id=snap_id, remaining=remaining, total=total_active_cards)
            for i, m in enumerate(results, 1):
                msg += t(locale, "match_line", i=i, map=m["map"], rule=m["rule"])

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /next: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(name="backto", description=app_commands.locale_str("backto"))
@app_commands.describe(snapshot_id=app_commands.locale_str("backto.id"))
async def cmd_backto(interaction: discord.Interaction, snapshot_id: int):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            current_pl = state.get("current_playlist", "ranked_arena")
            pl_state = state["playlists"][current_pl]

            result = backto_user_id(pl_state, snapshot_id)

            if result == "not_found":
                await interaction.followup.send(t(locale, "err_invalid_snapshot"), ephemeral=True)
                return

            save_channel_state(channel_id, state)

            settings = FULL_DECK[current_pl]["settings"]
            cards = FULL_DECK[current_pl]["cards"]
            total_active_cards = get_total_active_cards(settings, cards)
            remaining = len(pl_state.get("deck", [])) + len(pl_state.get("priority_queue", []))

            if result == "already_current":
                msg = t(locale, "backto_already_current", id=snapshot_id)
            else:
                msg = t(locale, "backto_success", id=snapshot_id, remaining=remaining, total=total_active_cards)
        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /backto: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(name="redraw", description=app_commands.locale_str("redraw"))
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
            current_pl = state.get("current_playlist", "ranked_arena")
            pl_state = state["playlists"][current_pl]
            snapshots = pl_state.get("snapshots", [])
            last_results = pl_state.get("last_results", [])

            if not snapshots:
                await interaction.followup.send(t(locale, "err_no_snapshot"), ephemeral=True)
                return
            if not last_results:
                await interaction.followup.send(t(locale, "err_no_last_results"), ephemeral=True)
                return

            target_snapshot = snapshots[-1]
            snap_id = target_snapshot["id"]
            # /redraw は「最新スナップショットへのbacktoした上で再抽選する」処理として、
            # /backto と共通の復元処理(backto_snapshot)を利用する
            backto_snapshot(pl_state, snap_id)

            settings = FULL_DECK[current_pl]["settings"]
            cards = FULL_DECK[current_pl]["cards"]
            results = [draw_match(pl_state, settings, cards) for _ in range(len(last_results))]
            
            pl_state["last_results"] = results
            pl_state["last_played_at"] = datetime.now(timezone.utc).isoformat()
            
            save_channel_state(channel_id, state)
            
            total_active_cards = get_total_active_cards(settings, cards)
            remaining = len(pl_state.get("deck", [])) + len(pl_state.get("priority_queue", []))
            
            pl_name = PL_NAMES.get(current_pl, current_pl)
            msg = t(locale, "redraw_header", pl_name=pl_name, id=snap_id, remaining=remaining, total=total_active_cards)
            for i, m in enumerate(results, 1):
                msg += t(locale, "match_line", i=i, map=m["map"], rule=m["rule"])

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /redraw: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(name="reset", description=app_commands.locale_str("reset"))
async def cmd_reset(interaction: discord.Interaction):
    locale = interaction.locale
    channel_id = interaction.channel_id
    lock = get_channel_lock(channel_id)

    if await _check_busy(interaction, lock):
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with lock:
            state = load_channel_state(channel_id)
            current_pl = state.get("current_playlist", "ranked_arena")
            pl_state = state["playlists"][current_pl]
            
            pl_state["deck"] = []
            pl_state["priority_queue"] = []
            pl_state["played_cards"] = []
            pl_state["history"] = []
            pl_state["slayer_pool"] = []
            pl_state["last_results"] = []
            
            save_channel_state(channel_id, state)

            pl_name = PL_NAMES.get(current_pl, current_pl)
        await interaction.followup.send(t(locale, "reset_done", pl_name=pl_name))

    except Exception as e:
        print(f"Error in /reset: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(name="deck", description=app_commands.locale_str("deck"))
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
            current_pl = state.get("current_playlist", "ranked_arena")
            pl_state = state["playlists"][current_pl]
            settings = FULL_DECK[current_pl]["settings"]
            cards = FULL_DECK[current_pl]["cards"]

            deck_cards  = pl_state.get("deck", [])
            pq_cards    = pl_state.get("priority_queue", [])
            slayer_pool = pl_state.get("slayer_pool", [])

            # 初期状態
            if not deck_cards and not pq_cards and not pl_state.get("played_cards", []):
                all_slayers = [c for c in cards if c["rule"] == "Slayer"]
                random.shuffle(all_slayers)
                active_slayer_count = settings.get("active_slayer_count")
                
                if active_slayer_count is not None:
                    deck_cards = [c for c in cards if c["rule"] != "Slayer"] + all_slayers[:active_slayer_count]
                    slayer_pool = all_slayers[active_slayer_count:]
                else:
                    deck_cards = [c for c in cards if c["rule"] != "Slayer"] + all_slayers
                    slayer_pool = []

            history = pl_state.get("history", [])
            pl_name = PL_NAMES.get(current_pl, current_pl)
            
            msg  = t(locale, "deck_header", pl_name=pl_name) + "\n"
            msg += t(locale, "deck_section", count=len(deck_cards))
            if deck_cards:
                for c in sorted(deck_cards, key=lambda x: (x["map"], x["rule"])):
                    if history:
                        m, r, e = get_cooldown_remaining(c, history, settings)
                        cd = f" (🚫🗺️{m} ⚔️{r} 🔁{e})" if m > 0 or r > 0 or e > 0 else " ✅"
                    else:
                        cd = ""
                    msg += f"・🗺️ {c['map']} | ⚔️ {c['rule']}{cd}\n"
            else:
                msg += t(locale, "none")

            msg += t(locale, "pq_section", count=len(pq_cards))
            if pq_cards:
                for c in sorted(pq_cards, key=lambda x: (x["map"], x["rule"])):
                    if history:
                        m, r, e = get_cooldown_remaining(c, history, settings)
                        cd = f" (🚫🗺️{m} ⚔️{r} 🔁{e})" if m > 0 or r > 0 or e > 0 else " ✅"
                    else:
                        cd = ""
                    msg += f"・🗺️ {c['map']} | ⚔️ {c['rule']}{cd}\n"
            else:
                msg += t(locale, "none")
                
            msg += t(locale, "deck_excluded", count=len(slayer_pool))
            if slayer_pool:
                for c in sorted(slayer_pool, key=lambda x: (x["map"], x["rule"])):
                    msg += f"・🗺️ {c['map']} | ⚔️ {c['rule']}\n"
            else:
                msg += t(locale, "none")

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /deck: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(name="history", description=app_commands.locale_str("history"))
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
            current_pl = state.get("current_playlist", "ranked_arena")
            pl_state = state["playlists"][current_pl]
            history_list = pl_state.get("history", [])
            pl_name = PL_NAMES.get(current_pl, current_pl)

            if not history_list:
                msg = t(locale, "history_empty", pl_name=pl_name)
            else:
                msg = t(locale, "history_header", count=len(history_list), pl_name=pl_name)
                for i, m in enumerate(history_list, 1):
                    msg += f"{i}. 🗺️ **{m['map']}** | ⚔️ **{m['rule']}**\n"

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"Error in /history: {e}")
        await interaction.followup.send(t(locale, "err_generic"), ephemeral=True)


@tree.command(name="status", description=app_commands.locale_str("status"))
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
            current_pl = state.get("current_playlist", "ranked_arena")
            pl_state = state["playlists"][current_pl]
            settings = FULL_DECK[current_pl]["settings"]
            cards = FULL_DECK[current_pl]["cards"]

            deck_count   = len(pl_state.get("deck", []))
            pq_count     = len(pl_state.get("priority_queue", []))
            played_count = len(pl_state.get("played_cards", []))
            excluded_count = len(pl_state.get("slayer_pool", []))

            if deck_count == 0 and pq_count == 0 and played_count == 0:
                excluded_count = get_excluded_slayer_count(settings, cards)
                deck_count = len(cards) - excluded_count

            history_count = len(pl_state.get("history", []))
            snap_count = len(pl_state.get("snapshots", []))
            pl_name = PL_NAMES.get(current_pl, current_pl)

            msg  = t(locale, "status_header", pl_name=pl_name)
            msg += t(locale, "status_deck",    count=deck_count)
            msg += t(locale, "status_pq",      count=pq_count)
            msg += t(locale, "status_trash",   count=played_count)
            msg += t(locale, "status_excluded",count=excluded_count)
            msg += t(locale, "status_history", count=history_count)
            msg += t(locale, "status_snapshots", count=snap_count)

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
            pass

    port = int(os.getenv("PORT", 10000))
    HTTPServer(("0.0.0.0", port), DummyHandler).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    bot.run(TOKEN)