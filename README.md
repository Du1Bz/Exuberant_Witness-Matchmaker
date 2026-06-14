# Exuberant Witness - Matchmaker — Halo Infinite Custom Match Selector

A Discord Bot that randomly selects map & rule combinations for Halo Infinite ranked arena custom matches using a deck system.

> 日本語版は [README_ja.md](README_ja.md) をご覧ください。

---

## What It Does

Exuberant Witness shuffles map & rule combinations into a deck and draws from the top. Instead of pure RNG, it uses a smart algorithm to prevent repetitive matches.

- **Cooldown logic** prevents back-to-back duplicates: same map (last 4 matches), same rule type (last 3 matches), and exact same combination (last 7 matches) are automatically blocked.
- **Priority Queue System**: If all remaining cards in the deck are blocked by cooldowns (a dead end), they are temporarily moved to the Priority Queue. The trash pile is then reshuffled into a new deck to keep the games rolling. Cards in the Priority Queue will be drawn first as soon as their cooldowns expire.
- **Per-channel decks** allow multiple custom lobbies to run simultaneously without interfering with each other.
- Available 24/7 with instant responses.

---

## Commands

| Command | Description |
|---------|-------------|
| `/next` | Draw the next match combination (remaining count shown). |
| `/next count:3` | Draw multiple combinations at once (1–5). |
| `/redraw` | Return the previous draw to the deck and draw again. |
| `/reset` | Reset the deck and reshuffle all 22 cards. |
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