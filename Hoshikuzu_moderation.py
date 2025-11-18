#!/usr/bin/env python3
# Hoshikuzu_complete.py
# Bot de modération complet avec système de vérification et rôles de statut
# Requires: discord.py==2.3.2
# Configure DISCORD_BOT_TOKEN in environment variables before running.

import os, json, asyncio, datetime, threading, http.server, socketserver
from typing import Optional, Dict, Any, Union, List

import discord
from discord.ext import commands
from discord import app_commands

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
intents.presences = True

bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

# -------------------- Configuration storage --------------------
STATUS_CONFIG_FILE = "status_roles.json"
VERIFICATION_CONFIG_FILE = "verification_config.json"

def load_config(filename):
    """Charge une configuration depuis un fichier JSON"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(config, filename):
    """Sauvegarde une configuration dans un fichier JSON"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

status_config = load_config(STATUS_CONFIG_FILE)
verification_config = load_config(VERIFICATION_CONFIG_FILE)

# -------------------- Liste des rôles à créer --------------------
ROLES_TO_CREATE = [
    # STAFF EXÉCUTIF
    {"name": "Owner", "color": 0xFF0000},
    {"name": "Co-Owner", "color": 0xFF4500},
    {"name": "Super Admin", "color": 0xFF6347},
    {"name": "Admin", "color": 0xFF7F50},
    {"name": "Manager Général", "color": 0xFFA500},
    {"name": "Responsable Sécurité", "color": 0xFFB347},
    {"name": "Responsable Communauté", "color": 0xFFC04C},
    {"name": "Responsable Partenariats", "color": 0xFFD700},
    {"name": "Responsable Communication", "color": 0xFFE135},
    
    # STAFF MODÉRATION
    {"name": "Head Mod", "color": 0x9B59B6},
    {"name": "Modérateur Senior", "color": 0xA569BD},
    {"name": "Modérateur", "color": 0xAF7AC5},
    {"name": "Modérateur Test", "color": 0xBB8FCE},
    {"name": "Helper Senior", "color": 0xC39BD3},
    {"name": "Helper", "color": 0xD2B4DE},
    {"name": "Support Staff", "color": 0xE8DAEF},
    
    # STAFF TECHNIQUE
    {"name": "Développeur", "color": 0x3498DB},
    {"name": "Designer", "color": 0x5DADE2},
    {"name": "Graphiste", "color": 0x85C1E2},
    {"name": "Monteur Vidéo", "color": 0xAED6F1},
    {"name": "Tech Support", "color": 0xBBDEFB},
    {"name": "Bot Manager", "color": 0xD4E6F1},
    
    # ANIMATION / SOCIAL
    {"name": "Animateur", "color": 0xE74C3C},
    {"name": "Organisateur d'Évents", "color": 0xEC7063},
    {"name": "Rédacteur", "color": 0xF1948A},
    {"name": "Ambassadeur", "color": 0xF5B7B1},
    {"name": "Comédien", "color": 0xF8C9C1},
    
    # RÔLES SPÉCIAUX
    {"name": "VIP+", "color": 0xF1C40F},
    {"name": "VIP", "color": 0xF4D03F},
    {"name": "Boosters du Serveur", "color": 0xF39C12},
    {"name": "Top Donateur", "color": 0xE67E22},
    {"name": "Membre Privilégié", "color": 0xF8B500},
    {"name": "Partenaire Vérifié", "color": 0xD68910},
    
    # ACTIVITÉ
    {"name": "Légende", "color": 0x1ABC9C},
    {"name": "Elite", "color": 0x48C9B0},
    {"name": "Actif+", "color": 0x76D7C4},
    {"name": "Actif", "color": 0xA3E4D7},
    {"name": "Sociable", "color": 0xC8E6C9},
    {"name": "Nouveau Actif", "color": 0xE8F5E9},
    
    # RÔLES MEMBRES
    {"name": "Membre Vérifié", "color": 0x2ECC71},
    {"name": "Membre", "color": 0x95A5A6},
    {"name": "Nouveau", "color": 0xBDC3C7},
    {"name": "En Attente de Vérification", "color": 0x7F8C8D},
    
    # RÔLES SYSTÈME
    {"name": "Bots", "color": 0x607D8B},
    {"name": "Système Auto", "color": 0x546E7A},
    {"name": "Muted", "color": 0x424242},
    {"name": "Warned", "color": 0xFF5722}
]

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
    
    if user_str.isdigit():
        member = ctx.guild.get_member(int(user_str))
        if member:
            return member
        try:
            return await bot.fetch_user(int(user_str))
        except:
            pass
    
    member = discord.utils.find(lambda m: m.name.lower() == user_str.lower() or m.display_name.lower() == user_str.lower(), ctx.guild.members)
    if member:
        return member
    return None

