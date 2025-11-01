#!/usr/bin/env python3
# Hoshikuzu_moderation.py
# Moderation-only bot: warn system (persistent), kick, ban, unban, clear, mute (temporary kick + invite), unmute, simple +help
# - Stores data in moderation_data.json
# - Mute = temporary exclusion (kick) + DM invite created for the user to rejoin when time is up
# - Requires discord.py==2.3.2
#
# Configure DISCORD_BOT_TOKEN env variable before running.

import os
import json
import asyncio
import datetime
import threading
import http.server
import socketserver
from typing import Optional, Dict, Any

import discord
from discord.ext import commands

# ---------------- keep-alive for Render ----------------
def keep_alive():
    try:
        port = int(os.environ.get("PORT", 8080))
    except Exception:
        port = 8080
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args): pass
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
        # default structure
        return {"warns": {}, "mutes": {}}

    async def save(self):
        async with self.lock:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

    # warns helpers
    async def add_warn(self, guild_id: int, user_id: int, issuer_id: int, reason: str):
        gid = str(guild_id); uid = str(user_id)
        self.data.setdefault("warns", {}).setdefault(gid, {}).setdefault(uid, [])
        entry = {
            "id": int(datetime.datetime.now().timestamp()),
            "issuer": str(issuer_id),
            "reason": reason,
            "date": datetime.datetime.now(datetime.timezone.utc).isoformat() if hasattr(datetime, "timezone") else str(datetime.datetime.now())
        }
        self.data["warns"][gid][uid].append(entry)
        await self.save()
        return entry

    def list_warns(self, guild_id: int, user_id: int):
        gid = str(guild_id); uid = str(user_id)
        return self.data.get("warns", {}).get(gid, {}).get(uid, [])

    async def del_warn(self, guild_id: int, user_id: int, warn_id: int):
        gid = str(guild_id); uid = str(user_id)
        warns = self.data.get("warns", {}).get(gid, {}).get(uid, [])
        new = [w for w in warns if w.get("id") != warn_id]
        self.data.setdefault("warns", {}).setdefault(gid, {})[uid] = new
        await self.save()

    # mutes helpers: store as { guild: { user_id: { "unmute_ts": ts, "channel": channel_id, "invite": invite_url } } }
    async def add_mute(self, guild_id: int, user_id: int, unmute_ts: int, channel_id: Optional[int], invite_url: Optional[str]):
        gid = str(guild_id); uid = str(user_id)
        self.data.setdefault("mutes", {}).setdefault(gid, {})[uid] = {
            "unmute_ts": int(unmute_ts),
            "channel": int(channel_id) if channel_id else None,
            "invite": invite_url
        }
        await self.save()

    def get_mute(self, guild_id: int, user_id: int):
        gid = str(guild_id); uid = str(user_id)
        return self.data.get("mutes", {}).get(gid, {}).get(uid)

    async def remove_mute(self, guild_id: int, user_id: int):
        gid = str(guild_id); uid = str(user_id)
        if gid in self.data.get("mutes", {}) and uid in self.data["mutes"][gid]:
            del self.data["mutes"][gid][uid]
            await self.save()

moddata = ModData()

# ---------------- bot setup ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

# background tasks storage for scheduled unmutes
_scheduled_unmutes: Dict[str, asyncio.Task] = {}

# ---------------- utilities ----------------
def parse_duration(s: str) -> Optional[int]:
    """Parses duration strings like '10m', '1h', '30s', '2d' into seconds.
    Returns None if invalid."""
    if not s: return None
    s = s.strip().lower()
    try:
        if s.endswith("s"):
            return int(s[:-1])
        if s.endswith("m"):
            return int(s[:-1]) * 60
        if s.endswith("h"):
            return int(s[:-1]) * 3600
        if s.endswith("d"):
            return int(s[:-1]) * 86400
        # plain integer -> seconds
        return int(s)
    except Exception:
        return None

