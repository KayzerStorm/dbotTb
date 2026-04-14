import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
from zoneinfo import ZoneInfo  # ← En lugar de pytz
import os
import asyncio
import logging

class Rashid(commands.Cog):
    """Módulo para mostrar la ubicación diaria de Rashid con soporte de mapas."""
    def __init__(self, bot):
        self.bot = bot
        # Zona horaria de Hermosillo usando zoneinfo
        self.timezone = ZoneInfo('America/Hermosillo')
        
        # Diccionario con nombres de archivos y ubicaciones exactas
        self.locations = {
            0: {"city": "Svargrond", "map": "Minimap_Floor_0.png", "pos": "En la taberna de Dankwart, al sur del templo."},
            1: {"city": "Liberty Bay", "map": "Minimap_Floor_1.png", "pos": "En la taberna de Lyonel, al oeste del depot."},
            2: {"city": "Port Hope", "map": "Minimap_Floor_2.png", "pos": "En la taberna de Clyde, al norte del depot."},
            3: {"city": "Ankrahmun", "map": "Minimap_Floor_3.png", "pos": "En la taberna de Jakundaf, arriba del depot."},
            4: {"city": "Darashia", "map": "Minimap_Floor_4.png", "pos": "En la taberna de Omur, al oeste del depot."},
            5: {"city": "Edron", "map": "Minimap_Floor_5.png", "pos": "En la taberna de Mirabell, arriba del depot."},
            6: {"city": "Carlin", "map": "Minimap_Floor_6.png", "pos": "En la taberna de Gorn, arriba del depot."}
        }
        self.auto_rashid.start()

    def cog_unload(self):
        self.auto_rashid.cancel()

    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})

    def get_rashid_info(self):
        day = datetime.now(self.timezone).weekday()
        return self.locations.get(day, {"city": "Desconocida", "map": None, "pos": "Desconocida"})

    async def send_rashid_embed(self, guild_id):
        """Genera y envía el embed de Rashid, editando el anterior si es posible."""
        s = self.get_settings(guild_id)
        channel_id = s.get("rashid_channel")
        if not channel_id: return

        channel = self.bot.get_channel(int(channel_id))
        if not channel: return

        info = self.get_rashid_info()
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        now = datetime.now(self.timezone)
        dia_actual = dias[now.weekday()]
        
        embed = discord.Embed(
            title="👳‍♂️ Ubicación Diaria de Rashid",
            description=f"[The Traveling Trader](https://tibia.fandom.com/wiki/The_Traveling_Trader_Quest) \n Hoy es **{dia_actual}**, Rashid se encuentra en:",
            color=0xf1c40f
        )
        embed.add_field(name="📍 Ciudad", value=f"**{info['city']}**", inline=True)
        embed.add_field(name="🏠 Lugar", value=info['pos'], inline=False)
        
        file = None
        if info['map']:
            image_path = os.path.join("mapas", info['map'])
            if os.path.exists(image_path):
                file = discord.File(image_path, filename=info['map'])
                embed.set_image(url=f"attachment://{info['map']}")

        msg_id = s.get("last_rashid_message_id")
        
        try:
            if msg_id:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.delete()
                except:
                    pass
            
            new_msg = await channel.send(file=file, embed=embed) if file else await channel.send(embed=embed)
            s["last_rashid_message_id"] = new_msg.id
            self.bot.save_data()
        except Exception as e:
            logging.error(f"Error enviando Rashid en guild {guild_id}: {e}")

    @tasks.loop(time=time(hour=8, minute=0))
    async def auto_rashid(self):
        """Bucle diario para actualizar Rashid."""
        try:
            for gid in list(self.bot.db.keys()):
                await self.send_rashid_embed(gid)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error en el bucle de Rashid: {e}")

    @auto_rashid.before_loop
    async def before_rashid(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setup_rashid", description="Configura el canal para el reporte diario de Rashid")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_rashid(self, interaction: discord.Interaction, canal: discord.TextChannel):
        s = self.get_settings(interaction.guild_id)
        s["rashid_channel"] = canal.id
        s["last_rashid_message_id"] = None
        self.bot.save_data()
        
        await interaction.response.send_message(f"✅ Canal de Rashid configurado en {canal.mention}.", ephemeral=True)
        await self.send_rashid_embed(interaction.guild_id)

    @app_commands.command(name="rashid", description="Muestra la ubicación actual de Rashid")
    async def rashid_manual(self, interaction: discord.Interaction):
        info = self.get_rashid_info()
        embed = discord.Embed(
            title=f"📍 Rashid está en {info['city']}",
            description=f"**Ubicación:** {info['pos']}",
            color=0xf1c40f
        )
        
        file = None
        if info['map']:
            image_path = os.path.join("mapas", info['map'])
            if os.path.exists(image_path):
                file = discord.File(image_path, filename=info['map'])
                embed.set_image(url=f"attachment://{info['map']}")
        
        if file:
            await interaction.response.send_message(file=file, embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Rashid(bot))