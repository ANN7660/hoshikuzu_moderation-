const { Client, GatewayIntentBits, ChannelType, PermissionFlagsBits, ButtonBuilder, ButtonStyle, ActionRowBuilder, EmbedBuilder, StringSelectMenuBuilder, StringSelectMenuOptionBuilder, REST, Routes } = require('discord.js');
const fs = require('fs');

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMembers,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildPresences
    ]
});

// Configuration
const CONFIG = {};
const CONFIG_FILE = 'bot_config.json';
const STATUS_CONFIG_FILE = 'status_roles.json';

// Charger les configurations
function loadConfig() {
    if (fs.existsSync(STATUS_CONFIG_FILE)) {
        try {
            const data = fs.readFileSync(STATUS_CONFIG_FILE, 'utf8');
            return JSON.parse(data);
        } catch (err) {
            console.error('Erreur chargement config:', err);
        }
    }
    return {};
}

function saveConfig(config) {
    try {
        fs.writeFileSync(STATUS_CONFIG_FILE, JSON.stringify(config, null, 2));
    } catch (err) {
        console.error('Erreur sauvegarde config:', err);
    }
}

const statusConfig = loadConfig();

// Liste complète des rôles à créer
const ROLES_TO_CREATE = [
    // STAFF EXÉCUTIF
    { name: "Owner", color: 0xFF0000 },
    { name: "Co-Owner", color: 0xFF4500 },
    { name: "Super Admin", color: 0xFF6347 },
    { name: "Admin", color: 0xFF7F50 },
    { name: "Manager Général", color: 0xFFA500 },
    { name: "Responsable Sécurité", color: 0xFFB347 },
    { name: "Responsable Communauté", color: 0xFFC04C },
    { name: "Responsable Partenariats", color: 0xFFD700 },
    { name: "Responsable Communication", color: 0xFFE135 },
    
    // STAFF MODÉRATION
    { name: "Head Mod", color: 0x9B59B6 },
    { name: "Modérateur Senior", color: 0xA569BD },
    { name: "Modérateur", color: 0xAF7AC5 },
    { name: "Modérateur Test", color: 0xBB8FCE },
    { name: "Helper Senior", color: 0xC39BD3 },
    { name: "Helper", color: 0xD2B4DE },
    { name: "Support Staff", color: 0xE8DAEF },
    
    // STAFF TECHNIQUE
    { name: "Développeur", color: 0x3498DB },
    { name: "Designer", color: 0x5DADE2 },
    { name: "Graphiste", color: 0x85C1E2 },
    { name: "Monteur Vidéo", color: 0xAED6F1 },
    { name: "Tech Support", color: 0xBBDEFB },
    { name: "Bot Manager", color: 0xD4E6F1 },
    
    // ANIMATION / SOCIAL
    { name: "Animateur", color: 0xE74C3C },
    { name: "Organisateur d'Évents", color: 0xEC7063 },
    { name: "Rédacteur", color: 0xF1948A },
    { name: "Ambassadeur", color: 0xF5B7B1 },
    { name: "Comédien", color: 0xF8C9C1 },
    
    // RÔLES SPÉCIAUX
    { name: "VIP+", color: 0xF1C40F },
    { name: "VIP", color: 0xF4D03F },
    { name: "Boosters du Serveur", color: 0xF39C12 },
    { name: "Top Donateur", color: 0xE67E22 },
    { name: "Membre Privilégié", color: 0xF8B500 },
    { name: "Partenaire Vérifié", color: 0xD68910 },
    
    // ACTIVITÉ
    { name: "Légende", color: 0x1ABC9C },
    { name: "Elite", color: 0x48C9B0 },
    { name: "Actif+", color: 0x76D7C4 },
    { name: "Actif", color: 0xA3E4D7 },
    { name: "Sociable", color: 0xC8E6C9 },
    { name: "Nouveau Actif", color: 0xE8F5E9 },
    
    // RÔLES MEMBRES
    { name: "Membre Vérifié", color: 0x2ECC71 },
    { name: "Membre", color: 0x95A5A6 },
    { name: "Nouveau", color: 0xBDC3C7 },
    { name: "En Attente de Vérification", color: 0x7F8C8D },
    
    // RÔLES SYSTÈME
    { name: "Bots", color: 0x607D8B },
    { name: "Système Auto", color: 0x546E7A },
    { name: "Muted", color: 0x424242 },
    { name: "Warned", color: 0xFF5722 }
];

