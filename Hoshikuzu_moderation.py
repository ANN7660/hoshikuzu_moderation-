#!/usr/bin/env python3
# 🌌 Hoshikuzu — Modération
# Bot de modération complet (warn, mute, kick, ban, etc.) avec support des @mentions et IDs.
# Compatible Render (keep_alive intégré).

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

# ---------------- keep-alive ----------------
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

# ---------------- Data ----------------
DATA_FILE = "moderation_data.json"

class ModData:
    def __init__(self, filename=DATA_FILE):
        self.filename = filename
        self.lock = asyncio.Lock()
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"warns": {}, "mutes": {}}

    async def save(self):
        async with self.lock:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

    def list_warns(self, guild_id, user_id):
        return self.data.get("warns", {}).get(str(guild_id), {}).get(str(user_id), [])

    async def add_warn(self, guild_id, user_id, issuer_id, reason):
        gid, uid = str(guild_id), str(user_id)
        self.data.setdefault("warns", {}).setdefault(gid, {}).setdefault(uid, [])
        entry = {
            "issuer": str(issuer_id),
            "reason": reason,
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.data["warns"][gid][uid].append(entry)
        await self.save()

    async def remove_warn(self, guild_id, user_id, index):
        gid, uid = str(guild_id), str(user_id)
        warns = self.list_warns(guild_id, user_id)
        if 0 <= index - 1 < len(warns):
            warns.pop(index - 1)
            self.data["warns"][gid][uid] = warns
            await self.save()
            return True
        return False

moddata = ModData()

# ---------------- Bot setup ----------------
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

async def fetch_user_or_member(ctx, arg: str) -> Union[discord.Member, discord.User, None]:
    # Try to parse mention or numeric ID
    if arg.startswith("<@") and arg.endswith(">"):
        arg = arg.strip("<@!>")
    if arg.isdigit():
        member = ctx.guild.get_member(int(arg))
        if member:
            return member
        try:
            return await bot.fetch_user(int(arg))
        except:
            return None
    # fallback: maybe it's a name
    try:
        return await commands.MemberConverter().convert(ctx, arg)
    except:
        return None

# ---------------- HELP ----------------
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

# ---------------- Commands ----------------
@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, user: str, *, reason="Aucune raison fournie"):
    member = await fetch_user_or_member(ctx, user)
    if not member:
        return await ctx.send("❌ Utilisateur introuvable.")
    await moddata.add_warn(ctx.guild.id, member.id, ctx.author.id, reason)
    await ctx.send(f"⚠️ {member.mention if isinstance(member, discord.Member) else member} averti pour : {reason}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warnings(ctx, user: str):
    member = await fetch_user_or_member(ctx, user)
    if not member:
        return await ctx.send("❌ Utilisateur introuvable.")
    warns = moddata.list_warns(ctx.guild.id, member.id)
    if not warns:
        await ctx.send("✅ Aucun avertissement pour cet utilisateur.")
    else:
        lines = [f"{i+1}. {w['reason']} (par <@{w['issuer']}>)" for i, w in enumerate(warns)]
        await ctx.send("**Avertissements :**\n" + "\n".join(lines))

@bot.command()
@commands.has_permissions(kick_members=True)
async def delwarn(ctx, user: str, index: int):
    member = await fetch_user_or_member(ctx, user)
    if not member:
        return await ctx.send("❌ Utilisateur introuvable.")
    ok = await moddata.remove_warn(ctx.guild.id, member.id, index)
    if ok:
        await ctx.send(f"✅ Avertissement n°{index} supprimé pour {member}.")
    else:
        await ctx.send("❌ Index invalide ou aucun avertissement trouvé.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 {amount} messages supprimés.", delete_after=5)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, user: str, *, reason="Aucune raison fournie"):
    member = await fetch_user_or_member(ctx, user)
    if not isinstance(member,

