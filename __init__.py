from .onlineping import OnlinePing

async def setup(bot):
    await bot.add_cog(OnlinePing(bot))