def embed_action(color: discord.Color, title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    return e

def error_embed(title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=discord.Color.red())
    return e

# -------------------- Système de vérification --------------------
class VerifyButton(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
    
    @discord.ui.button(label="✅ Me vérifier", style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Ce bouton n'est pas pour toi !", ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        if guild_id not in verification_config:
            return await interaction.response.send_message("❌ Configuration manquante !", ephemeral=True)
        
        config = verification_config[guild_id]
        member = interaction.user
        
        try:
            # Retire le rôle non vérifié
            unverified_role = interaction.guild.get_role(config.get("unverified_role_id"))
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role)
            
            # Ajoute les rôles vérifiés
            verified_roles = []
            for role_id in config.get("verified_role_ids", []):
                role = interaction.guild.get_role(role_id)
                if role:
                    verified_roles.append(role)
            
            if verified_roles:
                await member.add_roles(*verified_roles)
            
            roles_names = ", ".join([r.name for r in verified_roles])
            await interaction.response.send_message(
                f"✅ **Vérification réussie !**\nTu as reçu les rôles: {roles_names}\nBienvenue sur le serveur ! 🎉",
                ephemeral=True
            )
            
            # Édite le message original
            verified_embed = discord.Embed(
                title="✅ Membre vérifié !",
                description=f"{member.mention} s'est vérifié avec succès !",
                color=discord.Color.green()
            )
            verified_embed.set_thumbnail(url=member.display_avatar.url)
            verified_embed.set_footer(text=f"ID: {member.id}")
            verified_embed.timestamp = datetime.datetime.now()
            
            await interaction.message.edit(embed=verified_embed, view=None)
            
        except Exception as e:
            print(f"Erreur vérification: {e}")
            await interaction.response.send_message("❌ Erreur lors de la vérification.", ephemeral=True)

@bot.event
async def on_member_join(member: discord.Member):
    """Système d'accueil et de vérification automatique"""
    guild_id = str(member.guild.id)
    
    if guild_id not in verification_config:
        return
    
    config = verification_config[guild_id]
    
    # Ajoute le rôle non vérifié
    unverified_role = member.guild.get_role(config.get("unverified_role_id"))
    if unverified_role:
        try:
            await member.add_roles(unverified_role)
            print(f"✅ Rôle '{unverified_role.name}' attribué à {member.name}")
        except Exception as e:
            print(f"Erreur attribution rôle: {e}")
    
    # Envoie le message de bienvenue dans le salon de vérification
    verification_channel = member.guild.get_channel(config.get("verification_channel_id"))
    if verification_channel:
        welcome_embed = discord.Embed(
            title="🎉 Bienvenue sur le serveur !",
            description=(
                f"Salut {member.mention} !\n\n"
                "Pour accéder au serveur, tu dois te vérifier en cliquant sur le bouton ci-dessous.\n\n"
                "Une fois vérifié, tu auras accès à tous les salons ! 🚀"
            ),
            color=discord.Color.blue()
        )
        welcome_embed.set_thumbnail(url=member.display_avatar.url)
        welcome_embed.set_footer(text=f"ID: {member.id}")
        welcome_embed.timestamp = datetime.datetime.now()
        
        view = VerifyButton(member.id)
        
        try:
            await verification_channel.send(
                content=f"{member.mention}",
                embed=welcome_embed,
                view=view
            )
        except Exception as e:
            print(f"Erreur envoi message bienvenue: {e}")

# -------------------- Système de statut --------------------
async def check_and_apply_status_role(member: discord.Member) -> bool:
    """Vérifie et applique le rôle de statut pour un membre"""
    if member.bot:
        return False
    
    guild_id = str(member.guild.id)
    if guild_id not in status_config:
        return False
    
    custom_status = None
    for activity in member.activities:
        if isinstance(activity, discord.CustomActivity):
            custom_status = activity.name
            break
    
    if not custom_status:
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
    
    for status_text, config in status_config[guild_id].items():
        role = member.guild.get_role(config["role_id"])
        if not role:
            continue
        
        if status_text in custom_status_lower:
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Statut contient: {config['original_text']}")
                    applied = True
                except:
                    pass
        else:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Statut ne contient plus: {config['original_text']}")
                except:
                    pass
    
    return applied

@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    """Détecte les changements de statut"""
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
    
    if before_status != after_status:
        await check_and_apply_status_role(after)

# -------------------- Commandes de configuration --------------------
@bot.command(name="setupverification")
@commands.has_permissions(administrator=True)
async def setup_verification(ctx: commands.Context):
    """Configure le système de vérification complet"""
    await ctx.send("🔧 Configuration en cours... Création des rôles et du salon de vérification.")
    
    guild = ctx.guild
    stats = {"roles_created": [], "roles_existing": [], "channels_created": []}
    
    # Crée tous les rôles
    for role_data in ROLES_TO_CREATE:
        existing_role = discord.utils.get(guild.roles, name=role_data["name"])
        if existing_role:
            stats["roles_existing"].append(role_data["name"])
        else:
            try:
                await guild.create_role(
                    name=role_data["name"],
                    color=discord.Color(role_data["color"]),
                    mentionable=False
                )
                stats["roles_created"].append(role_data["name"])
            except Exception as e:
                print(f"Erreur création rôle {role_data['name']}: {e}")
    
    # Crée le salon de vérification
    try:
        verification_channel = await guild.create_text_channel(
            name="✅・vérification",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False,
                    view_channel=True,
                    read_message_history=True
                )
            }
        )
        stats["channels_created"].append("✅・vérification")
        
        info_embed = discord.Embed(
            title="📋 Salon de Vérification",
            description="Les nouveaux membres apparaîtront ici avec un bouton de vérification.",
            color=discord.Color.blue()
        )
        info_embed.timestamp = datetime.datetime.now()
        await verification_channel.send(embed=info_embed)
        
    except Exception as e:
        print(f"Erreur création salon: {e}")
        return await ctx.send("❌ Erreur lors de la création du salon de vérification.")
    
    # Affiche les statistiques
    stats_embed = discord.Embed(
        title="✅ Création terminée !",
        color=discord.Color.green()
    )
    stats_embed.add_field(name="📊 Rôles créés", value=f"{len(stats['roles_created'])} rôles", inline=True)
    stats_embed.add_field(name="📋 Rôles existants", value=f"{len(stats['roles_existing'])} rôles", inline=True)
    stats_embed.add_field(name="📢 Salons créés", value="\n".join(stats["channels_created"]), inline=False)
    
    await ctx.send(embed=stats_embed)
    
    # Configuration interactive
    config_embed = discord.Embed(
        title="⚙️ Configuration des rôles",
        description=(
            "**Étape suivante :** Configure les rôles de vérification\n\n"
            "1. Utilise `/configverif unverified <@role>` pour définir le rôle non vérifié\n"
            "2. Utilise `/configverif verified <@role>` pour ajouter un rôle après vérification\n"
            "3. Tu peux ajouter plusieurs rôles vérifiés en répétant la commande 2"
        ),
        color=discord.Color.orange()
    )
    await ctx.send(embed=config_embed)
    
    # Initialise la config
    guild_id = str(guild.id)
    verification_config[guild_id] = {
        "verification_channel_id": verification_channel.id,
        "unverified_role_id": None,
        "verified_role_ids": []
    }
    save_config(verification_config, VERIFICATION_CONFIG_FILE)

