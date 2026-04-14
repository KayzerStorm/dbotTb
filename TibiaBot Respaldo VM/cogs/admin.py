import discord
from discord.ext import commands
from discord import app_commands
import logging

class Admin(commands.Cog):
    """Módulo central de administración y configuración de la base de datos."""
    def __init__(self, bot):
        self.bot = bot

    def get_settings(self, guild_id):
        """Obtiene o inicializa la configuración de una guild con un esquema unificado."""
        gid = str(guild_id)
        if gid not in self.bot.db:
            self.bot.db[gid] = {
                "world": "Antica", 
                "lists": {}, 
                "channels": {}, 
                "last_msg_ids": {}, 
                "guild_sync": {}, 
                "rashid_channel": None, 
                "last_rashid_message_id": None,
                "history": {}, 
                "alerts_enabled": False, 
                "alert_channel": None, 
                "alert_channel_config": {}, 
                "active_alert_lists": [],
                "active_lvltracker_lists": [],
                "claim_catalog_channel": None,
                "claim_status_channel": None,
                "last_claim_menu_id": None,
                "last_status_msg_id": None,
                "claims_active": {},
                "global_claim_duration": 120,
                "tracker_channel_id": None,
                "tracker_assigned_list": None,
                "level_tracker": {"data": {}, "last_msg_id": None},
                "highscore_channel": None,
                "highscore_list_target": None,
                "last_highscore_msg_id": None
            }
        
        # Asegurar que campos nuevos existan en guilds viejas (Migración automática)
        defaults = {
            "world": "Antica",
            "lists": {},
            "channels": {},
            "last_msg_ids": {},
            "history": {},
            "alerts_enabled": False,
            "alert_channel": None,
            "alert_channel_config": {},
            "active_alert_lists": [],
            "active_lvltracker_lists": [],
            "rashid_channel": None,
            "last_rashid_message_id": None,
            "claim_catalog_channel": None,
            "claim_status_channel": None,
            "last_claim_menu_id": None,
            "last_status_msg_id": None,
            "claims_active": {},
            "global_claim_duration": 120,
            "tracker_channel_id": None,
            "tracker_assigned_list": None,
            "level_tracker": {"data": {}, "last_msg_id": None},
            "highscore_channel": None,
            "highscore_list_target": None,
            "last_highscore_msg_id": None
        }
        
        modified = False
        for key, val in defaults.items():
            if key not in self.bot.db[gid]:
                self.bot.db[gid][key] = val
                modified = True
        
        if modified:
            self.bot.save_data()
                
        return self.bot.db[gid]

    # --- CONFIGURACIÓN GLOBAL ---

    @app_commands.command(name="set_world", description="Configura el mundo de Tibia para este servidor")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_world(self, interaction: discord.Interaction, mundo: str):
        s = self.get_settings(interaction.guild_id)
        s["world"] = mundo.capitalize()
        self.bot.save_data()
        await interaction.response.send_message(f"🌍 Mundo configurado: **{s['world']}**.")

    @app_commands.command(name="reload", description="Recarga un módulo (Cog) sin apagar el bot")
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction, modulo: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(f"cogs.{modulo.lower()}")
            await self.bot.tree.sync()
            await interaction.followup.send(f"✅ Módulo `{modulo}` recargado correctamente.")
        except Exception as e:
            await interaction.followup.send(f"❌ Error al recargar: `{e}`")

    # --- GESTIÓN DE ALERTAS (NIVEL Y MUERTE) ---

    @app_commands.command(name="setup_alerts", description="Configura el canal principal y activa las alertas de nivel/muerte")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_alerts(self, interaction: discord.Interaction, canal: discord.TextChannel, activar: bool):
        s = self.get_settings(interaction.guild_id)
        s["alert_channel"] = canal.id
        s["alerts_enabled"] = activar
        self.bot.save_data()
        estado = "ACTIVADAS" if activar else "DESACTIVADAS"
        await interaction.response.send_message(f"📢 Alertas de Nivel/Muerte {estado} en {canal.mention}.")

    @app_commands.command(name="link_list_alerts", description="Vincula una lista específica a su propio canal de alertas")
    @app_commands.checks.has_permissions(administrator=True)
    async def link_list_alerts(self, interaction: discord.Interaction, lista: str, canal: discord.TextChannel):
        s = self.get_settings(interaction.guild_id)
        if lista not in s["lists"]:
            return await interaction.response.send_message(f"❌ La lista `{lista}` no existe.")
        
        s["alert_channel_config"][lista] = canal.id
        self.bot.save_data()
        await interaction.response.send_message(f"🔔 Alertas de la lista `{lista}` vinculadas a {canal.mention}.")

    @app_commands.command(name="enable_alerts_for_list", description="Activa el rastreo de alertas para una lista específica")
    @app_commands.checks.has_permissions(administrator=True)
    async def enable_alerts_for_list(self, interaction: discord.Interaction, lista: str):
        s = self.get_settings(interaction.guild_id)
        if lista not in s["lists"]:
            return await interaction.response.send_message(f"❌ La lista `{lista}` no existe.", ephemeral=True)
        
        if "active_alert_lists" not in s: s["active_alert_lists"] = []
        
        if lista not in s["active_alert_lists"]:
            s["active_alert_lists"].append(lista)
            self.bot.save_data()
            await interaction.response.send_message(f"✅ Alertas **ACTIVADAS** para la lista `{lista}`.")
        else:
            await interaction.response.send_message(f"⚠️ Las alertas ya están activas para `{lista}`.", ephemeral=True)

    @app_commands.command(name="disable_alerts_for_list", description="Desactiva el rastreo de alertas para una lista específica")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_alerts_for_list(self, interaction: discord.Interaction, lista: str):
        s = self.get_settings(interaction.guild_id)
        if "active_alert_lists" in s and lista in s["active_alert_lists"]:
            s["active_alert_lists"].remove(lista)
            self.bot.save_data()
            await interaction.response.send_message(f"🛑 Alertas **DESACTIVADAS** para la lista `{lista}`.")
        else:
            await interaction.response.send_message(f"⚠️ La lista `{lista}` no estaba siendo rastreada.", ephemeral=True)

    @app_commands.command(name="enable_lvltracker_for_list", description="Activa el ranking diario de niveles para una lista específica")
    @app_commands.checks.has_permissions(administrator=True)
    async def enable_lvltracker_for_list(self, interaction: discord.Interaction, lista: str):
        s = self.get_settings(interaction.guild_id)
        if lista not in s["lists"]:
            return await interaction.response.send_message(f"❌ La lista `{lista}` no existe.", ephemeral=True)
        
        if "active_lvltracker_lists" not in s: s["active_lvltracker_lists"] = []
        
        if lista not in s["active_lvltracker_lists"]:
            s["active_lvltracker_lists"].append(lista)
            self.bot.save_data()
            await interaction.response.send_message(f"📈 LvlTracker **ACTIVADO** para la lista `{lista}`.")
        else:
            await interaction.response.send_message(f"⚠️ El LvlTracker ya está activo para `{lista}`.", ephemeral=True)

    @app_commands.command(name="disable_lvltracker_for_list", description="Desactiva el ranking diario de niveles para una lista específica")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_lvltracker_for_list(self, interaction: discord.Interaction, lista: str):
        s = self.get_settings(interaction.guild_id)
        if "active_lvltracker_lists" in s and lista in s["active_lvltracker_lists"]:
            s["active_lvltracker_lists"].remove(lista)
            self.bot.save_data()
            await interaction.response.send_message(f"🛑 LvlTracker **DESACTIVADO** para la lista `{lista}`.")
        else:
            await interaction.response.send_message(f"⚠️ La lista `{lista}` no tenía el LvlTracker activo.", ephemeral=True)

    # --- GESTIÓN DE LISTAS ---

    @app_commands.command(name="create_list", description="Crea una nueva lista de tracking")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_list(self, interaction: discord.Interaction, nombre: str):
        s = self.get_settings(interaction.guild_id)
        if nombre in s["lists"]:
            return await interaction.response.send_message(f"⚠️ La lista `{nombre}` ya existe.")
        s["lists"][nombre] = []
        self.bot.save_data()
        await interaction.response.send_message(f"✅ Lista `{nombre}` creada.")

    @app_commands.command(name="delete_list", description="Elimina una lista completa y sus configuraciones")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_list(self, interaction: discord.Interaction, nombre: str):
        s = self.get_settings(interaction.guild_id)
        if nombre in s["lists"]:
            del s["lists"][nombre]
            # Limpiar vínculos de canales si existen
            if nombre in s["channels"]: del s["channels"][nombre]
            if nombre in s["alert_channel_config"]: del s["alert_channel_config"][nombre]
            if nombre in s["last_msg_ids"]: del s["last_msg_ids"][nombre]
            
            self.bot.save_data()
            await interaction.response.send_message(f"🗑️ Lista `{nombre}` eliminada por completo.")
        else:
            await interaction.response.send_message("❌ Esa lista no existe.")

    @app_commands.command(name="show_lists", description="Muestra todas las listas creadas y su cantidad de jugadores")
    async def show_lists(self, interaction: discord.Interaction):
        s = self.get_settings(interaction.guild_id)
        if not s["lists"]:
            return await interaction.response.send_message("No hay listas creadas.")
        out = [f"🔹 `{n}`: {len(p)} personajes" for n, p in s["lists"].items()]
        await interaction.response.send_message("**Listas configuradas:**\n" + "\n".join(out))

    @app_commands.command(name="list_players", description="Muestra todos los personajes dentro de una lista específica")
    @app_commands.describe(lista="El nombre de la lista a consultar")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_players(self, interaction: discord.Interaction, lista: str):
        s = self.get_settings(interaction.guild_id)
        if lista not in s["lists"]:
            return await interaction.response.send_message(f"❌ La lista `{lista}` no existe.", ephemeral=True)
        
        players = s["lists"][lista]
        if not players:
            return await interaction.response.send_message(f"📂 La lista `{lista}` está vacía.", ephemeral=True)
        
        # Dividir en bloques si hay muchos jugadores (Discord tiene límite de 2000 caracteres)
        players_sorted = sorted(players)
        chunks = [players_sorted[i:i + 50] for i in range(0, len(players_sorted), 50)]
        
        await interaction.response.send_message(f"📋 **Personajes en la lista `{lista}` ({len(players)} total):**", ephemeral=True)
        for chunk in chunks:
            await interaction.followup.send(f"```\n" + "\n".join(chunk) + "\n```", ephemeral=True)

    @app_commands.command(name="unlink_highscores", description="Desvincula y limpia el canal del Hall of Fame")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlink_highscores(self, interaction: discord.Interaction):
        s = self.get_settings(interaction.guild_id)
        chan_id = s.get("highscore_channel")
        
        if not chan_id:
            return await interaction.response.send_message("⚠️ No hay un canal de Highscores configurado.", ephemeral=True)
        
        # Intentar borrar el último mensaje enviado
        msg_id = s.get("last_highscore_msg_id")
        if msg_id:
            try:
                channel = self.bot.get_channel(int(chan_id))
                if channel:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.delete()
            except: pass
        
        # Limpiar configuración
        s["highscore_channel"] = None
        s["highscore_list_target"] = None
        s["last_highscore_msg_id"] = None
        self.bot.save_data()
        
        await interaction.response.send_message("✅ Hall of Fame desvinculado y mensaje eliminado correctamente.")

    # --- GESTIÓN DE JUGADORES ---

    @app_commands.command(name="add_player", description="Añade un jugador a una lista específica")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_player(self, interaction: discord.Interaction, lista: str, nombre: str):
        s = self.get_settings(interaction.guild_id)
        if lista not in s["lists"]: return await interaction.response.send_message("❌ La lista no existe.")
        
        nombre_cap = nombre.title()
        if nombre_cap not in s["lists"][lista]: 
            s["lists"][lista].append(nombre_cap)
            self.bot.save_data()
            await interaction.response.send_message(f"✅ **{nombre_cap}** añadido a `{lista}`.")
        else:
            await interaction.response.send_message(f"⚠️ **{nombre_cap}** ya está en esa lista.")

    @app_commands.command(name="delete_player", description="Borra un jugador de una lista")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_player(self, interaction: discord.Interaction, lista: str, nombre: str):
        s = self.get_settings(interaction.guild_id)
        nombre_cap = nombre.title()
        if lista in s["lists"] and nombre_cap in s["lists"][lista]:
            s["lists"][lista].remove(nombre_cap)
            self.bot.save_data()
            await interaction.response.send_message(f"🗑️ **{nombre_cap}** eliminado de `{lista}`.")
        else:
            await interaction.response.send_message(f"❌ **{nombre_cap}** no está en la lista `{lista}`.")

    @app_commands.command(name="unlink_list_from_channel", description="Desvincula una lista de su canal de status y borra el mensaje previo")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlink_list_from_channel(self, interaction: discord.Interaction, lista: str):
        await interaction.response.defer(ephemeral=True)
        s = self.get_settings(interaction.guild_id)
        
        msg_borrado = False
        if "channels" in s and lista in s["channels"]:
            channel_id = s["channels"][lista]
            
            # Intentar borrar el último mensaje enviado
            if "last_msg_ids" in s and lista in s["last_msg_ids"]:
                msg_id = s["last_msg_ids"][lista]
                try:
                    channel = self.bot.get_channel(int(channel_id))
                    if channel:
                        msg = await channel.fetch_message(int(msg_id))
                        await msg.delete()
                        msg_borrado = True
                except Exception as e:
                    logging.warning(f"No se pudo borrar el mensaje previo de {lista}: {e}")
                
                del s["last_msg_ids"][lista]
            
            del s["channels"][lista]
            self.bot.save_data()
            
            txt = f"🔓 Lista `{lista}` desvinculada correctamente."
            if msg_borrado:
                txt += " El mensaje de status previo ha sido eliminado del canal."
            else:
                txt += " (No se encontró o no se pudo borrar el mensaje previo en el canal)."
                
            await interaction.followup.send(txt)
        else:
            await interaction.followup.send(f"⚠️ La lista `{lista}` no tiene ningún canal vinculado.")

async def setup(bot):
    await bot.add_cog(Admin(bot))
