import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
import json

logger = logging.getLogger('YuZhongBot')

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_channels = bot.active_channels
        self.save_enabled_channels = bot.save_enabled_channels
        self.MEMORY_DIR = bot.MEMORY_DIR
        self.safe_send_response = bot.safe_send_response

    @app_commands.command(name="arise", description="Activate Yu Zhong in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def arise(self, interaction: discord.Interaction):
        channel_id_str = str(interaction.channel_id)
        if channel_id_str is None:
            await self.safe_send_response(interaction, "This command can only be used in a channel.", ephemeral=True)
            return

        self.active_channels[channel_id_str] = True
        self.save_enabled_channels()
        await self.safe_send_response(interaction, "Yu Zhong reigns over this channel...", ephemeral=True)

    @app_commands.command(name="stop", description="Put Yu Zhong back to rest in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def stop(self, interaction: discord.Interaction):
        channel_id_str = str(interaction.channel_id)
        if channel_id_str is None:
            await self.safe_send_response(interaction, "This command can only be used in a channel.", ephemeral=True)
            return

        self.active_channels[channel_id_str] = False
        self.save_enabled_channels()
        await self.safe_send_response(interaction, "Yu Zhong no longer reigns over this channel.", ephemeral=True)

    @app_commands.command(name="reset", description="Reset Yu Zhong's memory for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id is None:
            await self.safe_send_response(interaction, "This command can only be used in a server.", ephemeral=True)
            return

        removed = False
        if not os.path.exists(self.MEMORY_DIR):
            os.makedirs(self.MEMORY_DIR)

        for filename in os.listdir(self.MEMORY_DIR):
            if filename.startswith(f"user_{guild_id}_") and filename.endswith(".json"):
                try:
                    os.remove(os.path.join(self.MEMORY_DIR, filename))
                    removed = True
                except OSError as e:
                    logger.error(f"Failed to remove memory file {filename}: {e}")

        if removed:
            await self.safe_send_response(interaction, "Yu Zhong's memory has been purged for this server.", ephemeral=True)
        else:
            await self.safe_send_response(interaction, "No memory found to reset for this server.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
