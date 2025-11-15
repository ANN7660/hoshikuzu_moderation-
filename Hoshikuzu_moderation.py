#!/usr/bin/env python3
# Hoshikuzu_moderation_embed.py
# Bot de modération avec embeds stylés, timeout (mute natif), clear, kick, ban, unban
# + Système de rôle automatique basé sur le statut personnalisé
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
intents.presences = True  # Requis pour détecter les changements de statut

bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

# -------------------- Configuration storage --------------------
CONFIG_FILE = "status_roles.json"

def load_config():
    """Charge la configuration des rôles de statut"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(config):
    """Sauvegarde la configuration des rôles de statut"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

status_config = load_config()

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
    embed.add_field(name="🌟 Status Role", value="`+setstatus <@role> <texte>` - Donne un rôle aux membres avec un statut contenant le texte\n`+removestatus <texte>` - Retire la config d'un statut\n`+liststatus` - Voir les statuts configurés", inline=False)
    embed.set_footer(text="Hoshikuzu | +help 🌙")
    await ctx.send(embed=embed)

# -------------------- Status Role System --------------------
@bot.command(name="setstatus")
@commands.has_permissions(manage_roles=True)
async def setstatus_cmd(ctx: commands.Context, role: discord.Role = None, *, status_text: str = None):
    """Configure un rôle à donner automatiquement quand un membre met un certain texte dans son statut"""
    if not role or not status_text:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+setstatus <@role> <texte du statut>`\n\nExemple : `+setstatus @Hoshikuzu /hoshikuzu`"))
    
    guild_id = str(ctx.guild.id)
    if guild_id not in status_config:
        status_config[guild_id] = {}
    
    # Normaliser le texte du statut (minuscules pour comparaison)
    status_key = status_text.lower().strip()
    
    status_config[guild_id][status_key] = {
        "role_id": role.id,
        "role_name": role.name,
        "original_text": status_text
    }
    save_config(status_config)
    
    embed = embed_action(
        discord.Color.purple(),
        "Status Role Configuré",
        f"🌟 Les membres qui mettent **{status_text}** dans leur statut recevront automatiquement le rôle {role.mention}\n\n"
        f"💡 Le bot vérifiera si le statut contient ce texte (insensible à la casse)."
    )
    await ctx.send(embed=embed)
    
    # Applique immédiatement aux membres existants
    applied_count = 0
    for member in ctx.guild.members:
        if await check_and_apply_status_role(member):
            applied_count += 1
    
    if applied_count > 0:
        await ctx.send(f"✅ Rôle appliqué à {applied_count} membre(s) existant(s) !", delete_after=5)

@bot.command(name="removestatus")
@commands.has_permissions(manage_roles=True)
async def removestatus_cmd(ctx: commands.Context, *, status_text: str = None):
    """Retire la configuration d'un statut"""
    if not status_text:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+removestatus <texte du statut>`"))
    
    guild_id = str(ctx.guild.id)
    status_key = status_text.lower().strip()
    
    if guild_id not in status_config or status_key not in status_config[guild_id]:
        return await ctx.send(embed=error_embed("Statut introuvable", f"❌ Aucune configuration trouvée pour : **{status_text}**"))
    
    role_name = status_config[guild_id][status_key]["role_name"]
    del status_config[guild_id][status_key]
    
    if not status_config[guild_id]:
        del status_config[guild_id]
    
    save_config(status_config)
    
    await ctx.send(embed=embed_action(
        discord.Color.green(),
        "Configuration Retirée",
        f"✅ La configuration pour **{status_text}** (rôle: {role_name}) a été supprimée."
    ))

@bot.command(name="liststatus")
async def liststatus_cmd(ctx: commands.Context):
    """Liste tous les statuts configurés sur ce serveur"""
    guild_id = str(ctx.guild.id)
    
    if guild_id not in status_config or not status_config[guild_id]:
        return await ctx.send(embed=error_embed("Aucune configuration", "❌ Aucun statut n'est configuré sur ce serveur.\n\nUtilise `+setstatus <@role> <texte>` pour en créer un."))
    
    embed = discord.Embed(title="🌟 Statuts Configurés", color=discord.Color.purple())
    
    for status_text, config in status_config[guild_id].items():
        role = ctx.guild.get_role(config["role_id"])
        role_mention = role.mention if role else f"~~{config['role_name']}~~ (rôle supprimé)"
        embed.add_field(
            name=f"📝 {config['original_text']}", 
            value=f"→ {role_mention}",
            inline=False
        )
    
    embed.set_footer(text="Les membres avec ces textes dans leur statut recevront automatiquement le rôle correspondant")
    await ctx.send(embed=embed)

async def check_and_apply_status_role(member: discord.Member) -> bool:
    """Vérifie et applique le rôle de statut pour un membre"""
    if member.bot:
        return False
    
    guild_id = str(member.guild.id)
    if guild_id not in status_config:
        return False
    
    # Récupère le statut personnalisé du membre
    custom_status = None
    for activity in member.activities:
        if isinstance(activity, discord.CustomActivity):
            custom_status = activity.name
            break
    
    if not custom_status:
        # Pas de statut personnalisé, retire tous les rôles configurés
        for config in status_config[guild_id].values():
            role = member.guild.get_role(config["role_id"])
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Statut personnalisé retiré")
                except:
                    pass
        return False
    
    custom_status_lower = custom_status.lower()
    applied = False
    
    # Vérifie tous les statuts configurés
    for status_text, config in status_config[guild_id].items():
        role = member.guild.get_role(config["role_id"])
        if not role:
            continue
        
        # Si le statut contient le texte configuré
        if status_text in custom_status_lower:
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Statut personnalisé contient: {config['original_text']}")
                    applied = True
                except:
                    pass
        else:
            # Le statut ne contient plus le texte, retire le rôle
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Statut personnalisé ne contient plus: {config['original_text']}")
                except:
                    pass
    
    return applied

@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    """Détecte les changements de statut et applique les rôles"""
    # Vérifie si le statut personnalisé a changé
    before_status = None
    after_status = None
    
    for activity in before.activities:
        if isinstance(activity, discord.CustomActivity):
            before_status = activity.name
            break
    
    for activity in after.activities:
        if isinstance(activity, discord.CustomActivity):
            after_status = activity.name
            break
    
    # Si le statut a changé, vérifie et applique les rôles
    if before_status != after_status:
        await check_and_apply_status_role(after)

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
    
    # Applique les rôles de statut aux membres existants au démarrage
    for guild in bot.guilds:
        guild_id = str(guild.id)
        if guild_id in status_config:
            print(f"[STATUS ROLES] Vérification des statuts pour {guild.name}...")
            for member in guild.members:
                await check_and_apply_status_role(member)

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
