# Hoshikuzu_moderation_embed.py (part 2/2)
# continuation — moderation commands, mute scheduling, on_ready, error handling, run

# ---------------- moderation commands ----------------
@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_cmd(ctx: commands.Context, amount: int = 5):
    if amount < 1 or amount > 100:
        return await ctx.send(embed=error_embed("Valeur invalide", "Le nombre doit être entre 1 et 100."))
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(embed=embed_action(discord.Color.blue(), "Clear", f"🧹 {len(deleted)} messages supprimés."), delete_after=5)

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_cmd(ctx: commands.Context, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+kick <user|id|@mention>`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible d'expulser", "❌ L'utilisateur n'est pas membre du serveur."))
    try:
        await target.kick(reason=None)
        await ctx.send(embed=embed_action(discord.Color.orange(), "Expulsion", f"👢 {target.mention} a été expulsé·e du serveur !"))
    except Exception as e:
        print("kick error:", e)
        await ctx.send(embed=error_embed("Erreur", "Impossible d'expulser cet utilisateur."))

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_cmd(ctx: commands.Context, user: str = None):
    if not user:
        return await ctx.send(embed=error_embed("Usage manquant", "❌ Utilisation : `+ban <user|id|@mention>`"))
    target = await fetch_user_or_member(ctx, user)
    if not target:
        return await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
    try:
        if isinstance(target, discord.Member):
            await target.ban(reason=None, delete_message_days=0)
            await ctx.send(embed=embed_action(discord.Color.red(), "Bannissement", f"⛔ {target.mention} a été banni du serveur !"))
        else:
            # ban by id (object)
            await ctx.guild.ban(discord.Object(id=int(target.id)), reason=None)
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
        await ctx.guild.unban(user)
        await ctx.send(embed=embed_action(discord.Color.green(), "Débannissement", f"✅ {user} a été débanni."))
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
    # pick a channel to create invite
    channel = ctx.guild.system_channel or next((c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).create_instant_invite), None)
    invite_url = None
    if channel and channel.permissions_for(ctx.guild.me).create_instant_invite:
        try:
            inv = await channel.create_invite(max_age=seconds + 60, max_uses=1, unique=True, reason=f"mute invite for {getattr(target, 'id', 'unknown')}")
            invite_url = inv.url
        except Exception as e:
            print("Invite creation failed:", e)
    # DM the user if possible, best effort
    try:
        await target.send(f"🔇 Tu as été temporairement expulsé·e de **{ctx.guild.name}** pour {duration}. Tu pourras revenir via ce lien après la durée : {invite_url}" if invite_url else f"🔇 Tu as été temporairement expulsé·e de **{ctx.guild.name}** pour {duration}.")
    except Exception:
        pass
    # if not a member (already out) -> cannot kick
    if not isinstance(target, discord.Member):
        return await ctx.send(embed=error_embed("Impossible d'expulser", "❌ L'utilisateur n'est pas membre du serveur (peut-être déjà exclu)."))
    # perform kick
    try:
        await target.kick(reason=None)
    except Exception as e:
        print("kick during mute failed:", e)
        return await ctx.send(embed=error_embed("Erreur", "Impossible d'expulser l'utilisateur."))
    # store mute and schedule unmute
    unmute_ts = int(datetime.datetime.utcnow().timestamp()) + seconds
    await moddata.add_mute(ctx.guild.id, target.id, unmute_ts, channel.id if channel else None, invite_url)
    await ctx.send(embed=embed_action(discord.Color.dark_magenta(), "Mute temporaire", f"🔇 {target.mention} a été temporairement expulsé·e pour {duration}. Il/elle recevra un lien pour revenir quand le mute sera terminé."))
    await schedule_unmute(ctx.guild, target.id, unmute_ts)

@bot.command(name="unmute")
@commands.has_permissions(kick_members=True)
async def unmute_cmd(ctx: commands.Context, user: str = None):
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
        await target.send(f"✅ Tu as été unmuté·e sur **{ctx.guild.name}**. Voici un lien pour revenir : {invite_url}" if invite_url else f"✅ Tu as été unmuté·e sur **{ctx.guild.name}**.")
    except Exception as e:
        print("Could not DM user on manual unmute:", e)
    # cancel scheduled task if exists
    key = f"{ctx.guild.id}-{int(target.id)}"
    task = _scheduled_unmutes.get(key)
    if task and not task.done():
        task.cancel()
    await moddata.remove_mute(ctx.guild.id, int(target.id))
    await ctx.send(embed=embed_action(discord.Color.green(), "Unmute", f"🔊 {target} a été unmuté·e et invité·e à revenir (si DM possible)."))

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
    # Missing argument
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=error_embed("Argument manquant", f"❌ {error.param.name} est requis. Vérifie la commande."))
        return
    # Member not found or bad argument
    if isinstance(error, (commands.MemberNotFound, commands.BadArgument)):
        await ctx.send(embed=error_embed("Utilisateur introuvable", "❌ Utilise une mention ou un ID valide."))
        return
    # Permissions
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=error_embed("Permission refusée", "❌ Tu n'as pas la permission pour utiliser cette commande."))
        return
    # default
    print("Unhandled command error:", error)
    try:
        await ctx.send(embed=error_embed("Erreur", "Une erreur est survenue en exécutant la commande."))
    except Exception:
        pass

# ---------------- Run ----------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ DISCORD_BOT_TOKEN non défini. Ajoute la variable d'environnement et relance.")
else:
    bot.run(TOKEN)
