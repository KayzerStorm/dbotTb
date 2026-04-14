import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime
import logging

class Tracking(commands.Cog):
    """Módulo para el seguimiento de personajes online en tiempo real con optimización de API."""
    def __init__(self, bot):
        self.bot = bot
        self.api_world_url = "https://api.tibiadata.com/v4/world/"
        self.auto_tracker.start()

    def cog_unload(self):
        self.auto_tracker.cancel()

    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})

    async def update_guild_tracking(self, session, guild_id):
        """Obtiene los jugadores online del mundo y actualiza todas las listas de la guild."""
        s = self.get_settings(guild_id)
        world_name = s.get("world", "Antica")
        lists = s.get("lists", {})
        channels = s.get("channels", {})
        
        if not lists or not channels:
            return

        # 1. Obtener todos los jugadores online del mundo (Optimización masiva)
        url = f"{self.api_world_url}{world_name.replace(' ', '%20')}"
        online_players_data = {}
        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    world_data = data.get("world", {})
                    online_list = world_data.get("online_players", [])
                    
                    for p in online_list:
                        online_players_data[p["name"]] = {
                            "level": p["level"],
                            "vocation": p["vocation"]
                        }
                else:
                    logging.warning(f"Error API TibiaData (World {world_name}): Status {resp.status}")
                    return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Error consultando mundo {world_name}: {e}")
            return

        # 2. Procesar cada lista que tenga un canal vinculado
        for list_name, channel_id in channels.items():
            if list_name not in lists:
                continue
            
            players_in_list = lists[list_name]
            vocation_groups = {
                "Elite Knight": [], "Elder Druid": [], "Master Sorcerer": [], "Royal Paladin": [], "Otros": []
            }
            online_count = 0

            for p_name in players_in_list:
                if p_name in online_players_data:
                    online_count += 1
                    p_info = online_players_data[p_name]
                    voc = p_info["vocation"]
                    
                    found_voc = False
                    for key in vocation_groups.keys():
                        if key in voc:
                            vocation_groups[key].append({"name": p_name, "level": p_info["level"]})
                            found_voc = True
                            break
                    
                    if not found_voc:
                        vocation_groups["Otros"].append({"name": p_name, "level": p_info["level"]})

            # 3. Generar Embed
            embed = discord.Embed(
                title=f"📊 Status Online: {list_name}", 
                color=0x2ecc71 if online_count > 0 else 0xe74c3c
            )
            
            icons = {"Elite Knight": "🛡️", "Elder Druid": "🌿", "Master Sorcerer": "🔥", "Royal Paladin": "🏹", "Otros": "👤"}
            
            embed_content = ""
            for voc, members in vocation_groups.items():
                if members:
                    members.sort(key=lambda x: x["level"], reverse=True)
                    val = "\n".join([f"🟢 **{m['name']}** | Lvl: {m['level']}" for m in members])
                    embed.add_field(name=f"{icons.get(voc, '👤')} {voc}s", value=val, inline=True)

            embed.description = f"👥 **Miembros:** {len(players_in_list)}\n🔥 **Online ahora:** {online_count}\n"
            if online_count == 0:
                embed.description += "\n_Nadie online actualmente._"

            embed.set_footer(text=f"Mundo: {world_name} | Actualizado: {datetime.now().strftime('%H:%M:%S')}")

            try:
                channel = self.bot.get_channel(int(channel_id))
                if not channel: continue

                if "last_msg_ids" not in s: s["last_msg_ids"] = {}
                old_id = s["last_msg_ids"].get(list_name)
                
                msg = None
                if old_id:
                    try:
                        msg = await channel.fetch_message(int(old_id))
                        await msg.edit(embed=embed)
                    except:
                        msg = await channel.send(embed=embed)
                else:
                    msg = await channel.send(embed=embed)
                
                if msg:
                    s["last_msg_ids"][list_name] = msg.id
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"Error actualizando lista {list_name} en guild {guild_id}: {e}")

        self.bot.save_data()

    @tasks.loop(minutes=2)
    async def auto_tracker(self):
        """Bucle periódico para actualizar el status online."""
        await self.run_tracker()

    async def run_tracker(self):
        """Ejecuta una actualización completa del tracker."""
        try:
            async with aiohttp.ClientSession() as session:
                for gid in list(self.bot.db.keys()):
                    await self.update_guild_tracking(session, gid)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error en ejecución de tracking: {e}")

    @auto_tracker.before_loop
    async def before_auto_tracker(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setup_tracking", description="Vincula una lista a un canal para mostrar el status online")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tracking(self, interaction: discord.Interaction, lista: str, canal: discord.TextChannel):
        s = self.get_settings(interaction.guild_id)
        
        if "lists" not in s or lista not in s["lists"]:
            return await interaction.response.send_message(f"❌ La lista `{lista}` no existe. Créala primero con `/create_list`.", ephemeral=True)
            
        if "channels" not in s: s["channels"] = {}
        s["channels"][lista] = canal.id
        self.bot.save_data()
        
        await interaction.response.send_message(f"✅ Status online de `{lista}` configurado en {canal.mention}. Actualizando...")
        
        async with aiohttp.ClientSession() as session:
            await self.update_guild_tracking(session, str(interaction.guild_id))

async def setup(bot):
    await bot.add_cog(Tracking(bot))