// ==================== UTILITAIRES ====================

function parseDuration(s) {
    try {
        if (s.endsWith('s')) return parseInt(s.slice(0, -1));
        if (s.endsWith('m')) return parseInt(s.slice(0, -1)) * 60;
        if (s.endsWith('h')) return parseInt(s.slice(0, -1)) * 3600;
        if (s.endsWith('d')) return parseInt(s.slice(0, -1)) * 86400;
    } catch (err) {
        return null;
    }
    return null;
}

async function findUser(guild, userStr) {
    // Mention
    const mentionMatch = userStr.match(/^<@!?(\d+)>$/);
    if (mentionMatch) {
        const member = guild.members.cache.get(mentionMatch[1]);
        if (member) return member;
        try {
            return await client.users.fetch(mentionMatch[1]);
        } catch (err) {
            return null;
        }
    }
    
    // ID
    if (/^\d+$/.test(userStr)) {
        const member = guild.members.cache.get(userStr);
        if (member) return member;
        try {
            return await client.users.fetch(userStr);
        } catch (err) {
            return null;
        }
    }
    
    // Nom
    const member = guild.members.cache.find(m => 
        m.user.username.toLowerCase() === userStr.toLowerCase() ||
        m.displayName.toLowerCase() === userStr.toLowerCase()
    );
    return member || null;
}

function checkConfigComplete(interaction, guildConfig) {
    if (guildConfig.unverifiedRoleId && guildConfig.verifiedRoleIds.length > 0) {
        interaction.followUp({ 
            content: '✅ Configuration complète ! Le système de vérification est maintenant actif.', 
            ephemeral: true 
        });
    }
}

// ==================== SYSTÈME DE VÉRIFICATION ====================

client.on('guildMemberAdd', async (member) => {
    try {
        const guildConfig = CONFIG[member.guild.id];
        if (!guildConfig) return;

        const unverifiedRole = member.guild.roles.cache.get(guildConfig.unverifiedRoleId);
        if (unverifiedRole) {
            await member.roles.add(unverifiedRole);
            console.log(`✅ Rôle "${unverifiedRole.name}" attribué à ${member.user.tag}`);
        }

        const verificationChannel = member.guild.channels.cache.get(guildConfig.verificationChannelId);
        if (verificationChannel) {
            const welcomeEmbed = new EmbedBuilder()
                .setColor(0x5865F2)
                .setTitle('🎉 Bienvenue sur le serveur !')
                .setDescription(
                    `Salut ${member} !\n\n` +
                    `Pour accéder au serveur, tu dois te vérifier en cliquant sur le bouton ci-dessous.\n\n` +
                    `Une fois vérifié, tu auras accès à tous les salons ! 🚀`
                )
                .setThumbnail(member.user.displayAvatarURL({ dynamic: true }))
                .setFooter({ text: `ID: ${member.id}` })
                .setTimestamp();

            const verifyButton = new ButtonBuilder()
                .setCustomId(`verify_${member.id}`)
                .setLabel('✅ Me vérifier')
                .setStyle(ButtonStyle.Success);

            const row = new ActionRowBuilder().addComponents(verifyButton);

            await verificationChannel.send({
                content: `${member}`,
                embeds: [welcomeEmbed],
                components: [row]
            });
        }
    } catch (error) {
        console.error('Erreur ajout membre:', error);
    }
});

// ==================== SYSTÈME DE STATUT ====================

async function checkAndApplyStatusRole(member) {
    if (member.bot) return false;
    
    const guildId = member.guild.id.toString();
    if (!statusConfig[guildId]) return false;
    
    let customStatus = null;
    for (const activity of member.presence?.activities || []) {
        if (activity.type === 4) {
            customStatus = activity.state;
            break;
        }
    }
    
    if (!customStatus) {
        for (const config of Object.values(statusConfig[guildId])) {
            const role = member.guild.roles.cache.get(config.role_id);
            if (role && member.roles.cache.has(role.id)) {
                try {
                    await member.roles.remove(role, 'Statut personnalisé retiré');
                } catch (err) {}
            }
        }
        return false;
    }
    
    const customStatusLower = customStatus.toLowerCase();
    let applied = false;
    
    for (const [statusText, config] of Object.entries(statusConfig[guildId])) {
        const role = member.guild.roles.cache.get(config.role_id);
        if (!role) continue;
        
        if (customStatusLower.includes(statusText)) {
            if (!member.roles.cache.has(role.id)) {
                try {
                    await member.roles.add(role, `Statut contient: ${config.original_text}`);
                    applied = true;
                } catch (err) {}
            }
        } else {
            if (member.roles.cache.has(role.id)) {
                try {
                    await member.roles.remove(role, `Statut ne contient plus: ${config.original_text}`);
                } catch (err) {}
            }
        }
    }
    
    return applied;
}