async def schedule_unmute(guild: discord.Guild, user_id: int, unmute_ts: int):
    """Wait until unmute_ts then create an invite and DM the user the invite url if still not in the guild.
    Afterwards remove the mute entry."""
    now = int(datetime.datetime.now().timestamp())
    wait = unmute_ts - now
    key = f"{guild.id}-{user_id}"
    if wait <= 0:
        await perform_unmute(guild, user_id)
        return
    # cancel existing task if any
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
    """Create an invite for guild and DM the user with the invite url if they're not in the guild.
    Remove mute record afterwards."""
    try:
        mute = moddata.get_mute(guild.id, user_id)
        # pick a channel to create invite
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
    # finally remove mute entry
    try:
        await moddata.remove_mute(guild.id, user_id)
    except Exception as e:
        print("Could not remove mute record:", e)

# ---------------- commands: simple help ----------------
@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    msg = (
        "Commandes de modération disponibles :\n"
        "+warn @user [raison]\n"
        "+warnings @user\n"
        "+delwarn @user <index>\n"
        "+clear [nombre]\n"
        "+kick @user [raison]\n"
        "+ban @user [raison]\n"
        "+unban <user_id>\n"
        "+mute @user <durée>  (ex: 10m, 1h, 2d)\n"
        "+unmute @user\n"
    )
    await ctx.send(msg)

# ---------------- commands: warns ----------------
@bot.command(name="warn")
@commands.has_permissions(kick_members=True)
async def warn_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "Aucune raison fournie"):
    gid = str(ctx.guild.id); uid = str(member.id)
    entry = {"issuer": str(ctx.author.id), "reason": reason, "date": datetime.datetime.now().isoformat()}
    moddata.data.setdefault("warns", {}).setdefault(gid, {}).setdefault(uid, []).append(entry)
    await moddata.save()
    await ctx.send(f"⚠️ {member.mention} averti·e. Raison : {reason}")

@bot.command(name="warnings")
@commands.has_permissions(kick_members=True)
async def warnings_cmd(ctx: commands.Context, member: discord.Member):
    warns = moddata.list_warns(ctx.guild.id, member.id)
    if not warns:
        return await ctx.send("Aucun avertissement pour cet utilisateur.")
    lines = []
    for i, w in enumerate(warns, start=1):
        issuer = f"<@{w.get('issuer')}>" if w.get("issuer") else "Inconnu"
        lines.append(f"{i}. {issuer} — {w.get('reason')} ({w.get('date')})")
    await ctx.send("Avertissements :\n" + "\n".join(lines))

@bot.command(name="delwarn")
@commands.has_permissions(kick_members=True)
async def delwarn_cmd(ctx: commands.Context, member: discord.Member, index: int):
    gid = str(ctx.guild.id); uid = str(member.id)
    warns = moddata.data.setdefault("warns", {}).setdefault(gid, {}).get(uid, [])
    if not warns or index < 1 or index > len(warns):
        return await ctx.send("Index d'avertissement invalide.")
    removed = warns.pop(index - 1)
    moddata.data["warns"][gid][uid] = warns
    await moddata.save()
    await ctx.send(f"✅ Avertissement supprimé : {removed.get('reason')}")

