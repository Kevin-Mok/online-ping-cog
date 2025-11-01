# onlineping/onlineping.py
import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

STATUS_EMOJI = {
    discord.Status.online: "🟢 online",
    discord.Status.offline: "⚫ offline",
    discord.Status.idle: "🌙 idle",
    discord.Status.dnd: "⛔ dnd",
    # Some libraries expose 'invisible' separately; Discord clients show it as offline to others.
    # We'll render it explicitly to be clear.
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
        self.config.register_guild(targets={}, mode="online_only")

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
        """List tracked members."""
        data = await self.config.guild(ctx.guild).targets()
        if not data:
            return await ctx.send("Nothing tracked.")
        lines = []
        for uid, entry in data.items():
            who = ctx.guild.get_member(int(uid))
            pingers = ", ".join(f"<@{pid}>" for pid in entry["pingers"]) or "—"
            lines.append(f"- {who.mention if who else uid} → <#{entry['channel']}> (ping: {pingers})")
        mode = await self.config.guild(ctx.guild).mode()
        lines.append(f"\nMode: **{mode}** (`online_only` or `all`)")
        await ctx.send("\n".join(lines))

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # Requires Intents.presences + Intents.members enabled in the Dev Portal and requested by the bot.
        # Only act if STATUS changed (ignore pure activity changes).
        if before.guild is None or before.status == after.status:
            return

        data = await self.config.guild(after.guild).targets()
        entry = data.get(str(after.id))
        if not entry:
            return

        mode = await self.config.guild(after.guild).mode()
        # Keep old behavior unless mode == "all"
        if mode == "online_only" and after.status != discord.Status.online:
            return

        ch = after.guild.get_channel(entry["channel"])
        if not ch:
            return

        before_label = STATUS_EMOJI.get(before.status, str(before.status))
        after_label  = STATUS_EMOJI.get(after.status,  str(after.status))
        mentions = " ".join(f"<@{pid}>" for pid in entry["pingers"]) or ""
        await ch.send(
            f"{mentions} {after.mention} status changed: **{before_label} → {after_label}**."
        )
