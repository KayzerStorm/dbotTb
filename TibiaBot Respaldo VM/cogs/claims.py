import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime, timezone
import logging

class Claims(commands.Cog):
    """Módulo para la gestión de reservas de Spawns (Claims) con sistema de fila."""
    def __init__(self, bot):
        self.bot = bot
        self.claim_expiration_checker.start()

    def cog_unload(self):
        self.claim_expiration_checker.cancel()

    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})

    async def update_claim_menu(self, guild_id):
        """Actualiza tanto el catálogo de spawns como el estado de hunting."""
        s = self.get_settings(guild_id)
        cat_chan_id = s.get("claim_catalog_channel")
        stat_chan_id = s.get("claim_status_channel")
        
        # 1. Actualizar Catálogo de Spawns
        if cat_chan_id:
            try:
                chan = self.bot.get_channel(int(cat_chan_id))
                if chan:
                    embed = discord.Embed(title="📍 LISTADO DE SPAWNS", description="Usa `/claim [id]` para reservar.", color=0x3498db)
                    for sid, info in self.bot.spawns.items():
                        embed.add_field(name=f"#{sid} - {info['name']}", value=f"Lvl: `{info['min_lvl']}+` | {info['desc']}", inline=False)
                    
                    old_id = s.get("last_claim_menu_id")
                    msg = None
                    if old_id:
                        try:
                            msg = await chan.fetch_message(int(old_id))
                            await msg.edit(embed=embed)
                        except:
                            msg = await chan.send(embed=embed)
                    else:
                        msg = await chan.send(embed=embed)
                    
                    if msg: s["last_claim_menu_id"] = msg.id
            except Exception as e:
                logging.error(f"Error actualizando catálogo en guild {guild_id}: {e}")

        # 2. Actualizar Estado de Hunting
        if stat_chan_id:
            try:
                chan = self.bot.get_channel(int(stat_chan_id))
                if chan:
                    embed = discord.Embed(title="🔴 ESTADO DE HUNTING", color=0xe74c3c)
                    now = datetime.now(timezone.utc).timestamp()
                    found = False
                    
                    active_claims = s.get("claims_active", {})
                    for sid, data in active_claims.items():
                        if data.get("owner"):
                            found = True
                            expires = data.get("expires", 0)
                            rem = max(0, int((expires - now) / 60))
                            
                            val = f"👤 **Dueño:** <@{data['owner']}>\n⏱️ **Resta:** `{rem} min`"
                            if data.get("next"): 
                                val += f"\n⌛ **En fila:** <@{data['next']}>"
                            
                            spawn_name = self.bot.spawns.get(sid, {}).get("name", f"Spawn #{sid}")
                            embed.add_field(name=f"📍 {spawn_name}", value=val, inline=False)
                    
                    if not found: 
                        embed.description = "✅ Todo libre."
                        embed.color = 0x2ecc71
                    
                    embed.set_footer(text=f"Última actualización: {datetime.now().strftime('%H:%M:%S')}")
                    
                    old_stat_id = s.get("last_status_msg_id")
                    msg_stat = None
                    if old_stat_id:
                        try:
                            msg_stat = await chan.fetch_message(int(old_stat_id))
                            await msg_stat.edit(embed=embed)
                        except:
                            msg_stat = await chan.send(embed=embed)
                    else:
                        msg_stat = await chan.send(embed=embed)
                    
                    if msg_stat: s["last_status_msg_id"] = msg_stat.id
            except Exception as e:
                logging.error(f"Error actualizando status en guild {guild_id}: {e}")
        
        self.bot.save_data()

    @tasks.loop(minutes=1)
    async def claim_expiration_checker(self):
        """Bucle de fondo para expirar claims y pasar turnos."""
        try:
            now = datetime.now(timezone.utc).timestamp()
            for gid in list(self.bot.db.keys()):
                s = self.get_settings(gid)
                changed = False
                active_claims = s.get("claims_active", {})
                
                for sid, data in list(active_claims.items()):
                    if data.get("owner") and now >= data.get("expires", 0):
                        if data.get("next"):
                            # Pasar turno al siguiente en fila
                            data["owner"] = data["next"]
                            data["next"] = None
                            duration = self.bot.spawns.get(sid, {}).get("duration", s.get("global_claim_duration", 120))
                            data["expires"] = now + (duration * 60)
                            
                            try: 
                                user = await self.bot.fetch_user(data["owner"])
                                spawn_name = self.bot.spawns.get(sid, {}).get("name", "un spawn")
                                await user.send(f"🔔 ¡Es tu turno en **{spawn_name}**! Tienes {duration} minutos.")
                            except: 
                                pass
                        else: 
                            # Liberar spawn
                            data["owner"] = None
                            data["expires"] = 0
                        changed = True
                
                if changed: 
                    await self.update_claim_menu(gid)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error en claim_expiration_checker: {e}")

    @claim_expiration_checker.before_loop
    async def before_claim_checker(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="claim", description="Reserva un spawn o entra en fila")
    @app_commands.describe(id="El ID numérico del spawn (ej: 1)")
    async def claim(self, interaction: discord.Interaction, id: str):
        if id not in self.bot.spawns: 
            return await interaction.response.send_message("❌ ID de spawn inválido. Consulta el catálogo.", ephemeral=True)
        
        s = self.get_settings(interaction.guild_id)
        uid = interaction.user.id
        active_claims = s.get("claims_active", {})
        
        # Verificar si el usuario ya tiene una reserva activa en cualquier spawn
        for sid, data in active_claims.items():
            if data.get("owner") == uid or data.get("next") == uid: 
                return await interaction.response.send_message("⚠️ Ya tienes una reserva activa o estás en fila para otro spawn.", ephemeral=True)
        
        if id not in active_claims: 
            active_claims[id] = {"owner": None, "next": None, "expires": 0}
        
        c = active_claims[id]
        now = datetime.now(timezone.utc).timestamp()
        duration = self.bot.spawns[id].get("duration", s.get("global_claim_duration", 120))
        
        if not c.get("owner"):
            c["owner"] = uid
            c["expires"] = now + (duration * 60)
            await interaction.response.send_message(f"✅ Has reclamado **{self.bot.spawns[id]['name']}** por {duration} minutos.", ephemeral=True)
        elif not c.get("next"):
            c["next"] = uid
            await interaction.response.send_message(f"👤 Has entrado en fila para **{self.bot.spawns[id]['name']}**. Te avisaré cuando sea tu turno.", ephemeral=True)
        else: 
            return await interaction.response.send_message("❌ Este spawn y su fila ya están llenos.", ephemeral=True)
        
        await self.update_claim_menu(interaction.guild_id)

    @app_commands.command(name="unclaim", description="Libera tu reserva actual")
    async def unclaim(self, interaction: discord.Interaction):
        s = self.get_settings(interaction.guild_id)
        uid = interaction.user.id
        active_claims = s.get("claims_active", {})
        
        found_sid = None
        for sid, data in active_claims.items():
            if data.get("owner") == uid:
                found_sid = sid
                # Forzar expiración inmediata para que el checker pase el turno
                data["expires"] = 0
                break
            elif data.get("next") == uid:
                found_sid = sid
                data["next"] = None
                break
        
        if found_sid:
            await interaction.response.send_message(f"🔓 Has liberado tu espacio en **{self.bot.spawns[found_sid]['name']}**.", ephemeral=True)
            await self.update_claim_menu(interaction.guild_id)
        else:
            await interaction.response.send_message("⚠️ No tienes ninguna reserva activa.", ephemeral=True)

    @app_commands.command(name="force_unclaim", description="Libera forzosamente un spawn (Solo Administradores)")
    @app_commands.describe(id="El ID numérico del spawn a liberar")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_unclaim(self, interaction: discord.Interaction, id: str):
        s = self.get_settings(interaction.guild_id)
        active_claims = s.get("claims_active", {})
        
        if id not in active_claims or not active_claims[id].get("owner"):
            return await interaction.response.send_message(f"⚠️ El spawn `{id}` no tiene ninguna reserva activa.", ephemeral=True)
        
        spawn_name = self.bot.spawns.get(id, {}).get("name", f"Spawn #{id}")
        
        # Forzar expiración inmediata para que el checker pase el turno o libere
        active_claims[id]["expires"] = 0
        self.bot.save_data()
        
        await interaction.response.send_message(f"🔨 **ADMIN:** Has liberado forzosamente el spawn **{spawn_name}**.")
        await self.update_claim_menu(interaction.guild_id)

    @app_commands.command(name="setup_claims", description="Configura los canales para el catálogo y el estado de hunting")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_claims(self, interaction: discord.Interaction, catalogo: discord.TextChannel, estado: discord.TextChannel):
        s = self.get_settings(interaction.guild_id)
        s["claim_catalog_channel"] = catalogo.id
        s["claim_status_channel"] = estado.id
        self.bot.save_data()
        
        await interaction.response.send_message(f"⚙️ Sistema de Claims configurado.\nCatálogo: {catalogo.mention}\nEstado: {estado.mention}")
        await self.update_claim_menu(interaction.guild_id)

async def setup(bot):
    await bot.add_cog(Claims(bot))
