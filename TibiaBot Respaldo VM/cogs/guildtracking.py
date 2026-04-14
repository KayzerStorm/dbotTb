import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import logging

class GuildSync(commands.Cog):
    """Módulo para sincronizar miembros de Guilds oficiales de Tibia con listas locales."""
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://api.tibiadata.com/v4/guild/"

    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})

    @app_commands.command(name="sync_guild", description="Importa los miembros de una Guild de Tibia a una lista local")
    @app_commands.describe(lista="Nombre de la lista local", nombre_guild="Nombre exacto de la Guild en Tibia")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_guild(self, interaction: discord.Interaction, lista: str, nombre_guild: str):
        await interaction.response.defer()
        s = self.get_settings(interaction.guild_id)
        
        if "lists" not in s or lista not in s["lists"]:
            return await interaction.followup.send(f"❌ La lista `{lista}` no existe. Créala primero con `/create_list`.")

        async with aiohttp.ClientSession() as session:
            try:
                url_guild = f"{self.api_url}{nombre_guild.replace(' ', '%20')}"
                async with session.get(url_guild, timeout=15) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(f"❌ Error API (Status {resp.status}). Verifica el nombre de la Guild.")
                    
                    data = await resp.json()
                    guild_data = data.get("guild", {})
                    members = guild_data.get("members", [])
                    
                    if not members:
                        return await interaction.followup.send(f"⚠️ No se encontró la guild `{nombre_guild}` o no tiene miembros públicos.")
                    
                    added = 0
                    exists = 0
                    for m in members:
                        name = m.get("name")
                        if name:
                            if name not in s["lists"][lista]:
                                s["lists"][lista].append(name)
                                added += 1
                            else:
                                exists += 1
                    
                    self.bot.save_data()
                    
                    embed = discord.Embed(title="🏰 Sincronización de Guild", color=0x3498db)
                    embed.add_field(name="Guild", value=nombre_guild, inline=True)
                    embed.add_field(name="Mundo", value=guild_data.get("world", "N/A"), inline=True)
                    embed.add_field(name="Añadidos", value=f"`{added}`", inline=True)
                    embed.add_field(name="Ya existían", value=f"`{exists}`", inline=True)
                    embed.set_footer(text=f"Lista destino: {lista}")
                    
                    await interaction.followup.send(embed=embed)

            except Exception as e:
                logging.error(f"Error en GuildSync: {e}")
                await interaction.followup.send(f"⚠️ Error inesperado: `{e}`")

async def setup(bot):
    await bot.add_cog(GuildSync(bot))