@bot.command(name="configverif")
@commands.has_permissions(administrator=True)
async def config_verif(ctx: commands.Context, config_type: str = None, role: discord.Role = None):
    """Configure les rôles de vérification"""
    if not config_type or not role:
        return await ctx.send(embed=error_embed(
            "Usage manquant",
            "❌ Utilisation :\n"
            "`+configverif unverified <@role>` - Définir le rôle non vérifié\n"
            "`+configverif verified <@role>` - Ajouter un rôle après vérification"
        ))
    
    guild_id = str(ctx.guild.id)
    if guild_id not in verification_config:
        return await ctx.send(embed=error_embed(
            "Configuration manquante",
            "❌ Utilise d'abord `/setupverification` pour initialiser le système."
        ))
    
    if config_type.lower() == "unverified":
        verification_config[guild_id]["unverified_role_id"] = role.id
        save_config(verification_config, VERIFICATION_CONFIG_FILE)
        await ctx.send(embed=embed_action(
            discord.Color.green(),
            "Rôle non vérifié défini",
            f"✅ Le rôle **{role.name}** sera attribué aux nouveaux membres."
        ))
    
    elif config_type.lower() == "verified":
        if role.id not in verification_config[guild_id]["verified_role_ids"]:
            verification_config[guild_id]["verified_role_ids"].append(role.id)
            save_config(verification_config, VERIFICATION_CONFIG_FILE)
            await ctx.send(embed=embed_action(
                discord.Color.green(),
                "Rôle vérifié ajouté",
                f"✅ Le rôle **{role.name}** sera attribué après vérification."
            ))
        else:
            await ctx.send("⚠️ Ce rôle est déjà configuré.")
    
    else:
        await ctx.send(embed=error_embed(
            "Type invalide",
            "❌ Utilise `unverified` ou `verified`"
        ))

