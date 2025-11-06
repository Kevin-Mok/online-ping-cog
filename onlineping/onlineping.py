import re
import time
import discord
from typing import Optional
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

STATUS_EMOJI = {
    discord.Status.online: "🟢 online",
    discord.Status.offline: "⚫ offline",
    discord.Status.idle: "🌙 idle",
    discord.Status.dnd: "⛔ dnd",
    # Libraries sometimes expose 'invisible' distinctly; most clients show it like Offline.
    discord.Status.invisible: "⚫ invisible",
}

IDENTIFIER = 987654321012345678  # arbitrary unique int for this cog's Config

class OnlinePing(commands.Cog):
    """Ping requesters when tracked members change status (or come online)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=IDENTIFIER, force_registration=True)
        # targets: {target_id: {"channel": int, "pingers": [int, ...]}}
        # mode: "online_only" or "all"
        # prefs: {requester_id: {"mention": bool}}
        # cooldown: seconds between alerts per (guild, target). 0 = disabled
        self.config.register_guild(targets={}, mode="online_only", prefs={}, cooldown=300)
        # in-memory throttle: {(guild_id, target_id): float_monotonic_last_sent}
        self._last_ping = {}

    # ---------- helpers ----------

    def _parse_seconds(self, text: str) -> Optional[int]:
        """Parse '300', '5m', '2m30s', '1h5m' → seconds. Return None if invalid."""
        if text is None:
            return None
        s = text.strip().lower()
        if s.isdigit():
            return int(s)
        parts = re.findall(r"(\d+)\s*([hms])", s)
        if not parts:
            return None
        total = 0
        for num, unit in parts:
            n = int(num)
            if unit == "h":
                total += n * 3600
            elif unit == "m":
                total += n * 60
            else:
                total += n
        return total

    def _fmt_secs(self, secs: int) -> str:
        if secs == 0:
            return "0s (disabled)"
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        out = []
        if h: out.append(f"{h}h")
        if m: out.append(f"{m}m")
        if s or not out: out.append(f"{s}s")
        return "".join(out)

    # ---------- commands ----------

    @commands.group(name="onlineping", aliases=["op"])
    @commands.guild_only()
    async def op(self, ctx: commands.Context):
        """Online ping settings."""

    @op.command(name="mode")
    @checks.admin_or_permissions(manage_guild=True)
    async def mode(self, ctx: commands.Context, mode: str):
        """Set when to ping: online_only (default) or all."""
        mode_l = (mode or "").lower()
        if mode_l not in {"online_only", "all"}:
            return await ctx.send("Mode must be `online_only` or `all`.")
        await self.config.guild(ctx.guild).mode.set(mode_l)
        await ctx.send(f"OnlinePing mode set to **{mode_l}**.")

    @op.command(name="pingme")
    async def pingme(self, ctx: commands.Context, option: str):
        """Choose whether YOU are mentioned on alerts: on/off."""
        opt = (option or "").lower()
        if opt not in {"on", "off", "true", "false", "yes", "no"}:
            return await ctx.send("Use `on` or `off`.")
        mention = opt in {"on", "true", "yes"}
        prefs = await self.config.guild(ctx.guild).prefs()
        prefs[str(ctx.author.id)] = {"mention": mention}
        await self.config.guild(ctx.guild).prefs.set(prefs)
        await ctx.send(
            f"I will **{'mention' if mention else 'not mention'}** you on OnlinePing alerts."
        )

    @op.command(name="cooldown")
    @checks.admin_or_permissions(manage_guild=True)
    async def cooldown(self, ctx: commands.Context, value: Optional[str] = None):
        """View/set cooldown between alerts. Accepts seconds or 5m/2m30s. Use 0 to disable."""
        if value is None:
            cd = await self.config.guild(ctx.guild).cooldown()
            return await ctx.send(f"Current cooldown: **{self._fmt_secs(cd)}**.")
        seconds = self._parse_seconds(value)
        if seconds is None or seconds < 0:
            return await ctx.send("Give a duration like `300`, `5m`, or `2m30s` (0 to disable).")
        await self.config.guild(ctx.guild).cooldown.set(int(seconds))
        await ctx.send(f"Cooldown set to **{self._fmt_secs(int(seconds))}**.")

    @op.command(name="track")
    @checks.admin_or_permissions(manage_guild=True)
    async def track(self, ctx: commands.Context, member: discord.Member, channel: Optional[discord.TextChannel] = None):
        """Track MEMBER; ping on status changes. Optionally set CHANNEL."""
        ch = channel or ctx.channel
        data = await self.config.guild(ctx.guild).targets()
        entry = data.get(str(member.id), {"channel": ch.id, "pingers": []})
        if ctx.author.id not in entry["pingers"]:
            entry["pingers"].append(ctx.author.id)
        entry["channel"] = ch.id
        data[str(member.id)] = entry
        await self.config.guild(ctx.guild).targets.set(data)
        await ctx.send(f"Tracking {member.mention}. Pings in {ch.mention}.")

    @op.command(name="untrack")
    async def untrack(self, ctx: commands.Context, member: discord.Member):
        """Stop pinging you for MEMBER."""
        data = await self.config.guild(ctx.guild).targets()
        entry = data.get(str(member.id))
        if not entry or ctx.author.id not in entry["pingers"]:
            return await ctx.send("You weren’t being pinged for that member.")
        entry["pingers"].remove(ctx.author.id)
        if not entry["pingers"]:
            data.pop(str(member.id), None)
            # clear throttle entry too
            self._last_ping.pop((ctx.guild.id, member.id), None)
        else:
            data[str(member.id)] = entry
        await self.config.guild(ctx.guild).targets.set(data)
        await ctx.send(f"Removed your pings for {member.mention}.")

    @op.command(name="list")
    async def list_(self, ctx: commands.Context):
        """List tracked members + settings."""
        data = await self.config.guild(ctx.guild).targets()
        prefs = await self.config.guild(ctx.guild).prefs()
        if not data:
            return await ctx.send("Nothing tracked.")
        lines = []
        for uid, entry in data.items():
            who = ctx.guild.get_member(int(uid))
            pieces = []
            for pid in entry["pingers"]:
                mention_pref = prefs.get(str(pid), {}).get("mention", True)
                label = f"<@{pid}>" if mention_pref else f"<@{pid}> (no ping)"
                pieces.append(label)
            pingers = ", ".join(pieces) or "—"
            lines.append(f"- {who.mention if who else uid} → <#{entry['channel']}> (watchers: {pingers})")
        mode = await self.config.guild(ctx.guild).mode()
        cd = await self.config.guild(ctx.guild).cooldown()
        lines.append(f"\nMode: **{mode}** (`online_only` or `all`)")
        lines.append(f"Cooldown: **{self._fmt_secs(cd)}**")
        await ctx.send("\n".join(lines))

    # ---------- events ----------

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """
        Requires Intents.presences + Intents.members.
        Fires when a member's presence changes; we only act on status changes.
        """
        if before.guild is None or before.status == after.status:
            return

        # Is this member tracked in this guild?
        data = await self.config.guild(after.guild).targets()
        entry = data.get(str(after.id))
        if not entry:
            return

        # Respect mode
        mode = await self.config.guild(after.guild).mode()
        if mode == "online_only" and after.status != discord.Status.online:
            return

        # Throttle per (guild, target)
        now = time.monotonic()
        cd = await self.config.guild(after.guild).cooldown()
        if cd > 0:
            key = (after.guild.id, after.id)
            last = self._last_ping.get(key, 0.0)
            if now - last < cd:
                return

        # Resolve channel
        ch = after.guild.get_channel(entry["channel"])
        if not ch:
            return

        # Build mentions honoring per-user 'mention' preference (default True)
        prefs = await self.config.guild(after.guild).prefs()
        mention_ids = [
            pid for pid in entry["pingers"]
            if prefs.get(str(pid), {}).get("mention", True)
        ]
        mentions = " ".join(f"<@{pid}>" for pid in mention_ids)

        # Compose message (mention(s) at the END)
        before_label = STATUS_EMOJI.get(before.status, str(before.status))
        after_label = STATUS_EMOJI.get(after.status, str(after.status))
        msg = f"{after.mention} status changed: **{before_label} → {after_label}**."
        if mentions:
            msg = f"{msg} {mentions}"

        await ch.send(msg)

        # Record throttle time
        if cd > 0:
            self._last_ping[(after.guild.id, after.id)] = now
