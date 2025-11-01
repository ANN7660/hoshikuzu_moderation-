#!/usr/bin/env python3
# 🌌 Hoshikuzu — Modération
# Bot de modération complet avec warns persistants, mute temporaire (expulsion + invite), et help en embed.
# Compatible Render avec keep_alive intégré.

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

# ---------------- keep-alive pour Render ----------------
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

# ---------------- Data Manager ----------------
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
                print("Erreur de chargement :", e)
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
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.data["warns"][gid][uid].append(entry)
        await self.save()
        return entry

    async def remove_warn(self, guild_id: int, user_id: int, index: int):
        gid, uid = str(guild_id), str(user_id)
        warns = self.list_warns(guild_id, user_id)
        if 0 <= index - 1 < len(warns):
            warns.pop(index - 1)
            self.data["warns"][gid][uid] = warns
            await self.save()
            return True
        return False

moddata = ModData()

# ---------------- Bot Setup ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

# ---------------- Utils ----------------
def parse_duration(s: str) -> Optional[int]:
    s = s.lower().strip()
    if s.endswith("s"): return int(s[:-1])
    if s.endswith("m"): return int(s[:-1]) * 60
    if s.endswith("h"): return int(s[:-1]) * 3600
    if s.endswith("d"): return int(s[:-1]) * 86400
    return None

# ---------------- Commandes ----------------
@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="🌌 Hoshikuzu — Modération",
        description=(
            "**+warn @user [raison]** — Avertir un membre\n"
            "**+warnings @user** — Voir les avertissements\n"
            "**+delwarn @user <index>** — Supprimer un avertissement\n"
            "**+clear [nombre]** — Supprimer des messages\n"
            "**+kick @user [raison]** — Expulser un membre\n"
            "**+ban @user [raison]** — Bannir un membre\n"
            "**+unban <user_id>** — Débannir un utilisateur\n"
            "**+mute @user <durée>** — Mute temporaire (expulsion + retour auto)\n"
            "**+unmute @user** — Annule le mute et renvoie une invitation"
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text="Hoshikuzu Bot • Modération")
    await ctx.send(embed=embed)

# ⚠️ Warn system
@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    await moddata.add_warn(ctx.guild.id, member.id, ctx.author.id, reason)
    await ctx.send(f"⚠️ {member.mention} a été averti pour : {reason}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warnings(ctx, member: discord.Member):
    warns = moddata.list_warns(ctx.guild.id, member.id)
    if not warns:
        await ctx.send("✅ Aucun avertissement pour cet utilisateur.")
    else:
        lines = [f"{i+1}. {w['reason']} (par <@{w['issuer']}>)" for i, w in enumerate(warns)]
        await ctx.send("**Avertissements :**\n" + "\n".join(lines))

@bot.command()
@commands.has_permissions(kick_members=True)
async def delwarn(ctx, member: discord.Member, index: int):
    ok = await moddata.remove_warn(ctx.guild.id, member.id, index)
    if ok:
        await ctx.send(f"✅ Avertissement n°{index} supprimé pour {member.mention}.")
    else:
        await ctx.send("❌ Index invalide ou aucun avertissement trouvé.")

# 🔨 Clear
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 {amount} messages supprimés.", delete_after=5)

# 👢 Kick
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.mention} expulsé — Raison : {reason}")
    except:
        await ctx.send("❌ Impossible d'expulser cet utilisateur.")

# 🔨 Ban / Unban
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"⛔ {member.mention} banni — Raison : {reason}")
    except:
        await ctx.send("❌ Impossible de bannir cet utilisateur.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ {user} a été débanni.")

# 🔇 Mute temporaire (kick + auto-invite)
mutes = {}

@bot.command()
@commands.has_permissions(kick_members=True)
async def mute(ctx, member: discord.Member, duration: str):
    seconds = parse_duration(duration)
    if not seconds:
        await ctx.send("⏳ Durée invalide. Exemple : 10m / 1h / 1d")
        return

    try:
        invite = await ctx.channel.create_invite(max_age=seconds + 60, max_uses=1, reason="Mute temporaire")
        await member.send(f"Tu as été temporairement expulsé de **{ctx.guild.name}** pour {duration}.\nTu pourras revenir ici : {invite.url}")
    except:
        pass

    await member.kick(reason=f"Muted for {duration}")
    await ctx.send(f"🔇 {member.mention} a été expulsé pour {duration}.")

    async def unmute_task():
        await asyncio.sleep(seconds)
        try:
            user = await bot.fetch_user(member.id)
            await user.send(f"Ton mute sur **{ctx.guild.name}** est terminé ! Tu peux revenir via le lien ci-dessus.")
        except:
            pass

    bot.loop.create_task(unmute_task())

@bot.command()
@commands.has_permissions(kick_members=True)
async def unmute(ctx, user: discord.User):
    try:
        invite = await ctx.channel.create_invite(max_age=86400, max_uses=1, reason="Unmute manuel")
        await user.send(f"✅ Tu as été unmuté sur **{ctx.guild.name}**. Voici ton invitation : {invite.url}")
        await ctx.send(f"{user.mention} a été unmuté et réinvité.")
    except:
        await ctx.send("❌ Impossible de DM l'utilisateur.")

# ---------------- Run ----------------
@bot.event
async def on_ready():
    print(f"[🌌 Hoshikuzu — Modération] Connecté comme {bot.user}")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ Variable d'environnement DISCORD_BOT_TOKEN manquante !")
else:
    bot.run(TOKEN)