# -------------------- Commandes de statut --------------------
@bot.command(name="setstatus")
@commands.has_permissions(manage_roles=True)
async def setstatus_cmd(ctx: commands.Context, role: discord.Role = None, *, status_text: str = None):
    """Configure un rôle à donner automatiquement selon le statut"""
    if not role or not status_text:
        return await ctx.send(embed=error_embed(
            "Usage manquant",
            "❌ Utilisation : `+setstatus <@role> <texte du statut>`\n\n"
            "Exemple : `+setstatus @Hoshikuzu /hoshikuzu`"
        ))
    
    guild_id = str(ctx.guild.id)
    if guild_id not in status_config:
        status_config[guild_id] = {}
    
    status_key = status_text.lower().strip()
    
    status_config[guild_id][status_key] = {
        "role_id": role.id,
        "role_name": role.name,
        "original_text": status_text
    }
    save_config(status_config, STATUS_CONFIG_FILE)
    
    embed = embed_action(
        discord.Color.purple(),
        "Status Role Configuré",
        f"🌟 Les membres qui mettent **{status_text}** dans leur statut recevront {role.mention}\n\n"
        f"💡 Le bot vérifiera si le statut contient ce texte (insensible à la casse)."
    )
    await ctx.send(embed=embed)
    
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
        return await ctx.send(embed=error_embed(
            "Usage manquant",
            "❌ Utilisation : `+removestatus <texte du statut>`"
        ))
    
    guild_id = str(ctx.guild.id)
    status_key = status_text.lower().strip()
    
    if guild_id not in status_config or status_key not in status_config[guild_id]:
        return await ctx.send(embed=error_embed(
            "Statut introuvable",
            f"❌ Aucune configuration trouvée pour : **{status_text}**"
        ))
    
    role_name = status_config[guild_id][status_key]["role_name"]
    del status_config[guild_id][status_key]
    
    if not status_config[guild_id]:
        del status_config[guild_id]
    
    save_config(status_config, STATUS_CONFIG_FILE)
    
    await ctx.send(embed=embed_action(
        discord.Color.green(),
        "Configuration Retirée",
        f"✅ La configuration pour **{status_text}** (rôle: {role_name}) a été supprimée."
    ))

@bot.command(name="liststatus")
async def liststatus_cmd(ctx: commands.Context):
    """Liste tous les statuts configurés"""
    guild_id = str(ctx.guild.id)
    
    if guild_id not in status_config or not status_config[guild_id]:
        return await ctx.send(embed=error_embed(
            "Aucune configuration",
            "❌ Aucun statut n'est configuré.\n\nUtilise `+setstatus <@role> <texte>` pour en créer un."
        ))
    
    embed = discord.Embed(title="🌟 Statuts Configurés", color=discord.Color.purple())
    
    for status_text, config in status_config[guild_id].items():
        role = ctx.guild.get_role(config["role_id"])
        role_mention = role.mention if role else f"~~{config['role_name']}~~ (rôle supprimé)"
        embed.add_field(
            name=f"📝 {config['original_text']}", 
            value=f"→ {role_mention}",
            inline=False
        )
    
    embed.set_footer(text="Les membres avec ces textes dans leur statut recevront le rôle correspondant")
    await ctx.send(embed=embed)

