import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
import json

l = logging.getLogger('YuZhongBot')

class AdminCog(commands.Cog):
    def __init__(self, b):
        self.b = b
        self.a = b.active_channels
        self.s = b.save_enabled_channels
        self.m = b.MEMORY_DIR
        self.r = b.safe_send_response

    @app_commands.command(name="arise", description="Activate Yu Zhong in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def arise(self, i: discord.Interaction):
        c = str(i.channel_id)
        if c is None:
            await self.r(i, "This command can only be used in a channel.", ephemeral=True)
            return

        self.a[c] = True
        self.s()
        await self.r(i, "Yu Zhong reigns over this channel...", ephemeral=True)

    @app_commands.command(name="stop", description="Put Yu Zhong back to rest in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def stop(self, i: discord.Interaction):
        c = str(i.channel_id)
        if c is None:
            await self.r(i, "This command can only be used in a channel.", ephemeral=True)
            return

        self.a[c] = False
        self.s()
        await self.r(i, "Yu Zhong no longer reigns over this channel.", ephemeral=True)

    @app_commands.command(name="reset", description="Reset Yu Zhong's memory for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, i: discord.Interaction):
        g = str(i.guild_id)
        if g is None:
            await self.r(i, "This command can only be used in a server.", ephemeral=True)
            return

        rem = False
        if not os.path.exists(self.m):
            os.makedirs(self.m)

        for f in os.listdir(self.m):
            if f.startswith(f"user_{g}_") and f.endswith(".json"):
                try:
                    os.remove(os.path.join(self.m, f))
                    rem = True
                except OSError as e:
                    l.error(f"Failed to remove memory file {f}: {e}")

        if rem:
            await self.r(i, "Yu Zhong's memory has been purged for this server.", ephemeral=True)
        else:
            await self.r(i, "No memory found to reset for this server.", ephemeral=True)

async def setup(b):
    await b.add_cog(AdminCog(b))
