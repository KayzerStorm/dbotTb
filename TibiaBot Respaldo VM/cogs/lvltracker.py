import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime, timedelta
import logging

class LevelTracker(commands.Cog):
    """Módulo para el seguimiento de progreso de niveles diario y mensual."""
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://api.tibiadata.com/v4/character/"
        self.update_tracker.start()

    def cog_unload(self):
        self.update_tracker.cancel()

    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})

    async def get_char_level(self, session, name):
        """Consulta el nivel actual de un personaje en la API."""
        try:
            async with session.get(f"{self.api_url}{name.replace(' ', '%20')}", timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    char_info = data.get("character", {}).get("character", {})
                    return char_info.get("level")
        except Exception as e:
            logging.error(f"Error consultando API para {name}: {e}")
        return None

    async def update_report_embed(self, guild_id):
        """Genera y actualiza el embed de reporte en el canal configurado."""
        s = self.get_settings(guild_id)
        chan_id = s.get("tracker_channel_id")
        active_lists = s.get("active_lvltracker_lists", [])
        
        if not chan_id or not active_lists:
            return

        chan = self.bot.get_channel(int(chan_id))
        if not chan: return

        # Recopilar todos los jugadores de las listas activas
        all_players = set()
        for lname in active_lists:
            if lname in s.get("lists", {}):
                all_players.update(s["lists"][lname])
        
        if not all_players: return

        if "level_tracker" not in s: s["level_tracker"] = {"data": {}, "last_msg_id": None}
        tracker_data = s["level_tracker"].get("data", {})
        
        player_stats = []
        limit_date = datetime.now() - timedelta(days=30)

        for p_name in all_players:
            char_data = tracker_data.get(p_name)
            if not char_data or "history" not in char_data: continue

            history = char_data["history"]
            sorted_dates = sorted(history.keys())
            if not sorted_dates: continue

            level_now = char_data.get("current_level", history[sorted_dates[-1]])
            
            # Buscar el nivel base más antiguo dentro de los últimos 30 días
            level_base = None
            for date_key in sorted_dates:
                try:
                    date_obj = datetime.strptime(date_key, "%Y-%m-%d")
                    if date_obj >= limit_date:
                        level_base = history[date_key]
                        break
                except: continue
            
            if level_base is not None:
                diff = level_now - level_base
                player_stats.append({"name": p_name, "level": level_now, "diff": diff})

        if not player_stats: return

        # Ordenar por mayor progreso, luego por nivel
        player_stats.sort(key=lambda x: (x["diff"], x["level"]), reverse=True)

        embed = discord.Embed(
            title="📈 Ranking de Progreso Diario",
            description=f"Comparativa de niveles (Últimos 30 días) para: {', '.join(active_lists)}",
            color=0x5865F2,
            timestamp=datetime.now()
        )

        report_list = ""
        for i, p in enumerate(player_stats, 1):
            emoji = "🔥" if p["diff"] >= 5 else "🚀" if p["diff"] > 0 else "💤"
            medalla = "🥇" if i == 1 and p["diff"] > 0 else "🥈" if i == 2 and p["diff"] > 0 else "🥉" if i == 3 and p["diff"] > 0 else f"`{i}.`"
            report_list += f"{medalla} **{p['name']}**\n└ Lvl: `{p['level']}` | Progreso: `{p['diff']:+}` {emoji}\n"

        embed.description += f"\n\n{report_list}"
        embed.set_footer(text="Actualización cada 4 horas")

        try:
            old_id = s["level_tracker"].get("last_msg_id")
            if old_id:
                try:
                    msg = await chan.fetch_message(int(old_id))
                    await msg.edit(embed=embed)
                except:
                    msg = await chan.send(embed=embed)
                    s["level_tracker"]["last_msg_id"] = msg.id
            else:
                msg = await chan.send(embed=embed)
                s["level_tracker"]["last_msg_id"] = msg.id
            
            self.bot.save_data()
        except Exception as e:
            logging.error(f"Error enviando LvlTracker embed en guild {guild_id}: {e}")

    @tasks.loop(hours=4)
    async def update_tracker(self):
        """Bucle para registrar niveles y actualizar reportes."""
        try:
            async with aiohttp.ClientSession() as session:
                for gid in list(self.bot.db.keys()):
                    s = self.get_settings(gid)
                    
                    # Filtrar jugadores SOLO de las listas activas para LvlTracker
                    active_lists = s.get("active_lvltracker_lists", [])
                    if not active_lists: continue
                    
                    all_players = set()
                    for lname in active_lists:
                        if lname in s.get("lists", {}):
                            all_players.update(s["lists"][lname])
                    
                    if not all_players: continue

                    if "level_tracker" not in s: s["level_tracker"] = {"data": {}, "last_msg_id": None}
                    tracker_data = s["level_tracker"]["data"]
                    date_str = datetime.now().strftime("%Y-%m-%d")

                    for p_name in all_players:
                        level = await self.get_char_level(session, p_name)
                        if level:
                            if p_name not in tracker_data:
                                tracker_data[p_name] = {"history": {}}
                            
                            # Guardar nivel base del día si no existe
                            if date_str not in tracker_data[p_name]["history"]:
                                tracker_data[p_name]["history"][date_str] = level
                            
                            # Guardar nivel actual
                            tracker_data[p_name]["current_level"] = level
                        await asyncio.sleep(1.5) # Evitar Rate Limit

                    await self.update_report_embed(gid)
                
                self.bot.save_data()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error en el bucle de LvlTracker: {e}")

    @update_tracker.before_loop
    async def before_lvl_tracker(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setup_lvl_tracker", description="Configura el canal para el seguimiento de progreso diario")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_lvl_tracker(self, interaction: discord.Interaction, lista: str, canal: discord.TextChannel):
        s = self.get_settings(interaction.guild_id)
        if lista not in s.get("lists", {}):
            return await interaction.response.send_message(f"❌ La lista `{lista}` no existe.", ephemeral=True)
        
        s["tracker_channel_id"] = canal.id
        s["tracker_assigned_list"] = lista
        self.bot.save_data()
        
        await interaction.response.send_message(f"✅ Seguimiento de progreso para `{lista}` configurado en {canal.mention}.")
        await self.update_report_embed(interaction.guild_id)

async def setup(bot):
    await bot.add_cog(LevelTracker(bot))