# -------------------- Commandes de modération --------------------
@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_cmd(ctx: commands.Context, amount: int = 5):
    """Supprime des messages"""
    if amount < 1 or amount > 100:
        return await ctx.send(embed=error_embed("Valeur invalide", "Le nombre doit être entre 1 et 100."))
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(embed=embed_action(discord.Color.blue(), "Clear", f"🧹 {len(deleted) - 1} messages supprimés."), delete_after=5)

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_cmd(ctx: commands.Context, *, user: str = None):
    """Expulse un membre"""
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+kick <user|id|@mention>`"))
    target = await fetch_user_or_member(ctx, user)
    if not target or not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Membre introuvable."))
    try:
        await target.kick(reason=f"Kick par {ctx.author}")
        await ctx.send(embed=embed_action(discord.Color.orange(), "Expulsion", f"👢 {target.mention} a été expulsé !"))
    except Exception as e:
        await ctx.send(embed=error_embed("Erreur", "Impossible d'expulser cet utilisateur."))

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_cmd(ctx: commands.Context, *, user: str = None):
    """Bannit un utilisateur"""
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+ban <user|id|@mention>`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilisateur introuvable."))
    try:
        if isinstance(target, discord.Member):
            await target.ban(reason=f"Ban par {ctx.author}", delete_message_days=0)
        else:
            await ctx.guild.ban(discord.Object(id=int(target.id)), reason=f"Ban par {ctx.author}")
        await ctx.send(embed=embed_action(discord.Color.red(), "Bannissement", f"⛔ {target.mention if isinstance(target, discord.Member) else target} a été banni !"))
    except Exception as e:
        await ctx.send(embed=error_embed("Erreur", "Impossible de bannir cet utilisateur."))

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_cmd(ctx: commands.Context, user_id: str = None):
    """Débannit un utilisateur"""
    if not user_id or not user_id.isdigit():
        return await ctx.send(embed=error_embed("ID invalide", "❌ Utilisation : `+unban <user_id>`"))
    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user, reason=f"Unban par {ctx.author}")
        await ctx.send(embed=embed_action(discord.Color.green(), "Débannissement", f"✅ {user} a été débanni."))
    except Exception as e:
        await ctx.send(embed=error_embed("Erreur", "Impossible de débannir (ID invalide ou pas banni)."))

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_cmd(ctx: commands.Context, user: str = None, duration: str = None):
    """Met un membre en timeout"""
    if not user or not duration:
        return await ctx.send(embed=error_embed(
            "Usage manquant",
            "❌ Utilisation : `+mute <user|id|@mention> <durée>`\n"
            "Exemple : 10m, 1h, 2d\n⚠️ Max: 28 jours"
        ))
    
    seconds = parse_duration(duration)
    if seconds is None or seconds <= 0 or seconds > 28 * 86400:
        return await ctx.send(embed=error_embed(
            "Durée invalide",
            "❌ Exemple : 30s, 10m, 1h, 2d\n⚠️ Maximum : 28 jours"
        ))
    
    target = await fetch_user_or_member(ctx, user)
    if not target or not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Membre introuvable."))
    
    timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
    
    try:
        await target.timeout(timeout_until, reason=f"Mute par {ctx.author}")
        
        try:
            await target.send(f"🔇 Tu as été mis en timeout sur **{ctx.guild.name}** pour {duration}.")
        except:
            pass
        
        await ctx.send(embed=embed_action(
            discord.Color.dark_magenta(),
            "Timeout",
            f"🔇 {target.mention} a été mis en timeout pour {duration}."
        ))
    except Exception as e:
        await ctx.send(embed=error_embed("Erreur", "Impossible de mute cet utilisateur."))

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_cmd(ctx: commands.Context, *, user: str = None):
    """Retire le timeout d'un membre"""
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+unmute <user|id|@mention>`"))
    
    target = await fetch_user_or_member(ctx, user)
    if not target or not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Membre introuvable."))
    
    if target.timed_out_until is None:
        return await ctx.send(embed=error_embed("Non mute", "❌ Cet utilisateur n'est pas en timeout."))
    
    try:
        await target.timeout(None, reason=f"Unmute par {ctx.author}")
        
        try:
            await target.send(f"✅ Ton timeout sur **{ctx.guild.name}** a été levé !")
        except:
            pass
        
        await ctx.send(embed=embed_action(discord.Color.green(), "Unmute", f"🔊 {target.mention} a été unmute !"))
    except Exception as e:
        await ctx.send(embed=error_embed("Erreur", "Impossible d'unmute cet utilisateur."))

# -------------------- Commande d'aide --------------------
@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    """Affiche l'aide complète"""
    embed = discord.Embed(
        title="🛡️ Hoshikuzu — Bot de Modération Complet",
        description="Voici toutes les commandes disponibles :",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="⚙️ Configuration",
        value=(
            "`+setupverification` - Configure le système de vérification complet\n"
            "`+configverif unverified <@role>` - Définir le rôle non vérifié\n"
            "`+configverif verified <@role>` - Ajouter un rôle vérifié"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🌟 Status Roles",
        value=(
            "`+setstatus <@role> <texte>` - Donne un rôle selon le statut\n"
            "`+removestatus <texte>` - Retire une config de statut\n"
            "`+liststatus` - Voir les statuts configurés"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🧹 Modération Messages",
        value="`+clear [nombre]` - Supprimer des messages (1-100)",
        inline=False
    )
    
    embed.add_field(
        name="👮 Modération Membres",
        value=(
            "`+kick <user>` - Expulser un membre\n"
            "`+ban <user>` - Bannir un utilisateur\n"
            "`+unban <user_id>` - Débannir un utilisateur"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔇 Timeout",
        value=(
            "`+mute <user> <durée>` - Timeout temporaire (ex: 10m, 1h)\n"
            "`+unmute <user>` - Annuler un timeout"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📝 Informations",
        value=(
            "`+setbio` - Info sur la modification de la bio du bot\n"
            "`+help` - Affiche cette aide"
        ),
        inline=False
    )
    
    embed.set_footer(text="Hoshikuzu | Bot de modération complet 🌙")
    embed.timestamp = datetime.datetime.now()
    
    await ctx.send(embed=embed)

@bot.command(name="setbio")
async def setbio_cmd(ctx: commands.Context):
    """Instructions pour modifier la bio du bot"""
    embed = discord.Embed(
        title="📝 Modifier la bio du bot",
        description=(
            "**Pour modifier la bio (À propos de moi) du bot :**\n\n"
            "1. Va sur le [Discord Developer Portal](https://discord.com/developers/applications)\n"
            "2. Sélectionne ton application\n"
            "3. Va dans **Bot** dans le menu de gauche\n"
            "4. Trouve la section **About Me** (À propos de moi)\n"
            "5. Modifie le texte et sauvegarde\n\n"
            "⚠️ Seul le créateur du bot peut modifier cette section."
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# -------------------- Événements du bot --------------------
@bot.event
async def on_ready():
    """Événement de connexion du bot"""
    await bot.change_presence(
        activity=discord.Game("Hoshikuzu | +help"),
        status=discord.Status.online
    )
    print(f"[BOT] ✅ Connecté en tant que {bot.user} ({bot.user.id})")
    print(f"[BOT] 📊 Présent sur {len(bot.guilds)} serveur(s)")
    
    # Applique les rôles de statut aux membres existants
    for guild in bot.guilds:
        guild_id = str(guild.id)
        if guild_id in status_config:
            print(f"[STATUS] 🔍 Vérification des statuts pour {guild.name}...")
            for member in guild.members:
                await check_and_apply_status_role(member)
    
    # Enregistre les boutons persistants
    bot.add_view(VerifyButton(0))  # user_id=0 sera remplacé par l'ID réel
    print("[BOT] ✅ Boutons de vérification enregistrés")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    """Gestion des erreurs de commandes"""
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        return
    if isinstance(error, (commands.MemberNotFound, commands.BadArgument)):
        return
    if isinstance(error, commands.MissingPermissions):
        return
    print(f"[ERREUR] Commande {ctx.command}: {error}")

# -------------------- Gestion des erreurs globales --------------------
@bot.event
async def on_error(event, *args, **kwargs):
    """Gestion des erreurs globales"""
    print(f"[ERREUR] Événement {event}")

# -------------------- Démarrage du bot --------------------
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    
    if not TOKEN:
        print("❌ DISCORD_BOT_TOKEN non défini dans les variables d'environnement !")
        print("📝 Ajoute la variable d'environnement DISCORD_BOT_TOKEN et relance.")
        exit(1)
    
    print("=" * 60)
    print("🌙 HOSHIKUZU - Bot de Modération Complet")
    print("=" * 60)
    print("📦 Fonctionnalités :")
    print("  ✅ Système de vérification automatique")
    print("  ✅ Rôles automatiques basés sur le statut")
    print("  ✅ Commandes de modération complètes")
    print("  ✅ Clear, Kick, Ban, Unban, Mute, Unmute")
    print("  ✅ Création automatique de 50+ rôles")
    print("=" * 60)
    print("🚀 Démarrage du bot...")
    print("=" * 60)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Token invalide ! Vérifie ton DISCORD_BOT_TOKEN.")
    except Exception as e:
        print(f"❌ Erreur de connexion : {e}")
