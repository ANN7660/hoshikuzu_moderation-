#!/usr/bin/env python3
# Hoshikuzu_moderation_embed.py
# Bot de modération avec embeds stylés, mute temporaire, clear, kick, ban, unban
# Requires: discord.py==2.3.2
# Configure DISCORD_BOT_TOKEN in environment variables before running.

import os, json, asyncio, datetime, threading, http.server, socketserver
from typing import Optional, Dict, Any, Union

import discord
from discord.ext import commands

# -------------------- Keep-alive (Render) --------------------
def keep_alive():
    try:
        port = int(os.environ.get("PORT", 8080))
    except Exception:
        port = 8080

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

    with socketserver.TCPServer(("", port), QuietHandler) as httpd:
        print(f"[keep-alive] HTTP server running on port {port}")
        httpd.serve_forever()

threading.Thread(target=keep_alive, daemon=True).start()

# -------------------- Data Manager (for mutes) --------------------
class ModDataManager:
    def __init__(self, filename: str = "moderation_data.json"):
        self.filename = filename
        self.lock = asyncio.Lock()
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print("Data load error:", e)
        return {"mutes": {}}

    async def save(self):
        async with self.lock:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

    async def add_mute(self, guild_id: int, user_id: int, unmute_ts: int, channel_id: Optional[int], invite_url: Optional[str]):
        gid = str(guild_id); uid = str(user_id)
        self.data.setdefault("mutes", {}).setdefault(gid, {})[uid] = {
            "unmute_ts": unmute_ts,
            "channel": channel_id,
            "invite": invite_url
        }
        await self.save()

    def get_mute(self, guild_id: int, user_id: int) -> Optional[Dict]:
        gid = str(guild_id); uid = str(user_id)
        return self.data.get("mutes", {}).get(gid, {}).get(uid)

    async def remove_mute(self, guild_id: int, user_id: int):
        gid = str(guild_id); uid = str(user_id)
        if gid in self.data.get("mutes", {}) and uid in self.data["mutes"][gid]:
            del self.data["mutes"][gid][uid]
            await self.save()

moddata = ModDataManager()
_scheduled_unmutes = {}

# -------------------- Bot init --------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

# -------------------- Utilities --------------------
def parse_duration(s: str) -> Optional[int]:
    """Parse duration like 30s, 10m, 1h, 2d into seconds"""
    try:
        if s.endswith('s'):
            return int(s[:-1])
        elif s.endswith('m'):
            return int(s[:-1]) * 60
        elif s.endswith('h'):
            return int(s[:-1]) * 3600
        elif s.endswith('d'):
            return int(s[:-1]) * 86400
    except:
        pass
    return None

async def fetch_user_or_member(ctx: commands.Context, user_str: str) -> Optional[Union[discord.Member, discord.User]]:
    """Try to find a member/user from mention, ID, or name"""
    # Try mention
    if user_str.startswith("<@") and user_str.endswith(">"):
        uid = user_str.replace("<@", "").replace("!", "").replace(">", "")
        if uid.isdigit():
            member = ctx.guild.get_member(int(uid))
            if member:
                return member
            try:
                return await bot.fetch_user(int(uid))
            except:
                pass
    # Try ID
    if user_str.isdigit():
        member = ctx.guild.get_member(int(user_str))
        if member:
            return member
        try:
            return await bot.fetch_user(int(user_str))
        except:
            pass
    # Try name search
    member = discord.utils.find(lambda m: m.name.lower() == user_str.lower() or m.display_name.lower() == user_str.lower(), ctx.guild.members)
    if member:
        return member
    return None