client.on('presenceUpdate', async (oldPresence, newPresence) => {
    if (!newPresence.member) return;
    
    const oldStatus = oldPresence?.activities.find(a => a.type === 4)?.state;
    const newStatus = newPresence.activities.find(a => a.type === 4)?.state;
    
    if (oldStatus !== newStatus) {
        await checkAndApplyStatusRole(newPresence.member);
    }
});

// ==================== COMMANDES SLASH ====================

const commands = [
    {
        name: 'setupverification',
        description: 'Configure le système de vérification',
    },
    {
        name: 'setstatus',
        description: 'Configure un rôle automatique basé sur le statut',
        options: [
            { name: 'role', type: 8, description: 'Le rôle à attribuer', required: true },
            { name: 'texte', type: 3, description: 'Le texte à rechercher dans le statut', required: true }
        ],
    },
    {
        name: 'removestatus',
        description: 'Retire la configuration d\'un statut',
        options: [
            { name: 'texte', type: 3, description: 'Le texte du statut à retirer', required: true }
        ],
    },
    {
        name: 'liststatus',
        description: 'Liste tous les statuts configurés',
    },
    {
        name: 'clear',
        description: 'Supprime des messages',
        options: [
            { name: 'nombre', type: 4, description: 'Nombre de messages à supprimer (1-100)', required: true }
        ],
    },
    {
        name: 'kick',
        description: 'Expulse un membre',
        options: [
            { name: 'user', type: 3, description: 'Utilisateur à expulser', required: true }
        ],
    },
    {
        name: 'ban',
        description: 'Bannit un utilisateur',
        options: [
            { name: 'user', type: 3, description: 'Utilisateur à bannir', required: true }
        ],
    },
    {
        name: 'unban',
        description: 'Débannit un utilisateur',
        options: [
            { name: 'user_id', type: 3, description: 'ID de l\'utilisateur à débannir', required: true }
        ],
    },
    {
        name: 'mute',
        description: 'Met un membre en timeout',
        options: [
            { name: 'user', type: 3, description: 'Utilisateur à mute', required: true },
            { name: 'duree', type: 3, description: 'Durée (ex: 10m, 1h, 2d)', required: true }
        ],
    },
    {
        name: 'unmute',
        description: 'Retire le timeout d\'un membre',
        options: [
            { name: 'user', type: 3, description: 'Utilisateur à unmute', required: true }
        ],
    },
    {
        name: 'setbio',
        description: 'Instructions pour modifier la bio du bot',
    },
    {
        name: 'help',
        description: 'Affiche l\'aide',
    }
];