# ---------------- moderation commands ----------------
@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_cmd(ctx: commands.Context, amount: int = 5):
    if amount < 1 or amount > 100:
        return await ctx.send("Le nombre doit être entre 1 et 100.")
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 {len(deleted)} messages supprimés.", delete_after=5)

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "Aucune raison fournie"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.mention} expulsé·e. Raison : {reason}")
    except Exception as e:
        await ctx.send("Impossible d'expulser cet utilisateur.")
        print("kick error:", e)

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "Aucune raison fournie"):
    try:
        await member.ban(reason=reason, delete_message_days=0)
        await ctx.send(f"⛔ {member.mention} banni·e. Raison : {reason}")
    except Exception as e:
        await ctx.send("Impossible de bannir cet utilisateur.")
        print("ban error:", e)

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_cmd(ctx: commands.Context, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Utilisateur {user} débanni.")
    except Exception as e:
        await ctx.send("Impossible de débannir cet utilisateur (id invalide ou pas banni).")
        print("unban error:", e)

# ---------------- mute (temporary exclusion) ----------------
@bot.command(name="mute")
@commands.has_permissions(kick_members=True)
async def mute_cmd(ctx: commands.Context, member: discord.Member, duration: str):
    seconds = parse_duration(duration)
    if seconds is None or seconds <= 0:
        return await ctx.send("Durée invalide. Exemples : 30s, 10m, 1h, 2d")
    unmute_ts = int(datetime.datetime.now().timestamp()) + seconds
    # choose a channel to create invite (prefer system channel, else first text channel where bot can create invite)
    channel = ctx.guild.system_channel or next((c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).create_instant_invite), None)
    invite_url = None
    if channel and channel.permissions_for(ctx.guild.me).create_instant_invite:
        try:
            inv = await channel.create_invite(max_age=seconds+60, max_uses=1, unique=True, reason=f"mute invite for {member.id}")
            invite_url = inv.url
        except Exception as e:
            print("Invite creation failed:", e)
    # Kick the member
    try:
        await member.kick(reason=f"Muted for {duration} by {ctx.author}")
    except Exception as e:
        await ctx.send("Impossible d'expulser l'utilisateur.")
        print("kick during mute failed:", e); return
    # store mute info and schedule unmute
    await moddata.add_mute(ctx.guild.id, member.id, unmute_ts, channel.id if channel else None, invite_url)
    await ctx.send(f"🔇 {member} a été expulsé·e pour {duration}. Il recevra un lien pour revenir quand le mute sera terminé.")
    # try to DM the user immediately with the invite (if created)
    if invite_url:
        try:
            await member.send(f"Tu as été temporairement expulsé·e de **{ctx.guild.name}** pour {duration}. Tu pourras revenir automatiquement via ce lien après la durée : {invite_url}")
        except Exception:
            pass
    # schedule unmute task
    await schedule_unmute(ctx.guild, member.id, unmute_ts)

@bot.command(name="unmute")
@commands.has_permissions(kick_members=True)
async def unmute_cmd(ctx: commands.Context, user: discord.User):
    mute = moddata.get_mute(ctx.guild.id, user.id)
    if not mute:
        return await ctx.send("Utilisateur non muted (aucun enregistrement).")
    channel = ctx.guild.get_channel(mute.get("channel")) if mute.get("channel") else (ctx.guild.system_channel or next((c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).create_instant_invite), None))
    invite_url = None
    if channel and channel.permissions_for(ctx.guild.me).create_instant_invite:
        try:
            inv = await channel.create_invite(max_age=24*3600, max_uses=1, unique=True, reason="manual unmute invite")
            invite_url = inv.url
        except Exception as e:
            print("manual unmute invite failed:", e)
    try:
        await user.send(f"Tu as été unmuté·e sur **{ctx.guild.name}**. Voici un lien pour revenir : {invite_url}" if invite_url else f"Tu as été unmuté·e sur **{ctx.guild.name}**.")
    except Exception as e:
        print("Could not DM user on manual unmute:", e)
    key = f"{ctx.guild.id}-{user.id}"
    task = _scheduled_unmutes.get(key)
    if task and not task.done():
        task.cancel()
    await moddata.remove_mute(ctx.guild.id, user.id)
    await ctx.send(f"✅ {user} unmuté·e et invité·e à revenir (si DM possible).")

# ---------------- on_ready: reschedule unmutes ----------------
@bot.event
async def on_ready():
    print(f"[MOD BOT] connecté comme {bot.user} ({bot.user.id})")
    try:
        for gid, guild_mutes in moddata.data.get("mutes", {}).items():
            for uid, info in guild_mutes.items():
                guild = discord.utils.get(bot.guilds, id=int(gid))
                if not guild:
                    continue
                unmute_ts = int(info.get("unmute_ts", 0))
                if unmute_ts > int(datetime.datetime.now().timestamp()):
                    asyncio.create_task(schedule_unmute(guild, int(uid), unmute_ts))
    except Exception as e:
        print("Error scheduling unmutes on ready:", e)

# ---------------- run ----------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ DISCORD_BOT_TOKEN non défini. Ajoute la variable d'environnement et relance.")
else:
    bot.run(TOKEN)
