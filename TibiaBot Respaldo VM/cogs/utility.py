import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import logging

class Utility(commands.Cog):
    """Módulo de utilidades generales para el servidor y consultas de Tibia."""
    def __init__(self, bot):
        self.bot = bot
        self.api_char_url = "https://api.tibiadata.com/v4/character/"

    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})

    @app_commands.command(name="whois", description="Muestra información detallada de un personaje de Tibia")
    @app_commands.describe(nombre="El nombre del personaje a consultar")
    async def whois(self, interaction: discord.Interaction, nombre: str):
        await interaction.response.defer()
        
        url = f"{self.api_char_url}{nombre.replace(' ', '%20')}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        char_data = data.get("character", {})
                        char = char_data.get("character", {})
                        
                        if not char or not char.get("name"):
                            return await interaction.followup.send(f"❌ No se encontró al personaje **{nombre}**.")
                        
                        embed = discord.Embed(
                            title=f"👤 {char['name']}", 
                            color=0x3498db if char.get("status") == "online" else 0x95a5a6
                        )
                        
                        status_emoji = "🟢 Online" if char.get("status") == "online" else "🔴 Offline"
                        guild_info = char.get("guild", {})
                        guild_str = f"{guild_info.get('rank', '')} of {guild_info.get('name', '')}" if guild_info.get("name") else "Ninguna"
                        
                        embed.add_field(name="Nivel", value=char.get("level", "N/A"), inline=True)
                        embed.add_field(name="Vocación", value=char.get("vocation", "N/A"), inline=True)
                        embed.add_field(name="Mundo", value=char.get("world", "N/A"), inline=True)
                        embed.add_field(name="Gremio", value=guild_str, inline=False)
                        embed.add_field(name="Estado", value=status_emoji, inline=True)
                        
                        if char.get("last_login"):
                            last_login = char["last_login"].replace("T", " ").replace("Z", "")
                            embed.add_field(name="Último Login", value=last_login, inline=True)
                        
                        embed.set_footer(text=f"Consultado por {interaction.user.display_name}")
                        await interaction.followup.send(embed=embed)
                    else:
                        await interaction.followup.send(f"⚠️ Error al consultar la API (Status {resp.status}).")
        except Exception as e:
            logging.error(f"Error en comando whois: {e}")
            await interaction.followup.send("❌ Ocurrió un error al procesar la consulta.")

    @app_commands.command(name="move_all", description="Mueve a todos los miembros de voz a tu canal actual")
    @app_commands.checks.has_permissions(move_members=True)
    async def move_all(self, interaction: discord.Interaction):
        if not interaction.user.voice: 
            return await interaction.response.send_message("❌ Debes estar en un canal de voz para usar este comando.", ephemeral=True)
        
        dest = interaction.user.voice.channel
        await interaction.response.defer(ephemeral=True)
        
        count = 0
        for vc in interaction.guild.voice_channels:
            if vc != dest:
                for m in vc.members:
                    try: 
                        await m.move_to(dest)
                        count += 1
                    except Exception as e:
                        logging.warning(f"No se pudo mover a {m.display_name}: {e}")
                        continue
        
        await interaction.followup.send(f"✅ Se han movido {count} miembros a **{dest.name}**.")

    @app_commands.command(name="ping", description="Muestra la latencia del bot")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 ¡Pong! Latencia: **{latency}ms**")

async def setup(bot):
    await bot.add_cog(Utility(bot))
