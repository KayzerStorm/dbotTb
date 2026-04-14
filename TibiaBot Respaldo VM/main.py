import discord
from discord.ext import commands
import json
import os
import logging
import asyncio

# Configuración de logs básica
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TibiaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        
        self.db_file = "tibia_bot_final.json"
        self.db = self.load_data()
        self.spawns = self.load_spawns()
        self.last_online_state = {}

    def load_data(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error cargando base de datos: {e}")
                return {}
        return {}

    def load_spawns(self):
        if os.path.exists("spawns.json"):
            try:
                with open("spawns.json", 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error cargando spawns: {e}")
        return {"1": {"name": "Cobras", "min_lvl": 400, "duration": 120, "desc": "Gaffir"}}

    def save_data(self):
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.db, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error guardando base de datos: {e}")

    async def setup_hook(self):
        print("\n" + "="*50)
        print("⚡ PROTOCOLOS DE INICIO: ASCENTION GUILD SYSTEM ⚡")
        print("="*50)
        
        # Cargar módulos automáticamente desde la carpeta /cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"📦 [MODULO] {filename[:-3].upper()} cargado.")
                except Exception as e:
                    print(f"❌ [ERROR] No se pudo cargar {filename}: {e}")

        await self.tree.sync()
        print("⚔️ [COMANDOS] Slash Commands sincronizados.")

    async def on_ready(self):
        print(f"✅ [ONLINE] Bot activo como: {self.user}")
        print("-" * 50)
        
        # Limpieza y republicación automática al inicio
        print("🧹 [LIMPIEZA] Iniciando purga de canales configurados...")
        for gid in list(self.db.keys()):
            try:
                await self.clean_and_repost_all(gid)
            except Exception as e:
                logging.error(f"Error en limpieza inicial de guild {gid}: {e}")
        print("✨ [LIMPIEZA] Canales purgados y actualizados.")
        print("-" * 50)

    async def clean_and_repost_all(self, guild_id):
        """Limpia los canales configurados y fuerza la republicación de embeds."""
        admin_cog = self.get_cog("Admin")
        if not admin_cog: return
        
        s = admin_cog.get_settings(guild_id)
        canales_a_limpiar = set()
        
        # Recopilar todos los canales configurados en este servidor
        if s.get("channels"): canales_a_limpiar.update(s["channels"].values())
        if s.get("rashid_channel"): canales_a_limpiar.add(s["rashid_channel"])
        if s.get("claim_catalog_channel"): canales_a_limpiar.add(s["claim_catalog_channel"])
        if s.get("claim_status_channel"): canales_a_limpiar.add(s["claim_status_channel"])
        if s.get("tracker_channel_id"): canales_a_limpiar.add(s["tracker_channel_id"])
        if s.get("highscore_channel"): canales_a_limpiar.add(s["highscore_channel"])
        
        for cid in canales_a_limpiar:
            try:
                channel = self.get_channel(int(cid))
                if channel:
                    # Borrar todos los mensajes del canal (propios y de usuarios)
                    await channel.purge(limit=100)
                    # Resetear IDs de mensajes guardados para forzar republicación
                    # El purge ya borró los mensajes, así que solo reseteamos las referencias en la BD
                    
                    # Limpiar referencias de IDs en la base de datos para forzar envío de nuevos mensajes
                    if s.get("last_msg_ids"):
                        for k in list(s["last_msg_ids"].keys()):
                            if s["last_msg_ids"][k] and s.get("channels", {}).get(k) == cid:
                                s["last_msg_ids"][k] = None
                    
                    if s.get("last_rashid_message_id") and s.get("rashid_channel") == cid:
                        s["last_rashid_message_id"] = None
                    if s.get("last_claim_menu_id") and s.get("claim_catalog_channel") == cid:
                        s["last_claim_menu_id"] = None
                    if s.get("last_status_msg_id") and s.get("claim_status_channel") == cid:
                        s["last_status_msg_id"] = None
                    if s.get("level_tracker", {}).get("last_msg_id") and s.get("tracker_channel_id") == cid:
                        s["level_tracker"]["last_msg_id"] = None
                    if s.get("last_highscore_msg_id") and s.get("highscore_channel") == cid:
                        s["last_highscore_msg_id"] = None
            except Exception as e:
                logging.warning(f"No se pudo limpiar el canal {cid}: {e}")

        self.save_data()
        
        # Forzar republicación en los módulos correspondientes
        # (Se activarán automáticamente por sus bucles, pero podemos forzar algunos críticos)
        tracking_cog = self.get_cog("Tracking")
        if tracking_cog:
            asyncio.create_task(tracking_cog.run_tracker())
            
        claims_cog = self.get_cog("Claims")
        if claims_cog:
            await claims_cog.update_claim_menu(guild_id)
            
        rashid_cog = self.get_cog("Rashid")
        if rashid_cog:
            await rashid_cog.send_rashid_embed(guild_id)

bot = TibiaBot()
# Reemplaza 'TU_TOKEN_AQUI' con el token real de tu bot de Discord
if __name__ == "__main__":
    bot.run("DISCORD TOKEN")
