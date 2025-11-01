# OnlinePing — Red Discord Bot Cog

Ping when tracked members change **Discord status**.

- `online_only` — only ping when a member switches to **Online**
- `all` — ping on **any** status change (Online / Offline / Idle / DND / Invisible)

> Requires Discord **Privileged Gateway Intents**: **Guild Presences** and **Guild Members**.

---

## Features
- Track **multiple targets** per guild (run `track` once per user)
- Per-guild **mode**: `online_only` or `all`
- Choosable **channel** to post pings
- Minimal storage (member IDs, requester IDs, channel ID)

---

## Requirements
- Red Discord Bot **v3.5+**
- Your bot application with **Guild Presences** and **Guild Members** intents enabled in the **Developer Portal**
- Bot permission to **Send Messages** in the target channel(s)

> If your bot is in **≥100 servers**, Discord may require intent **approval**.

---

## Install

### A) Via Downloader (recommended)
```text
.load downloader
.repo add onlineping https://github.com/Kevin-Mok/online-ping-cog
.cog install onlineping onlineping
.load onlineping
