#!/usr/bin/env python3
# Hoshikuzu_moderation_embed.py
# Bot de modération avec embeds stylés, timeout (mute natif), clear, kick, ban, unban
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
    embed.add_field(name="🔇 Mute", value="`+mute <user|id|@mention> <durée>` - Timeout temporaire (ex: 10m, 1h)", inline=False)
    embed.add_field(name="🔊 Unmute", value="`+unmute <user|id|@mention>` - Annuler un timeout", inline=False)
    embed.set_footer(text="Hoshikuzu | +help 🌙")
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

# -------------------- Mute (Discord Timeout) --------------------
@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_cmd(ctx: commands.Context, user: str = None, duration: str = None):
    if not user or not duration:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+mute <user|id|@mention> <durée>` (ex : 10m, 1h)\n⚠️ Max: 28 jours"))
    
    seconds = parse_duration(duration)
    if seconds is None or seconds <= 0:
        return await ctx.send(embed=error_embed("Durée invalide", "❌ Exemple : 30s, 10m, 1h, 2d\n⚠️ Maximum : 28 jours"))
    
    # Discord timeout max: 28 days
    if seconds > 28 * 86400:
        return await ctx.send(embed=error_embed("Durée trop longue", "❌ La durée maximale est de 28 jours."))
    
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible de mute", "❌ L'utilisateur n'est pas membre du serveur."))
    
    # Calculate timeout until
    timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
    
    try:
        await target.timeout(timeout_until, reason=f"Mute par {ctx.author}")
        
        # Try to DM the user
        try:
            await target.send(f"🔇 Tu as été mis en timeout sur **{ctx.guild.name}** pour {duration}. Tu ne pourras pas envoyer de messages jusqu'à la fin du timeout.")
        except:
            pass
        
        await ctx.send(embed=embed_action(
            discord.Color.dark_magenta(), 
            "Timeout", 
            f"🔇 {target.mention} a été mis en timeout pour {duration}. Il/elle ne pourra pas envoyer de messages ni rejoindre les vocaux."
        ))
    except discord.Forbidden:
        await ctx.send(embed=error_embed("Erreur de permissions", "❌ Je n'ai pas la permission de timeout ce membre (rôle trop élevé ou permissions manquantes)."))
    except Exception as e:
        print("mute error:", e)
        await ctx.send(embed=error_embed("Erreur", f"Impossible de mute cet utilisateur: {str(e)}"))

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_cmd(ctx: commands.Context, *, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+unmute <user|id|@mention>`"))
    
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible d'unmute", "❌ L'utilisateur n'est pas membre du serveur."))
    
    # Check if user is timed out
    if target.timed_out_until is None:
        return await ctx.send(embed=error_embed("Non mute", "❌ Cet utilisateur n'est pas en timeout."))
    
    try:
        await target.timeout(None, reason=f"Unmute par {ctx.author}")
        
        # Try to DM the user
        try:
            await target.send(f"✅ Ton timeout sur **{ctx.guild.name}** a été levé. Tu peux de nouveau participer normalement !")
        except:
            pass
        
        await ctx.send(embed=embed_action(discord.Color.green(), "Unmute", f"🔊 {target.mention} a été unmute !"))
    except discord.Forbidden:
        await ctx.send(embed=error_embed("Erreur de permissions", "❌ Je n'ai pas la permission d'unmute ce membre."))
    except Exception as e:
        print("unmute error:", e)
        await ctx.send(embed=error_embed("Erreur", f"Impossible d'unmute cet utilisateur: {str(e)}"))

# -------------------- on_ready: set status --------------------
@bot.event
async def on_ready():
    # Set bot status
    await bot.change_presence(activity=discord.Game("Hoshikuzu | +help"))
    print(f"[MOD BOT] connecté comme {bot.user} ({bot.user.id})")

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