client.on('interactionCreate', async (interaction) => {
    if (interaction.isButton()) {
        // Bouton de vérification
        if (interaction.customId.startsWith('verify_')) {
            const targetUserId = interaction.customId.split('_')[1];
            if (interaction.user.id !== targetUserId) {
                return interaction.reply({ content: '❌ Ce bouton n\'est pas pour toi !', ephemeral: true });
            }

            try {
                const member = interaction.member;
                const guildConfig = CONFIG[interaction.guild.id];
                const unverifiedRole = interaction.guild.roles.cache.get(guildConfig.unverifiedRoleId);
                const rolesToAdd = guildConfig.verifiedRoleIds.map(id => 
                    interaction.guild.roles.cache.get(id)
                ).filter(Boolean);

                if (unverifiedRole) await member.roles.remove(unverifiedRole);
                if (rolesToAdd.length > 0) await member.roles.add(rolesToAdd);

                const rolesNames = rolesToAdd.map(r => r.name).join(', ');
                await interaction.reply({
                    content: `✅ **Vérification réussie !**\nTu as reçu les rôles: ${rolesNames}\nBienvenue sur le serveur ! 🎉`,
                    ephemeral: true
                });

                const verifiedEmbed = new EmbedBuilder()
                    .setColor(0x57F287)
                    .setTitle('✅ Membre vérifié !')
                    .setDescription(`${member} s'est vérifié avec succès !`)
                    .setThumbnail(member.user.displayAvatarURL({ dynamic: true }))
                    .setFooter({ text: `ID: ${member.id}` })
                    .setTimestamp();

                await interaction.message.edit({ embeds: [verifiedEmbed], components: [] });
            } catch (error) {
                console.error('Erreur vérification:', error);
                await interaction.reply({ content: '❌ Erreur lors de la vérification.', ephemeral: true });
            }
        }
    }

    if (interaction.isStringSelectMenu()) {
        const guildConfig = CONFIG[interaction.guild.id];
        if (!guildConfig) return;

        if (interaction.customId === 'select_unverified_role') {
            const roleId = interaction.values[0];
            const role = interaction.guild.roles.cache.get(roleId);
            guildConfig.unverifiedRoleId = roleId;
            await interaction.reply({ content: `✅ Rôle non vérifié défini: **${role.name}**`, ephemeral: true });
            checkConfigComplete(interaction, guildConfig);
        }

        if (interaction.customId === 'select_verified_roles') {
            const roleIds = interaction.values;
            const roles = roleIds.map(id => interaction.guild.roles.cache.get(id));
            guildConfig.verifiedRoleIds = roleIds;
            await interaction.reply({ content: `✅ Rôles après vérification: **${roles.map(r => r.name).join(', ')}**`, ephemeral: true });
            checkConfigComplete(interaction, guildConfig);
        }
    }

    if (!interaction.isChatInputCommand()) return;

    // SETUPVERIFICATION
    if (interaction.commandName === 'setupverification') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        await interaction.reply({ content: '🔧 Configuration en cours...', ephemeral: true });

        try {
            const guild = interaction.guild;
            const stats = { rolesCreated: [], rolesExisting: [], channelsCreated: [] };

            for (const roleData of ROLES_TO_CREATE) {
                const existingRole = guild.roles.cache.find(r => r.name.toLowerCase() === roleData.name.toLowerCase());
                if (existingRole) {
                    stats.rolesExisting.push(roleData.name);
                } else {
                    await guild.roles.create({ name: roleData.name, color: roleData.color, mentionable: false });
                    stats.rolesCreated.push(roleData.name);
                }
            }

            const verificationChannel = await guild.channels.create({
                name: '✅・vérification',
                type: ChannelType.GuildText,
                permissionOverwrites: [{
                    id: guild.roles.everyone,
                    deny: [PermissionFlagsBits.SendMessages],
                    allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory]
                }]
            });
            stats.channelsCreated.push('✅・vérification');

            const infoEmbed = new EmbedBuilder()
                .setColor(0x5865F2)
                .setTitle('📋 Salon de Vérification')
                .setDescription('Les nouveaux membres apparaîtront ici avec un bouton de vérification.')
                .setTimestamp();
            await verificationChannel.send({ embeds: [infoEmbed] });

            const roles = guild.roles.cache
                .filter(role => role.name !== '@everyone' && !role.managed)
                .sort((a, b) => b.position - a.position)
                .first(25);

            const roleOptions = roles.map(role => 
                new StringSelectMenuOptionBuilder()
                    .setLabel(role.name)
                    .setValue(role.id)
                    .setDescription(`Position: ${role.position}`)
            );

            const unverifiedMenu = new StringSelectMenuBuilder()
                .setCustomId('select_unverified_role')
                .setPlaceholder('🔒 Choisis le rôle "Non Vérifié"')
                .addOptions(roleOptions);

            const verifiedMenu = new StringSelectMenuBuilder()
                .setCustomId('select_verified_roles')
                .setPlaceholder('✅ Choisis les rôles après vérification')
                .setMinValues(1)
                .setMaxValues(Math.min(roleOptions.length, 10))
                .addOptions(roleOptions);

            const row1 = new ActionRowBuilder().addComponents(unverifiedMenu);
            const row2 = new ActionRowBuilder().addComponents(verifiedMenu);

            const statsEmbed = new EmbedBuilder()
                .setColor(0x00FF00)
                .setTitle('✅ Création terminée !')
                .addFields(
                    { name: '📊 Rôles créés', value: `${stats.rolesCreated.length} rôles`, inline: true },
                    { name: '📋 Rôles existants', value: `${stats.rolesExisting.length} rôles`, inline: true },
                    { name: '📢 Salons créés', value: stats.channelsCreated.join('\n'), inline: false }
                );

            const configEmbed = new EmbedBuilder()
                .setColor(0xFFA500)
                .setTitle('⚙️ Configuration des rôles')
                .setDescription('Sélectionne les rôles de vérification ci-dessous');

            await interaction.followUp({ embeds: [statsEmbed, configEmbed], components: [row1, row2], ephemeral: true });

            CONFIG[guild.id] = {
                verificationChannelId: verificationChannel.id,
                unverifiedRoleId: null,
                verifiedRoleIds: []
            };
        } catch (error) {
            console.error('Erreur setup:', error);
            await interaction.followUp({ content: '❌ Erreur lors de la configuration.', ephemeral: true });
        }
    }

    // SETSTATUS
    if (interaction.commandName === 'setstatus') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.ManageRoles)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const role = interaction.options.getRole('role');
        const statusText = interaction.options.getString('texte');
        const guildId = interaction.guild.id.toString();

        if (!statusConfig[guildId]) statusConfig[guildId] = {};

        const statusKey = statusText.toLowerCase().trim();
        statusConfig[guildId][statusKey] = {
            role_id: role.id,
            role_name: role.name,
            original_text: statusText
        };
        saveConfig(statusConfig);

        const embed = new EmbedBuilder()
            .setColor(0x9B59B6)
            .setTitle('Status Role Configuré')
            .setDescription(`🌟 Les membres avec **${statusText}** dans leur statut recevront ${role}`);

        await interaction.reply({ embeds: [embed], ephemeral: true });

        let appliedCount = 0;
        for (const member of interaction.guild.members.cache.values()) {
            if (await checkAndApplyStatusRole(member)) appliedCount++;
        }
        if (appliedCount > 0) {
            await interaction.followUp({ content: `✅ Rôle appliqué à ${appliedCount} membre(s) !`, ephemeral: true });
        }
    }

    // REMOVESTATUS
    if (interaction.commandName === 'removestatus') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.ManageRoles)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const statusText = interaction.options.getString('texte');
        const guildId = interaction.guild.id.toString();
        const statusKey = statusText.toLowerCase().trim();

        if (!statusConfig[guildId] || !statusConfig[guildId][statusKey]) {
            return interaction.reply({ content: '❌ Statut introuvable !', ephemeral: true });
        }

        const roleName = statusConfig[guildId][statusKey].role_name;
        delete statusConfig[guildId][statusKey];
        if (Object.keys(statusConfig[guildId]).length === 0) delete statusConfig[guildId];
        saveConfig(statusConfig);

        const embed = new EmbedBuilder()
            .setColor(0x57F287)
            .setTitle('Configuration Retirée')
            .setDescription(`✅ **${statusText}** (${roleName}) supprimé`);

        await interaction.reply({ embeds: [embed], ephemeral: true });
    }

    // LISTSTATUS
    if (interaction.commandName === 'liststatus') {
        const guildId = interaction.guild.id.toString();

        if (!statusConfig[guildId] || Object.keys(statusConfig[guildId]).length === 0) {
            return interaction.reply({ content: '❌ Aucun statut configuré.', ephemeral: true });
        }

        const embed = new EmbedBuilder()
            .setTitle('🌟 Statuts Configurés')
            .setColor(0x9B59B6);

        for (const [statusText, config] of Object.entries(statusConfig[guildId])) {
            const role = interaction.guild.roles.cache.get(config.role_id);
            const roleMention = role ? role.toString() : `~~${config.role_name}~~`;
            embed.addFields({ name: `📝 ${config.original_text}`, value: `→ ${roleMention}`, inline: false });
        }

        await interaction.reply({ embeds: [embed], ephemeral: true });
    }

    // CLEAR
    if (interaction.commandName === 'clear') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.ManageMessages)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const amount = interaction.options.getInteger('nombre');
        if (amount < 1 || amount > 100) {
            return interaction.reply({ content: '❌ Nombre entre 1 et 100 !', ephemeral: true });
        }

        const deleted = await interaction.channel.bulkDelete(amount, true);
        await interaction.reply({ content: `🧹 ${deleted.size} messages supprimés !`, ephemeral: true });
    }

    // KICK
    if (interaction.commandName === 'kick') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.KickMembers)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const userStr = interaction.options.getString('user');
        const target = await findUser(interaction.guild, userStr);

        if (!target || !(target instanceof client.guilds.cache.first().members.cache.first().constructor)) {
            return interaction.reply({ content: '❌ Utilisateur introuvable ou pas membre !', ephemeral: true });
        }

        try {
            await target.kick(`Kick par ${interaction.user.tag}`);
            const embed = new EmbedBuilder()
                .setColor(0xFFA500)
                .setTitle('Expulsion')
                .setDescription(`👢 ${target} a été expulsé !`);
            await interaction.reply({ embeds: [embed] });
        } catch (error) {
            await interaction.reply({ content: '❌ Impossible d\'expulser cet utilisateur.', ephemeral: true });
        }
    }

    // BAN
    if (interaction.commandName === 'ban') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.BanMembers)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const userStr = interaction.options.getString('user');
        const target = await findUser(interaction.guild, userStr);

        if (!target) {
            return interaction.reply({ content: '❌ Utilisateur introuvable !', ephemeral: true });
        }

        try {
            await interaction.guild.members.ban(target.id, { reason: `Ban par ${interaction.user.tag}` });
            const embed = new EmbedBuilder()
                .setColor(0xFF0000)
                .setTitle('Bannissement')
                .setDescription(`⛔ ${target} a été banni !`);
            await interaction.reply({ embeds: [embed] });
        } catch (error) {
            await interaction.reply({ content: '❌ Impossible de bannir cet utilisateur.', ephemeral: true });
        }
    }

    // UNBAN
    if (interaction.commandName === 'unban') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.BanMembers)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const userId = interaction.options.getString('user_id');
        if (!/^\d+$/.test(userId)) {
            return interaction.reply({ content: '❌ ID invalide !', ephemeral: true });
        }

        try {
            const user = await client.users.fetch(userId);
            await interaction.guild.members.unban(userId, `Unban par ${interaction.user.tag}`);
            const embed = new EmbedBuilder()
                .setColor(0x57F287)
                .setTitle('Débannissement')
                .setDescription(`✅ ${user.tag} a été débanni !`);
            await interaction.reply({ embeds: [embed] });
        } catch (error) {
            await interaction.reply({ content: '❌ Impossible de débannir (ID invalide ou pas banni).', ephemeral: true });
        }
    }

    // MUTE
    if (interaction.commandName === 'mute') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const userStr = interaction.options.getString('user');
        const duration = interaction.options.getString('duree');
        const seconds = parseDuration(duration);

        if (!seconds || seconds <= 0 || seconds > 28 * 86400) {
            return interaction.reply({ content: '❌ Durée invalide ! (ex: 10m, 1h, 2d - max 28j)', ephemeral: true });
        }

        const target = await findUser(interaction.guild, userStr);
        if (!target || !target.moderatable) {
            return interaction.reply({ content: '❌ Utilisateur introuvable ou impossible à mute !', ephemeral: true });
        }

        try {
            await target.timeout(seconds * 1000, `Mute par ${interaction.user.tag}`);
            
            try {
                await target.send(`🔇 Tu as été mis en timeout sur **${interaction.guild.name}** pour ${duration}.`);
            } catch (err) {}

            const embed = new EmbedBuilder()
                .setColor(0x5865F2)
                .setTitle('Timeout')
                .setDescription(`🔇 ${target} a été mis en timeout pour ${duration} !`);
            await interaction.reply({ embeds: [embed] });
        } catch (error) {
            await interaction.reply({ content: '❌ Impossible de mute cet utilisateur.', ephemeral: true });
        }
    }

    // UNMUTE
    if (interaction.commandName === 'unmute') {
        if (!interaction.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
            return interaction.reply({ content: '❌ Permission manquante !', ephemeral: true });
        }

        const userStr = interaction.options.getString('user');
        const target = await findUser(interaction.guild, userStr);

        if (!target) {
            return interaction.reply({ content: '❌ Utilisateur introuvable !', ephemeral: true });
        }

        if (!target.isCommunicationDisabled()) {
            return interaction.reply({ content: '❌ Cet utilisateur n\'est pas en timeout.', ephemeral: true });
        }

        try {
            await target.timeout(null, `Unmute par ${interaction.user.tag}`);
            
            try {
                await target.send(`✅ Ton timeout sur **${interaction.guild.name}** a été levé !`);
            } catch (err) {}

            const embed = new EmbedBuilder()
                .setColor(0x57F287)
                .setTitle('Unmute')
                .setDescription(`🔊 ${target} a été unmute !`);
            await interaction.reply({ embeds: [embed] });
        } catch (error) {
            await interaction.reply({ content: '❌ Impossible d\'unmute cet utilisateur.', ephemeral: true });
        }
    }

    // SETBIO
    if (interaction.commandName === 'setbio') {
        const embed = new EmbedBuilder()
            .setColor(0x5865F2)
            .setTitle('📝 Modifier la bio du bot')
            .setDescription(
                '**Pour modifier la bio (À propos de moi) du bot :**\n\n' +
                '1. Va sur le [Discord Developer Portal](https://discord.com/developers/applications)\n' +
                '2. Sélectionne ton application\n' +
                '3. Va dans **Bot** dans le menu de gauche\n' +
                '4. Trouve la section **About Me** (À propos de moi)\n' +
                '5. Modifie le texte et sauvegarde\n\n' +
                '⚠️ Seul le créateur du bot peut modifier cette section.'
            );
        await interaction.reply({ embeds: [embed], ephemeral: true });
    }

    // HELP
    if (interaction.commandName === 'help') {
        const embed = new EmbedBuilder()
            .setColor(0x5865F2)
            .setTitle('🛡️ Aide - Commandes du Bot')
            .setDescription('Voici toutes les commandes disponibles :')
            .addFields(
                { name: '⚙️ Configuration', value: '`/setupverification` - Configure le système de vérification', inline: false },
                { name: '🌟 Status Roles', value: '`/setstatus` - Configure un rôle basé sur le statut\n`/removestatus` - Retire une config\n`/liststatus` - Liste les configs', inline: false },
                { name: '🧹 Modération', value: '`/clear` - Supprime des messages\n`/kick` - Expulse un membre\n`/ban` - Bannit un utilisateur\n`/unban` - Débannit un utilisateur', inline: false },
                { name: '🔇 Timeout', value: '`/mute` - Timeout un membre\n`/unmute` - Retire le timeout', inline: false },
                { name: '📝 Autres', value: '`/setbio` - Info sur la modification de la bio\n`/help` - Affiche cette aide', inline: false }
            )
            .setFooter({ text: 'Bot de modération Discord' });
        await interaction.reply({ embeds: [embed], ephemeral: true });
    }
});

