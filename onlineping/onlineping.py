import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

class OnlinePing(commands.Cog):
    """Ping requesters when tracked members come online."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321012345678, force_registration=True)
        self.config.register_guild(targets={})  # {user_id: {"channel": int, "pingers": [int,...]}}

    @commands.group(name="onlineping", aliases=["op"])
    @commands.guild_only()
    async def op(self, ctx):
        """Online ping settings."""

    @op.command(name="track")
    @checks.admin_or_permissions(manage_guild=True)
    async def track(self, ctx, member: discord.Member, channel: discord.TextChannel = None):
        """Track MEMBER; ping you when they come online. Optionally set CHANNEL."""
        ch = channel or ctx.channel
        data = await self.config.guild(ctx.guild).targets()
        entry = data.get(str(member.id), {"channel": ch.id, "pingers": []})
        if ctx.author.id not in entry["pingers"]:
            entry["pingers"].append(ctx.author.id)
        entry["channel"] = ch.id
        data[str(member.id)] = entry
        await self.config.guild(ctx.guild).targets.set(data)
        await ctx.send(f"Tracking {member.mention}. I’ll ping you in {ch.mention} when they go **online**.")

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
        await ctx.send("\n".join(lines))

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # Requires Intents.presences and Intents.members
        if before.guild is None or before.status == after.status:
            return
        if after.status != discord.Status.online:
            return
        data = await self.config.guild(after.guild).targets()
        entry = data.get(str(after.id))
        if not entry:
            return
        ch = after.guild.get_channel(entry["channel"])
        if ch:
            mentions = " ".join(f"<@{pid}>" for pid in entry["pingers"])
            await ch.send(f"{mentions} {after.mention} just came **online**.")
