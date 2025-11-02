#!/usr/bin/env python3
# Hoshikuzu_moderation_embed.py
# 🌌 Hoshikuzu — Modération (final)
# - warn system persisted in moderation_data.json
# - mute = temporary kick + invite DM, auto-unmute scheduled
# - commands accept mention OR numeric ID
# - custom error handling with red embeds for missing args / not found
# - keep_alive for Render
# Requires: discord.py==2.3.2

import os
import json
import asyncio
import datetime
import threading
import http.server
import socketserver
from typing import Optional, Dict, Any, Union

import discord
from discord.ext import commands

# ---------------- keep-alive for Render ----------------
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

# ---------------- Data manager ----------------
DATA_FILE = "moderation_data.json"

class ModData:
    def __init__(self, filename=DATA_FILE):
        self.filename = filename
        self.lock = asyncio.Lock()
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print("Failed to load moderation data:", e)
        return {"warns": {}, "mutes": {}}

    async def save(self):
        async with self.lock:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

    def list_warns(self, guild_id: int, user_id: int):
        return self.data.get("warns", {}).get(str(guild_id), {}).get(str(user_id), [])

    async def add_warn(self, guild_id: int, user_id: int, issuer_id: int, reason: str):
        gid, uid = str(guild_id), str(user_id)
        self.data.setdefault("warns", {}).setdefault(gid, {}).setdefault(uid, [])
        entry = {
            "issuer": str(issuer_id),
            "reason": reason,
            "date": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.data["warns"][gid][uid].append(entry)
        await self.save()

    async def remove_warn(self, guild_id: int, user_id: int, index: int):
        gid, uid = str(guild_id), str(user_id)
        warns = self.list_warns(guild_id, user_id)
        if 0 <= index - 1 < len(warns):
            warns.pop(index - 1)
            self.data["warns"][gid][uid] = warns
            await self.save()
            return True
        return False

    async def add_mute(self, guild_id: int, user_id: int, unmute_ts: int, channel_id: Optional[int], invite_url: Optional[str]):
        gid, uid = str(guild_id), str(user_id)
        self.data.setdefault("mutes", {}).setdefault(gid, {})[uid] = {
            "unmute_ts": int(unmute_ts),
            "channel": int(channel_id) if channel_id else None,
            "invite": invite_url
        }
        await self.save()

    def get_mute(self, guild_id: int, user_id: int):
        return self.data.get("mutes", {}).get(str(guild_id), {}).get(str(user_id))

    async def remove_mute(self, guild_id: int, user_id: int):
        gid, uid = str(guild_id), str(user_id)
        if gid in self.data.get("mutes", {}) and uid in self.data["mutes"][gid]:
            del self.data["mutes"][gid][uid]
            await self.save()

moddata = ModData()

# ---------------- Bot setup ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

# scheduled tasks for unmutes
_scheduled_unmutes: Dict[str, asyncio.Task] = {}

# ---------------- Utilities ----------------
def parse_duration(s: str) -> Optional[int]:
    if not s:
        return None
    s = s.lower().strip()
    try:
        if s.endswith("s"):
            return int(s[:-1])
        if s.endswith("m"):
            return int(s[:-1]) * 60
        if s.endswith("h"):
            return int(s[:-1]) * 3600
        if s.endswith("d"):
            return int(s[:-1]) * 86400
        # fallback: integer seconds
        return int(s)
    except Exception:
        return None

async def fetch_user_or_member(ctx: commands.Context, arg: str) -> Union[discord.Member, discord.User, None]:
    """
    Accepts <@...>, plain ID, or username (tries MemberConverter).
    Returns discord.Member if in guild, otherwise discord.User (fetched), or None.
    """
    if not arg:
        return None
    original = arg
    # strip mention wrapper <@!id> or <@id>
    if arg.startswith("<@") and arg.endswith(">"):
        arg = arg.replace("<@", "").replace(">", "").replace("!", "")
    # if numeric id
    if arg.isdigit():
        uid = int(arg)
        # try to get Member first
        member = ctx.guild.get_member(uid)
        if member:
            return member
        # fallback to fetch_user
        try:
            user = await bot.fetch_user(uid)
            return user
        except Exception:
            return None
    # fallback: try MemberConverter (username#discrim or nickname)
    try:
        return await commands.MemberConverter().convert(ctx, original)
    except Exception:
        # try fetch by name? we avoid heavy searches; return None
        return None

# ---------------- Error embed helper ----------------
def error_embed(title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=discord.Color.red())
    return e

# ---------------- help (embed violet) ----------------
@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="🌌 Hoshikuzu — Modération",
        description=(
            "**+warn <user|id|@mention> [raison]** — Avertir un membre\n"
            "**+warnings <user|id|@mention>** — Voir les avertissements\n"
            "**+delwarn <user|id|@mention> <index>** — Supprimer un avertissement\n"
            "**+clear [nombre]** — Supprimer des messages (max 100)\n"
            "**+kick <user|id|@mention> [raison]** — Expulser un membre\n"
            "**+ban <user|id|@mention> [raison]** — Bannir un membre\n"
            "**+unban <user_id>** — Débannir un utilisateur\n"
            "**+mute <user|id|@mention> <durée>** — Expulsion temporaire + invite (ex: 10m, 1h)\n"
            "**+unmute <user|id|@mention>** — Annule le mute et envoie l'invite"
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text="Hoshikuzu Bot • Modération")
    await ctx.send(embed=embed)

# ---------------- Commands: warns ----------------
@bot.command(name="warn")
@commands.has_permissions(kick_members=True)
async def warn_cmd(ctx: commands.Context, user: str = None, *, reason: str = "Aucune raison fournie"):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+warn <user|id|@mention> [raison]`"))
    member_or_user = await fetch_user_or_member(ctx, user)
    if not member_or_user:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable. Utilise une mention ou un ID valide."))
    await moddata.add_warn(ctx.guild.id, int(member_or_user.id), ctx.author.id, reason)
    await ctx.send(f"⚠️ {member_or_user.mention if isinstance(member_or_user, discord.Member) else str(member_or_user)} averti·e. Raison: {reason}")

@bot.command(name="warnings")
@commands.has_permissions(kick_members=True)
async def warnings_cmd(ctx: commands.Context, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+warnings <user|id|@mention>`"))
    member_or_user = await fetch_user_or_member(ctx, user)
    if not member_or_user:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable."))
    warns = moddata.list_warns(ctx.guild.id, int(member_or_user.id))
    if not warns:
        return await ctx.send("✅ Aucun avertissement pour cet utilisateur.")
    lines = []
    for i, w in enumerate(warns, start=1):
        lines.append(f"{i}. {w.get('reason')} — par <@{w.get('issuer')}> ({w.get('date')})")
    # send in chunks if very long
    await ctx.send("**Avertissements :**\n" + "\n".join(lines))

@bot.command(name="delwarn")
@commands.has_permissions(kick_members=True)
async def delwarn_cmd(ctx: commands.Context, user: str = None, index: int = None):
    if not user or index is None:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+delwarn <user|id|@mention> <index>`"))
    member_or_user = await fetch_user_or_member(ctx, user)
    if not member_or_user:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable."))
    ok = await moddata.remove_warn(ctx.guild.id, int(member_or_user.id), index)
    if ok:
        await ctx.send(f"✅ Avertissement n°{index} supprimé pour {member_or_user}.")
    else:
        await ctx.send(embed=error_embed("Index invalide", "❌ Index invalide ou aucun avertissement trouvé."))

# ---------------- moderation commands ----------------
@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_cmd(ctx: commands.Context, amount: int = 5):
    if amount < 1 or amount > 100:
        return await ctx.send(embed=error_embed("Valeur invalide", "Le nombre doit être entre 1 et 100."))
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 {len(deleted)} messages supprimés.", delete_after=5)

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_cmd(ctx: commands.Context, user: str = None, *, reason: str = "Aucune raison fournie"):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+kick <user|id|@mention> [raison]`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable."))
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible d'expulser", "❌ L'utilisateur n'est pas membre du serveur."))
    try:
        await target.kick(reason=reason)
        await ctx.send(f"👢 {target.mention} expulsé·e. Raison : {reason}")
    except Exception as e:
        print("kick error:", e)
        await ctx.send(embed=error_embed("Erreur", "Impossible d'expulser cet utilisateur."))

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_cmd(ctx: commands.Context, user: str = None, *, reason: str = "Aucune raison fournie"):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+ban <user|id|@mention> [raison]`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable."))
    # if Member, ban, if User (not in guild) try to ban by id
    try:
        if isinstance(target, discord.Member):
            await target.ban(reason=reason, delete_message_days=0)
            await ctx.send(f"⛔ {target.mention} banni·e. Raison : {reason}")
        else:
            # fetch_user returned a User not in guild; ban by id
            await ctx.guild.ban(discord.Object(id=int(target.id)), reason=reason)
            await ctx.send(f"⛔ {target} banni·e (by id). Raison : {reason}")
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
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Utilisateur {user} débanni.")
    except Exception as e:
        print("unban error:", e)
        await ctx.send(embed=error_embed("Erreur", "Impossible de débannir cet utilisateur (id invalide ou pas banni)."))

# ---------------- mute (temporary exclusion = kick + invite) ----------------
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
        # choose a channel to create invite
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
        # DM the user with invite_url
        try:
            user = await bot.fetch_user(user_id)
            if user and invite_url:
                await user.send(f"Tu peux revenir sur **{guild.name}** via ce lien : {invite_url}")
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
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable."))
    # pick channel to create invite
    channel = ctx.guild.system_channel or next((c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).create_instant_invite), None)
    invite_url = None
    if channel and channel.permissions_for(ctx.guild.me).create_instant_invite:
        try:
            inv = await channel.create_invite(max_age=seconds + 60, max_uses=1, unique=True, reason=f"mute invite for {getattr(target, 'id', 'unknown')}")
            invite_url = inv.url
        except Exception as e:
            print("Invite creation failed:", e)
    # try DM before kicking (best effort)
    try:
        if isinstance(target, discord.Member):
            await target.send(f"Tu as été temporairement expulsé·e de **{ctx.guild.name}** pour {duration}. Tu pourras revenir via ce lien après la durée : {invite_url}" if invite_url else f"Tu as été temporairement expulsé·e de **{ctx.guild.name}** pour {duration}.")
        else:
            # if it's a User (not in guild), best effort DM
            await target.send(f"Tu as été temporairement expulsé·e de **{ctx.guild.name}** pour {duration}.")
    except Exception:
        pass
    # perform kick (only possible if it's Member)
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible d'expulser", "❌ L'utilisateur n'est pas membre du serveur (peut-être déjà exclu)."))
    try:
        await target.kick(reason=f"Muted for {duration} by {ctx.author}")
    except Exception as e:
        print("kick during mute failed:", e)
        return await ctx.send(embed=error_embed("Erreur", "Impossible d'expulser l'utilisateur."))
    unmute_ts = int(datetime.datetime.utcnow().timestamp()) + seconds
    await moddata.add_mute(ctx.guild.id, target.id, unmute_ts, channel.id if channel else None, invite_url)
    await ctx.send(f"🔇 {target.mention} a été expulsé·e pour {duration}. Il recevra un lien pour revenir quand le mute sera terminé.")
    # schedule unmute
    await schedule_unmute(ctx.guild, target.id, unmute_ts)

@bot.command(name="unmute")
@commands.has_permissions(kick_members=True)
async def unmute_cmd(ctx: commands.Context, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+unmute <user|id|@mention>`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable."))
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
        await target.send(f"✅ Tu as été unmuté·e sur **{ctx.guild.name}**. Voici un lien pour revenir : {invite_url}" if invite_url else f"✅ Tu as été unmuté·e sur **{ctx.guild.name}**.")
    except Exception as e:
        print("Could not DM user on manual unmute:", e)
    # cancel scheduled task if exists
    key = f"{ctx.guild.id}-{int(target.id)}"
    task = _scheduled_unmutes.get(key)
    if task and not task.done():
        task.cancel()
    await moddata.remove_mute(ctx.guild.id, int(target.id))
    await ctx.send(f"✅ {target} unmuté·e et invité·e à revenir (si DM possible).")

# ---------------- on_ready: reschedule unmutes ----------------
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

# ---------------- Error handling ----------------
@bot.event
async def on_command_error(ctx: commands.Context, error):
    # handle missing required argument
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=error_embed("Argument manquant", f"❌ {error.param.name} est requis. Vérifie la commande."))
        return
    # member not found or converter errors
    if isinstance(error, commands.MemberNotFound) or isinstance(error, commands.BadArgument):
        await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable. Utilise une mention ou un ID valide."))
        return
    # permission errors
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=error_embed("Permission refusée", "❌ Tu n'as pas la permission pour utiliser cette commande."))
        return
    # default: log and show message
    print("Unhandled command error:", error)
    try:
        await ctx.send(embed=error_embed("Erreur", "Une erreur est survenue en exécutant la commande."))
    except:
        pass

# ---------------- Run ----------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ DISCORD_BOT_TOKEN non défini. Ajoute la variable d'environnement et relance.")
else:
    bot.run(TOKEN)
