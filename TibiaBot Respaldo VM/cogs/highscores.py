import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime
import logging

class Highscores(commands.Cog):
    """Módulo para mostrar los Highscores de una lista específica agrupados por jugador."""
    def __init__(self, bot):
        self.bot = bot
        self.categories = ["experience", "magic", "axe", "club", "sword", "distance", "shielding", "fishing", "fist"]
        self.auto_highscore_update.start()

    def cog_unload(self):
        self.auto_highscore_update.cancel()

    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})

    async def fetch_highscores(self, session, world, category, page):
        url = f"https://api.tibiadata.com/v4/highscores/{world}/{category}/all/{page}"
        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logging.error(f"Error en API Highscores ({category} p.{page}): {e}")
        return None

    def format_results(self, players_data):
        """Formatea los resultados agrupados por jugador para el embed."""
        if not players_data:
            return "Nadie de la lista se encuentra en el Top 300 actualmente."
        
        text = ""
        # Ordenar jugadores por su mejor ranking
        sorted_players = sorted(players_data.items(), key=lambda x: min(s['rank'] for s in x[1]))

        for name, skills in sorted_players:
            text += f"👤 **{name}**\n"
            skills.sort(key=lambda x: x['rank'])
            for s in skills:
                icon = "🌟" if s["category"] == "Experience" else "⚔️"
                try:
                    val = f"{int(float(s['value'])):,}" if s["category"] == "Experience" else s["value"]
                except:
                    val = s['value']
                text += f"└ {icon} #{s['rank']} en {s['category']} (**{val}**)\n"
            text += "\n"
        return text

    async def update_highscore_embed(self, guild_id):
        """Actualiza el embed de Highscores en el canal configurado."""
        s = self.get_settings(guild_id)
        chan_id = s.get("highscore_channel")
        list_name = s.get("highscore_list_target")
        world = s.get("world", "Antica")
        
        if not chan_id or not list_name or list_name not in s.get("lists", {}):
            return

        chan = self.bot.get_channel(int(chan_id))
        if not chan: return

        players_to_check = [p.lower() for p in s["lists"][list_name]]
        if not players_to_check: return

        grouped_players = {}
        async with aiohttp.ClientSession() as session:
            for cat in self.categories:
                # Consultar las primeras 6 páginas (Top 300)
                for page in range(1, 7):
                    data = await self.fetch_highscores(session, world, cat, page)
                    if data and "highscores" in data:
                        h_list = data["highscores"].get("highscore_list", [])
                        if not h_list: break
                        
                        for entry in h_list:
                            p_name = entry["name"]
                            if p_name.lower() in players_to_check:
                                if p_name not in grouped_players:
                                    grouped_players[p_name] = []
                                grouped_players[p_name].append({
                                    "rank": entry["rank"],
                                    "category": cat.capitalize(),
                                    "value": entry["value"]
                                })
                    # Pausa estratégica para no saturar la API (Rate Limit)
                    await asyncio.sleep(1.2)

        embed = discord.Embed(title=f"🏆 TOP RANKINGS: {list_name.upper()}", color=0xf1c40f)
        embed.description = self.format_results(grouped_players)
        embed.set_footer(text=f"Mundo: {world} | Actualizado: {datetime.now().strftime('%d/%m %H:%M')}")

        try:
            old_id = s.get("last_highscore_msg_id")
            if old_id:
                try:
                    msg = await chan.fetch_message(int(old_id))
                    await msg.edit(embed=embed)
                except:
                    msg = await chan.send(embed=embed)
                    s["last_highscore_msg_id"] = msg.id
            else:
                msg = await chan.send(embed=embed)
                s["last_highscore_msg_id"] = msg.id
            
            self.bot.save_data()
        except Exception as e:
            logging.error(f"Error enviando Embed Highscores en guild {guild_id}: {e}")

    @tasks.loop(hours=12)
    async def auto_highscore_update(self):
        """Bucle de actualización automática cada 12 horas."""
        try:
            for gid in list(self.bot.db.keys()):
                await self.update_highscore_embed(gid)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error en el bucle de highscores: {e}")

    @auto_highscore_update.before_loop
    async def before_highscores(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setup_highscores", description="Configura el canal y la lista para el Hall of Fame")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_highscores(self, interaction: discord.Interaction, lista: str, canal: discord.TextChannel):
        s = self.get_settings(interaction.guild_id)
        if lista not in s.get("lists", {}):
            return await interaction.response.send_message(f"❌ La lista `{lista}` no existe.", ephemeral=True)
        
        s["highscore_channel"] = canal.id
        s["highscore_list_target"] = lista
        s["last_highscore_msg_id"] = None
        self.bot.save_data()
        
        await interaction.response.send_message(f"✅ Hall of Fame configurado para `{lista}` en {canal.mention}. Procesando datos...")
        await self.update_highscore_embed(interaction.guild_id)

async def setup(bot):
    await bot.add_cog(Highscores(bot))