// ==================== ENREGISTREMENT DES COMMANDES ====================

client.once('ready', async () => {
    console.log(`✅ Bot connecté en tant que ${client.user.tag}`);
    
    // Change le statut du bot
    client.user.setPresence({
        activities: [{ name: 'la modération | /help', type: 3 }],
        status: 'online'
    });

    // Enregistre les commandes slash
    const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
    
    try {
        console.log('🔄 Enregistrement des commandes slash...');
        await rest.put(
            Routes.applicationCommands(client.user.id),
            { body: commands }
        );
        console.log('✅ Commandes slash enregistrées !');
    } catch (error) {
        console.error('❌ Erreur lors de l\'enregistrement des commandes:', error);
    }

    // Applique les rôles de statut aux membres existants
    for (const guild of client.guilds.cache.values()) {
        const guildId = guild.id.toString();
        if (statusConfig[guildId]) {
            console.log(`🔍 Vérification des statuts pour ${guild.name}...`);
            for (const member of guild.members.cache.values()) {
                await checkAndApplyStatusRole(member);
            }
        }
    }
});

// ==================== GESTION DES ERREURS ====================

process.on('unhandledRejection', error => {
    console.error('Erreur non gérée:', error);
});

client.on('error', error => {
    console.error('Erreur client:', error);
});

// ==================== DÉMARRAGE ====================

const TOKEN = process.env.DISCORD_TOKEN;
if (!TOKEN) {
    console.error('❌ DISCORD_TOKEN non défini dans les variables d\'environnement !');
    process.exit(1);
}

client.login(TOKEN).catch(err => {
    console.error('❌ Erreur de connexion:', err);
    process.exit(1);
});