# -------------------- Embed helpers --------------------
def embed_action(color: discord.Color, title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    return e

def error_embed(title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=discord.Color.red())
    return e

# -------------------- Help command --------------------
@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(title="🛡️ Hoshikuzu — Modération", color=discord.Color.blue())
    embed.add_field(name="🧹 Clear", value="`+clear [nombre]` - Supprimer des messages (1-100)", inline=False)
    embed.add_field(name="👢 Kick", value="`+kick <user|id|@mention>` - Expulser un membre", inline=False)
    embed.add_field(name="⛔ Ban", value="`+ban <user|id|@mention>` - Bannir un utilisateur", inline=False)
    embed.add_field(name="✅ Unban", value="`+unban <user_id>` - Débannir un utilisateur", inline=False)
    embed.add_field(name="🔇 Mute", value="`+mute <user|id|@mention> <durée>` - Mute temporaire (ex: 10m, 1h)", inline=False)
    embed.add_field(name="🔊 Unmute", value="`+unmute <user|id|@mention>` - Annuler un mute", inline=False)
    embed.set_footer(text="Bot modération — commandes avec +")
    await ctx.send(embed=embed)

# -------------------- Moderation commands --------------------
@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_cmd(ctx: commands.Context, amount: int = 5):
    if amount < 1 or amount > 100:
        return await ctx.send(embed=error_embed("Valeur invalide", "Le nombre doit être entre 1 et 100."))
    deleted = await ctx.channel.purge(limit=amount + 1)  # +1 pour inclure la commande
    await ctx.send(embed=embed_action(discord.Color.blue(), "Clear", f"🧹 {len(deleted) - 1} messages supprimés."), delete_after=5)

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_cmd(ctx: commands.Context, *, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+kick <user|id|@mention>`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible d'expulser", "❌ L'utilisateur n'est pas membre du serveur."))
    try:
        await target.kick(reason=f"Kick par {ctx.author}")
        await ctx.send(embed=embed_action(discord.Color.orange(), "Expulsion", f"👢 {target.mention} a été expulsé du serveur !"))
    except Exception as e:
        print("kick error:", e)
        await ctx.send(embed=error_embed("Erreur", "Impossible d'expulser cet utilisateur."))

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_cmd(ctx: commands.Context, *, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+ban <user|id|@mention>`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    try:
        if isinstance(target, discord.Member):
            await target.ban(reason=f"Ban par {ctx.author}", delete_message_days=0)
            await ctx.send(embed=embed_action(discord.Color.red(), "Bannissement", f"⛔ {target.mention} a été banni du serveur !"))
        else:
            # ban by id (User object)
            await ctx.guild.ban(discord.Object(id=int(target.id)), reason=f"Ban par {ctx.author}")
            await ctx.send(embed=embed_action(discord.Color.red(), "Bannissement", f"⛔ {target} a été banni du serveur !"))
    except Exception as e:
        print("ban error:", e)
        await ctx.send(embed=error_embed("Erreur", "Impossible de bannir cet utilisateur."))

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_cmd(ctx: commands.Context, user_id: str = None):
    if not user_id:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+unban <user_id>`"))
    if not user_id.isdigit():
        return await ctx.send(embed=error_embed("ID invalide", "❌ Fournis un ID numérique valide."))
    uid = int(user_id)
    try:
        user = await bot.fetch_user(uid)
        await ctx.guild.unban(user, reason=f"Unban par {ctx.author}")
        await ctx.send(embed=embed_action(discord.Color.green(), "Débannissement", f"✅ {user} a été débanni."))
    except Exception as e:
        print("unban error:", e)
        await ctx.send(embed=error_embed("Erreur", "Impossible de débannir cet utilisateur (id invalide ou pas banni)."))

# -------------------- Mute (temporary exclusion = kick + invite) --------------------
async def schedule_unmute(guild: discord.Guild, user_id: int, unmute_ts: int):
    now = int(datetime.datetime.utcnow().timestamp())
    wait = unmute_ts - now
    key = f"{guild.id}-{user_id}"
    if wait <= 0:
        await perform_unmute(guild, user_id)
        return
    # cancel existing
    task = _scheduled_unmutes.get(key)
    if task and not task.done():
        task.cancel()
    
    async def _job():
        try:
            await asyncio.sleep(wait)
            await perform_unmute(guild, user_id)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print("scheduled_unmute error:", e)
    
    t = asyncio.create_task(_job())
    _scheduled_unmutes[key] = t

async def perform_unmute(guild: discord.Guild, user_id: int):
    try:
        mute = moddata.get_mute(guild.id, user_id)
        channel = None
        if mute and mute.get("channel"):
            channel = guild.get_channel(int(mute.get("channel")))
        if not channel:
            channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite), None)
        
        invite_url = None
        if channel and channel.permissions_for(guild.me).create_instant_invite:
            try:
                inv = await channel.create_invite(max_age=24*3600, max_uses=1, unique=True, reason="Auto unmute invite")
                invite_url = inv.url
            except Exception as e:
                print("Could not create invite:", e)
        
        # DM the user with invite_url if possible
        try:
            user = await bot.fetch_user(user_id)
            if user and invite_url:
                await user.send(f"🔔 Ton mute sur **{guild.name}** est terminé — voici ton lien pour revenir : {invite_url}")
            elif user:
                await user.send(f"🔔 Ton mute sur **{guild.name}** est terminé !")
        except Exception as e:
            print("Could not DM user on unmute:", e)
    except Exception as e:
        print("perform_unmute unexpected error:", e)
    
    # remove mute record
    try:
        await moddata.remove_mute(guild.id, user_id)
    except Exception as e:
        print("Could not remove mute record:", e)

@bot.command(name="mute")
@commands.has_permissions(kick_members=True)
async def mute_cmd(ctx: commands.Context, user: str = None, duration: str = None):
    if not user or not duration:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+mute <user|id|@mention> <durée>` (ex : 10m, 1h)"))
    
    seconds = parse_duration(duration)
    if seconds is None or seconds <= 0:
        return await ctx.send(embed=error_embed("Durée invalide", "❌ Exemple : 30s, 10m, 1h, 2d"))
    
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    
    # if not a member (already out) -> cannot kick
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible d'expulser", "❌ L'utilisateur n'est pas membre du serveur."))
    
    # pick a channel to create invite
    channel = ctx.guild.system_channel or next((c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).create_instant_invite), None)
    invite_url = None
    if channel and channel.permissions_for(ctx.guild.me).create_instant_invite:
        try:
            inv = await channel.create_invite(max_age=seconds + 60, max_uses=1, unique=True, reason=f"mute invite for {target.id}")
            invite_url = inv.url
        except Exception as e:
            print("Invite creation failed:", e)
    
    # DM the user if possible, best effort
    try:
        msg = f"🔇 Tu as été temporairement expulsé de **{ctx.guild.name}** pour {duration}."
        if invite_url:
            msg += f" Tu pourras revenir via ce lien après la durée : {invite_url}"
        await target.send(msg)
    except Exception:
        pass
    
    # perform kick
    try:
        await target.kick(reason=f"Mute temporaire par {ctx.author}")
    except Exception as e:
        print("kick during mute failed:", e)
        return await ctx.send(embed=error_embed("Erreur", "Impossible d'expulser l'utilisateur."))
    
    # store mute and schedule unmute
    unmute_ts = int(datetime.datetime.utcnow().timestamp()) + seconds
    await moddata.add_mute(ctx.guild.id, target.id, unmute_ts, channel.id if channel else None, invite_url)
    await ctx.send(embed=embed_action(discord.Color.dark_magenta(), "Mute temporaire", f"🔇 {target.mention} a été temporairement expulsé pour {duration}. Il/elle recevra un lien pour revenir quand le mute sera terminé."))
    await schedule_unmute(ctx.guild, target.id, unmute_ts)

@bot.command(name="unmute")
@commands.has_permissions(kick_members=True)
async def unmute_cmd(ctx: commands.Context, *, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+unmute <user|id|@mention>`"))
    
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    
    mute = moddata.get_mute(ctx.guild.id, int(target.id))
    if not mute:
        return await ctx.send(embed=error_embed("Non muted", "❌ Cet utilisateur n'est pas enregistré comme muted."))
    
    # create invite now and DM user
    channel = ctx.guild.get_channel(mute.get("channel")) if mute.get("channel") else (ctx.guild.system_channel or next((c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).create_instant_invite), None))
    invite_url = None
    if channel and channel.permissions_for(ctx.guild.me).create_instant_invite:
        try:
            inv = await channel.create_invite(max_age=24*3600, max_uses=1, unique=True, reason="manual unmute invite")
            invite_url = inv.url
        except Exception as e:
            print("manual unmute invite failed:", e)
    
    try:
        msg = f"✅ Tu as été unmute sur **{ctx.guild.name}**."
        if invite_url:
            msg += f" Voici un lien pour revenir : {invite_url}"
        await target.send(msg)
    except Exception as e:
        print("Could not DM user on manual unmute:", e)
    
    # cancel scheduled task if exists
    key = f"{ctx.guild.id}-{int(target.id)}"
    task = _scheduled_unmutes.get(key)
    if task and not task.done():
        task.cancel()
    
    await moddata.remove_mute(ctx.guild.id, int(target.id))
    await ctx.send(embed=embed_action(discord.Color.green(), "Unmute", f"🔊 {target} a été unmute et invité à revenir (si DM possible)."))

# -------------------- on_ready: reschedule unmutes --------------------
@bot.event
async def on_ready():
    print(f"[MOD BOT] connecté comme {bot.user} ({bot.user.id})")
    # reschedule pending unmutes from storage
    try:
        for gid, guild_mutes in moddata.data.get("mutes", {}).items():
            for uid_str, info in guild_mutes.items():
                guild = discord.utils.get(bot.guilds, id=int(gid))
                if not guild:
                    continue
                unmute_ts = int(info.get("unmute_ts", 0))
                if unmute_ts > int(datetime.datetime.utcnow().timestamp()):
                    asyncio.create_task(schedule_unmute(guild, int(uid_str), unmute_ts))
    except Exception as e:
        print("Error scheduling unmutes on ready:", e)

# -------------------- Error handling --------------------
@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Command not found - ignore silently
    if isinstance(error, commands.CommandNotFound):
        return
    # Missing argument - ignore silently
    if isinstance(error, commands.MissingRequiredArgument):
        return
    # Member not found or bad argument - ignore silently
    if isinstance(error, (commands.MemberNotFound, commands.BadArgument)):
        return
    # Permissions - ignore silently
    if isinstance(error, commands.MissingPermissions):
        return
    # default - ignore all errors
    print("Command error (ignored):", error)

# -------------------- Run --------------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ DISCORD_BOT_TOKEN non défini. Ajoute la variable d'environnement et relance.")
else:
    bot.run(TOKEN)
