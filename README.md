# Exuberant Witness - Matchmaker — Halo Infinite Custom Match Selector

A Discord Bot that randomly selects map & rule combinations for Halo Infinite ranked arena custom matches using a deck system.

> 日本語版は [README_ja.md](README_ja.md) をご覧ください。

---

## What It Does



https://github.com/user-attachments/assets/d5ab6c15-4fb0-4392-ba98-db9dc3cc7c1e



Exuberant Witness shuffles map & rule combinations into a deck and draws from the top. Instead of pure RNG, it uses a smart algorithm to prevent repetitive matches.

- **Cooldown logic** prevents back-to-back duplicates: same map (last 4 matches), same rule type (last 3 matches), and exact same combination (last 7 matches) are automatically blocked.
- **Adjustable Slayer rate**: Only 4 out of 6 Slayers are kept active to reduce their appearance rate (tuned from launch based on community feedback). When selected, all active Slayers have equal probability with no bias.
- **Priority Queue System**: If all remaining cards in the deck are blocked by cooldowns (a dead end), they are temporarily moved to the Priority Queue. The trash pile is then reshuffled into a new deck to keep the games rolling. Cards in the Priority Queue will be drawn first as soon as their cooldowns expire.
- **Gradual Relaxation Fallback**: If no valid card is found even after a deck reset, cooldowns are gradually relaxed one match at a time and retried. This ensures that forced picks (violating cooldowns) effectively never occur.
- **Playlist System** (`/start`): Choose between **Ranked Arena** and **GA (Gentleman's Agreement)** playlists. Each playlist has its own separate deck, cooldown settings, and snapshot history. Use `/start` to select or switch playlists.
- **Per-channel decks** allow multiple custom lobbies to run simultaneously without interfering with each other.
- Available 24/7 with instant responses.

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Start a custom match — select a playlist (Ranked Arena / GA), then choose to resume from save or reset. |
| `/next` | Draw the next match combination (remaining count shown). |
| `/next count:3` | Draw multiple combinations at once (1–5). |
| `/redraw` | Return the previous draw to the deck and draw again. |
| `/backto <id>` | Revert the simulation state to a specific snapshot ID and reshuffle. |
| `/reset` | Reset and reshuffle the deck for the **current** playlist only. |
| `/deck` | Show combinations remaining in the current deck (alphabetical order). |
| `/history` | Show recently played combinations (admin). |
| `/status` | Show internal deck state — card counts per zone (admin). |
> 💡 **Tip:** Thanks to Discord's autocomplete, you can simply type `/next 3` and press Enter to draw multiple matches quickly without clicking the parameter.
---

## How the Deck System Works

```text
[ Priority Queue ] ──(Drawn first when valid)──┐
        ▲                                      │
        │ (If stuck)                           ▼
    [ Deck ] ─────────draw─────────▶ [ Selected ] ──▶ [ Trash ]
        ▲                                                 │
        │                                                 │
        └────────────(Reshuffle to replenish)─────────────┘
```

Normally, cards are drawn from the Deck. If every remaining card in the deck violates a cooldown rule, those cards are shifted to the Priority Queue, and the Trash is reshuffled into a new deck. Cards in the Priority Queue take precedence and will be drawn as soon as they become valid again.

### Playlist System

Use `/start` to begin a custom match session. The bot presents two steps:

1. **Select a playlist**: Ranked Arena or GA (Gentleman's Agreement).
2. **Choose action**: Resume from existing save data, or reset and start over.

Each playlist maintains its own deck state, cooldown settings, and snapshot history independently. The current playlist is remembered per channel.

> The GA playlist uses its own cooldown settings (`rule_cooldown: 3`, `map_cooldown: 3`, `exact_cooldown: 5`) and its own set of 17 map/rule combinations.

---

## Server Setup

### Permissions (Optional)

By default, all server members can use every command. To restrict commands to specific roles:

1. Create a role (e.g. `Custom Host`).
2. Go to **Server Settings → Integrations → Exuberant Witness**.
3. Under **Command Permissions**, click **Add roles or members**.
4. Select the role you created.
5. Click the **✖** next to **@everyone** to remove default access.
6. Only members with the `Custom Host` role can now use Exuberant Witness commands.

> Server administrators can always use all commands regardless of restrictions.

---

## Add to Your Server

**[Click here to invite Exuberant Witness](https://discord.com/oauth2/authorize?client_id=1514278490818609162&permissions=2048&integration_type=0&scope=bot)**

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.