import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

STATUS_EMOJI = {
    discord.Status.online: "🟢 online",
    discord.Status.offline: "⚫ offline",
    discord.Status.idle: "🌙 idle",
    discord.Status.dnd: "⛔ dnd",
    # Some libraries expose invisible distinctly; clients show it as offline to others.
    discord.Status.invisible: "⚫ invisible",
}

class OnlinePing(commands.Cog):
    """Ping requesters when tracked members change status (or come online)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=987654321012345678, force_registration=True
        )
        # targets: {target_id: {"channel": int, "pingers": [int, ...]}}
        # mode: "online_only" or "all"
        # prefs: {requester_id: {"mention": bool}}
        self.config.register_guild(targets={}, mode="online_only", prefs={})

    @commands.group(name="onlineping", aliases=["op"])
    @commands.guild_only()
    async def op(self, ctx):
        """Online ping settings."""

    @op.command(name="mode")
    @checks.admin_or_permissions(manage_guild=True)
    async def mode(self, ctx, mode: str):
        """Set when to ping: online_only (default) or all."""
        mode = mode.lower()
        if mode not in {"online_only", "all"}:
            return await ctx.send("Mode must be `online_only` or `all`.")
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(f"OnlinePing mode set to **{mode}**.")

    @op.command(name="pingme")
    async def pingme(self, ctx, option: str):
        """Choose whether YOU are mentioned on alerts: on/off."""
        opt = option.lower()
        if opt not in {"on", "off", "true", "false", "yes", "no"}:
            return await ctx.send("Use `on` or `off`.")
        mention = opt in {"on", "true", "yes"}
        prefs = await self.config.guild(ctx.guild).prefs()
        prefs[str(ctx.author.id)] = {"mention": mention}
        await self.config.guild(ctx.guild).prefs.set(prefs)
        await ctx.send(
            f"I will **{'mention' if mention else 'not mention'}** you on OnlinePing alerts."
        )

    @op.command(name="track")
    @checks.admin_or_permissions(manage_guild=True)
    async def track(self, ctx, member: discord.Member, channel: discord.TextChannel = None):
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
    async def untrack(self, ctx, member: discord.Member):
        """Stop pinging you for MEMBER."""
        data = await self.config.guild(ctx.guild).targets()
        entry = data.get(str(member.id))
        if not entry or ctx.author.id not in entry["pingers"]:
            return await ctx.send("You weren’t being pinged for that member.")
        entry["pingers"].remove(ctx.author.id)
        if not entry["pingers"]:
            data.pop(str(member.id), None)
        else:
            data[str(member.id)] = entry
        await self.config.guild(ctx.guild).targets.set(data)
        await ctx.send(f"Removed your pings for {member.mention}.")

    @op.command(name="list")
    async def list_(self, ctx):
        """List tracked members + mode. Shows whether you'll be mentioned."""
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
            lines.append(f"- {who.mention if who else uid} → <#{entry['channel']}> (ping: {pingers})")
        mode = await self.config.guild(ctx.guild).mode()
        lines.append(f"\nMode: **{mode}** (`online_only` or `all`)")
        await ctx.send("\n".join(lines))

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # Requires Intents.presences + Intents.members
        # Only act if STATUS changed (ignore pure activity changes).
        if before.guild is None or before.status == after.status:
            return

        data = await self.config.guild(after.guild).targets()
        entry = data.get(str(after.id))
        if not entry:
            return

        mode = await self.config.guild(after.guild).mode()
        if mode == "online_only" and after.status != discord.Status.online:
            return

        ch = after.guild.get_channel(entry["channel"])
        if not ch:
            return

        # Build mentions list honoring per-user 'mention' preference (default True)
        prefs = await self.config.guild(after.guild).prefs()
        mention_ids = [
            pid for pid in entry["pingers"]
            if prefs.get(str(pid), {}).get("mention", True)
        ]
        mentions = " ".join(f"<@{pid}>" for pid in mention_ids)

        before_label = STATUS_EMOJI.get(before.status, str(before.status))
        after_label  = STATUS_EMOJI.get(after.status,  str(after.status))

        # Build the base message first…
        msg = f"{after.mention} status changed: **{before_label} → {after_label}**."
        # …then add mentions at the very end (if any).
        if mentions:
            msg = f"{msg} {mentions}"

        await ch.send(msg)
