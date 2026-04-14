import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio

class Refresh(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = "channel_config.json"
        # Nombres de referencia para buscar si no hay IDs guardados
        self.CHANNEL_NAMES = {
            "rashid": "rashid-location",
            "alertas": "alertas-tibia",
            "listas": "listas-seguimiento"
        }
        # Diccionario para cargar los IDs de memoria
        self.saved_ids = self.load_config()

    def load_config(self):
        """Carga los IDs guardados desde el archivo JSON."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error al cargar config: {e}")
        return {}

    def save_config(self, data):
        """Guarda los IDs encontrados en el archivo JSON."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error al guardar config: {e}")

    def register_channel(self, key, channel_id):
        """
        Método público para que otros módulos registren su canal.
        Uso desde otro Cog: self.bot.get_cog('Refresh').register_channel('rashid', interaction.channel.id)
        """
        if key in self.CHANNEL_NAMES:
            self.saved_ids[key] = str(channel_id)
            self.save_config(self.saved_ids)
            return True
        return False

    async def get_target_channel(self, guild, key):
        """Busca el canal usando el ID guardado o, si no existe, por su nombre."""
        # 1. Intentar por ID guardado
        saved_id = self.saved_ids.get(key)
        if saved_id:
            channel = guild.get_channel(int(saved_id))
            if channel:
                return channel

        # 2. Si no hay ID o el canal ya no existe, buscar por nombre
        target_name = self.CHANNEL_NAMES.get(key)
        channel = discord.utils.get(guild.text_channels, name=target_name)
        
        if channel:
            # Guardar el nuevo ID encontrado para la próxima vez
            self.saved_ids[key] = str(channel.id)
            self.save_config(self.saved_ids)
            return channel
            
        return None

    async def clear_channel(self, channel):
        """Borra los mensajes de un canal (límite 100)."""
        if not isinstance(channel, discord.TextChannel):
            return 0
        try:
            deleted = await channel.purge(limit=100)
            return len(deleted)
        except Exception as e:
            print(f"Error limpiando canal {channel.name}: {e}")
            return 0

    @app_commands.command(name="refresh", description="Limpia y republica info (con memoria de canales)")
    @app_commands.checks.has_permissions(administrator=True)
    async def refresh(self, interaction: discord.Interaction):
        """Comando que refresca los canales y guarda su configuración."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            return await interaction.followup.send("❌ Solo disponible en servidores.")

        results = []
        
        for key in self.CHANNEL_NAMES.keys():
            channel = await self.get_target_channel(interaction.guild, key)
            
            if not channel:
                results.append(f"❌ No se encontró el canal para `{key}` (buscado por nombre/memoria).")
                continue

            # Limpiar canal
            await self.clear_channel(channel)

            # Republicar (Lógica de tus módulos)
            try:
                if key == "rashid":
                    rashid_cog = self.bot.get_cog("Rashid")
                    if rashid_cog:
                        # Opcional: registrar el canal actual antes de publicar
                        self.register_channel("rashid", channel.id)
                        # await rashid_cog.post_info(channel)
                        await channel.send("📍 **Ubicación de Rashid actualizada.**")
                    else:
                        await channel.send("⚠️ Módulo de Rashid no cargado.")

                elif key == "alertas":
                    self.register_channel("alertas", channel.id)
                    await channel.send("📢 **Alertas activas refrescadas.**")

                elif key == "listas":
                    self.register_channel("listas", channel.id)
                    await channel.send("📋 **Listas de seguimiento actualizadas.**")

                results.append(f"✅ Canal `#{channel.name}` actualizado y guardado en memoria.")
            except Exception as e:
                results.append(f"⚠️ Error en `#{channel.name}`: {str(e)}")

        status_report = "\n".join(results)
        await interaction.followup.send(f"**Informe de Actualización Inteligente:**\n{status_report}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Refresh(bot))