import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime
import logging
from collections import defaultdict
import time

class Alerts(commands.Cog):
    """Modulo para notificaciones de muertes y subidas de nivel con soporte multicanal - Optimizado para tiempo real"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://api.tibiadata.com/v4/character/"
        self.session = None
        self.rate_limiter = asyncio.Semaphore(10)  # 10 requests concurrentes
        self.request_timestamps = defaultdict(list)  # Para rate limiting por dominio
        self.cache = {}  # Cache simple en memoria
        self.cache_ttl = 30  # Cache de 30 segundos
        self.check_alerts.start()
        self.last_full_check = 0
        self.full_check_interval = 120  # Check completo cada 2 minutos
        
    def cog_unload(self):
        self.check_alerts.cancel()
        if self.session:
            asyncio.create_task(self.session.close())
    
    async def cog_load(self):
        self.session = aiohttp.ClientSession()
    
    def get_settings(self, guild_id):
        admin_cog = self.bot.get_cog("Admin")
        if admin_cog:
            return admin_cog.get_settings(guild_id)
        return self.bot.db.get(str(guild_id), {})
    
    async def rate_limit_check(self, domain="api.tibiadata.com"):
        """Control de rate limiting adaptativo"""
        now = time.time()
        # Limpiar timestamps viejos (último segundo)
        self.request_timestamps[domain] = [ts for ts in self.request_timestamps[domain] if now - ts < 1]
        
        # Máximo 5 requests por segundo (ajustable)
        if len(self.request_timestamps[domain]) >= 5:
            wait_time = 1 - (now - self.request_timestamps[domain][0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        self.request_timestamps[domain].append(now)
    
    def get_cached(self, key):
        """Obtener datos del cache"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
            else:
                del self.cache[key]
        return None
    
    def set_cached(self, key, data):
        """Guardar datos en cache"""
        self.cache[key] = (data, time.time())
    
    @tasks.loop(seconds=15)  # Intervalo reducido a 15 segundos para mejor respuesta
    async def check_alerts(self):
        """Bucle principal optimizado con polling inteligente y procesamiento paralelo"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            current_time = time.time()
            is_full_check = (current_time - self.last_full_check) >= self.full_check_interval
            
            # Colección de tareas para procesamiento paralelo
            all_tasks = []
            
            for gid in list(self.bot.db.keys()):
                s = self.get_settings(gid)
                if not s.get("alerts_enabled"):
                    continue
                
                active_lists = s.get("active_alert_lists", [])
                if not active_lists:
                    continue
                
                # Unificar jugadores unicos de listas activas
                all_players = set()
                for lname in active_lists:
                    if lname in s.get("lists", {}):
                        all_players.update(s["lists"][lname])
                
                if "history" not in s:
                    s["history"] = {}
                
                # Para cada personaje, crear tarea de verificación
                for p_name in all_players:
                    # Solo verificar personajes prioritarios en checks rápidos
                    if not is_full_check:
                        # En checks rápidos, solo verificar personajes con cambios recientes
                        history = s["history"].get(p_name, {})
                        last_change = history.get("last_change", 0)
                        if current_time - last_change > 300:  # Si no ha cambiado en 5 minutos
                            continue
                    
                    task = self.check_character(p_name, gid, s, is_full_check)
                    all_tasks.append(task)
            
            # Ejecutar todas las verificaciones en paralelo
            if all_tasks:
                await asyncio.gather(*all_tasks, return_exceptions=True)
                self.bot.save_data()
            
            if is_full_check:
                self.last_full_check = current_time
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error en el bucle de alertas: {e}")
    
    async def check_character(self, p_name, guild_id, settings, is_full_check=False):
        """Verifica un personaje individual con rate limiting y cache"""
        async with self.rate_limiter:
            try:
                # Verificar cache
                cache_key = f"{p_name}_{guild_id}"
                cached_data = self.get_cached(cache_key)
                
                # Rate limiting
                await self.rate_limit_check()
                
                url = f"{self.api_url}{p_name.replace(' ', '%20')}"
                async with self.session.get(url, timeout=8) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        char_data = data.get("character", {})
                        char = char_data.get("character", {})
                        deaths = char_data.get("deaths", [])
                        
                        if not char:
                            return
                        
                        # Si hay datos en cache y no ha cambiado, solo actualizar timestamp
                        if cached_data and not is_full_check:
                            cached_char, cached_deaths = cached_data
                            if cached_char["level"] == char["level"] and cached_deaths == len(deaths):
                                # Actualizar timestamp de cache
                                self.set_cached(cache_key, (char, len(deaths)))
                                return
                        
                        # Guardar en cache
                        self.set_cached(cache_key, (char, len(deaths)))
                        
                        history = settings["history"]
                        
                        # Si es nuevo en el historial, registrar y continuar
                        if p_name not in history:
                            history[p_name] = {
                                "lvl": char["level"], 
                                "deaths": len(deaths),
                                "last_change": time.time()
                            }
                            return
                        
                        h = history[p_name]
                        has_changes = False
                        
                        # Determinar canal de destino
                        target_id = settings.get("alert_channel")
                        list_found = "Global"
                        for lname, players in settings.get("lists", {}).items():
                            if p_name in players:
                                list_found = lname
                                if settings.get("alert_channel_config", {}).get(lname):
                                    target_id = settings["alert_channel_config"][lname]
                                    break
                        
                        if not target_id:
                            return
                        
                        channel = self.bot.get_channel(int(target_id))
                        if not channel:
                            return
                        
                        # 1. Detección de Nivel
                        if char["level"] > h["lvl"]:
                            embed = discord.Embed(title="🚀 ¡Nivel Subido!", color=0x2ecc71)
                            embed.description = f"**{p_name}** ha subido del nivel **{h['lvl']}** → **{char['level']}**"
                            embed.set_footer(text=f"Lista: {list_found}")
                            await channel.send(embed=embed)
                            has_changes = True
                        elif char["level"] < h["lvl"]:
                            embed = discord.Embed(title="📉 ¡Nivel Bajado!", color=0xe74c3c)
                            embed.description = f"**{p_name}** ha bajado del nivel **{h['lvl']}** → **{char['level']}**"
                            embed.set_footer(text=f"Lista: {list_found}")
                            await channel.send(embed=embed)
                            has_changes = True
                        
                        # 2. Detección de Muerte
                        if len(deaths) > h["deaths"]:
                            new_death = deaths[0]
                            reason = new_death.get("reason", "causas desconocidas")
                            
                            embed = discord.Embed(title="💀 ¡Muerte Detectada!", color=0x000000)
                            embed.description = f"**{p_name}** (Lvl {char['level']}) murió por {reason}"
                            embed.set_footer(text=f"Lista: {list_found} | {new_death.get('time', 'Reciente')}")
                            await channel.send(embed=embed)
                            has_changes = True
                        
                        # Actualizar historial
                        if has_changes or char["level"] != h["lvl"] or len(deaths) != h["deaths"]:
                            history[p_name] = {
                                "lvl": char["level"], 
                                "deaths": len(deaths),
                                "last_change": time.time()
                            }
                        else:
                            # Actualizar solo el timestamp si no hay cambios
                            history[p_name]["last_change"] = time.time()
                        
            except asyncio.TimeoutError:
                logging.warning(f"Timeout para {p_name}")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"Error procesando alertas para {p_name} en guild {guild_id}: {e}")
    
    @check_alerts.before_loop
    async def before_check_alerts(self):
        await self.bot.wait_until_ready()
        # Pequeña espera inicial para evitar sobrecarga
        await asyncio.sleep(5)
    
    @app_commands.command(name="test_alerts", description="Envia un mensaje de prueba para verificar la configuracion de alertas")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_alerts(self, interaction: discord.Interaction):
        s = self.get_settings(interaction.guild_id)
        if not s.get("alerts_enabled"):
            return await interaction.response.send_message("⚠️ Las alertas estan **DESACTIVADAS** globalmente. Activalas con `/setup_alerts`.", ephemeral=True)
        
        target_id = s.get("alert_channel")
        if not target_id:
            return await interaction.response.send_message("❌ No hay un canal de alertas configurado. Usa `/setup_alerts`.", ephemeral=True)
        
        chan = self.bot.get_channel(int(target_id))
        if not chan:
            return await interaction.response.send_message(f"❌ No puedo encontrar el canal con ID `{target_id}`. Verifica los permisos del bot.", ephemeral=True)
        
        try:
            embed = discord.Embed(title="🧪 Prueba de Alertas", color=0x3498db)
            embed.description = "Si puedes ver este mensaje, el sistema de alertas esta **correctamente configurado** y el bot tiene permisos de envio."
            embed.add_field(name="Canal Global", value=chan.mention, inline=True)
            embed.add_field(name="Intervalo de verificación", value="15 segundos (optimizado)", inline=True)
            
            # Verificar canales especificos de listas
            list_configs = s.get("alert_channel_config", {})
            if list_configs:
                details = ""
                for lname, cid in list_configs.items():
                    l_chan = self.bot.get_channel(int(cid))
                    details += f"🔹 `{lname}` -> {l_chan.mention if l_chan else 'ID Invalido'}\n"
                embed.add_field(name="Canales por Lista", value=details, inline=False)
            
            await chan.send(embed=embed)
            await interaction.response.send_message(f"✅ Mensaje de prueba enviado a {chan.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al enviar mensaje de prueba: `{e}`", ephemeral=True)
    
    @app_commands.command(name="alerts_status", description="Muestra el estado actual del sistema de alertas")
    @app_commands.checks.has_permissions(administrator=True)
    async def alerts_status(self, interaction: discord.Interaction):
        """Comando adicional para ver el estado del sistema"""
        s = self.get_settings(interaction.guild_id)
        
        embed = discord.Embed(title="📊 Estado del Sistema de Alertas", color=0x3498db)
        
        # Estado general
        enabled = s.get("alerts_enabled", False)
        embed.add_field(name="Estado", value="✅ Activado" if enabled else "❌ Desactivado", inline=True)
        
        if enabled:
            # Información de configuración
            channel_id = s.get("alert_channel")
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                embed.add_field(name="Canal Global", value=channel.mention if channel else "No encontrado", inline=True)
            
            # Listas activas
            active_lists = s.get("active_alert_lists", [])
            if active_lists:
                lists_text = "\n".join([f"🔹 {l}" for l in active_lists])
                embed.add_field(name="Listas Activas", value=lists_text, inline=False)
            
            # Estadísticas
            total_players = 0
            for lname in active_lists:
                if lname in s.get("lists", {}):
                    total_players += len(s["lists"][lname])
            
            embed.add_field(name="Personajes Monitoreados", value=str(total_players), inline=True)
            embed.add_field(name="Intervalo de Verificación", value="15 segundos", inline=True)
            
            # Cache info
            cache_size = len(self.cache)
            embed.add_field(name="Cache Activo", value=f"{cache_size} personajes", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Alerts(bot))