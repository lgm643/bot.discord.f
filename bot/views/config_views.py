import asyncio
import discord

from bot.core import bot

from bot.utils.config import load_config, save_config
from bot.utils.helpers import now_utc
from bot.utils.config_panel import (
    CONFIG_GROUPS,
    _NUM_KEYS,
    _LIST_KEYS,
    _fmt_cfg_val,
    _build_group_embed,
    _build_home_embed,
)

class _GroupSelect(discord.ui.Select):
    def __init__(self, author_id):
        self.author_id = author_id
        options = []
        for grp in CONFIG_GROUPS:
            opt = discord.SelectOption(label=grp, value=grp)
            options.append(opt)
        super().__init__(placeholder="📂 Choisir une catégorie…", options=options, custom_id="cfg_group_sel")
    async def callback(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return
        group = self.values[0]
        embed = _build_group_embed(interaction.guild, group)
        view  = _GroupView(self.author_id, group, interaction.message)
        await interaction.response.edit_message(embed=embed, view=view)


class _HomeView(discord.ui.View):
    def __init__(self, author_id, msg=None):
        super().__init__(timeout=300)
        self.author_id = author_id; self.msg = msg
        self.add_item(_GroupSelect(author_id))
    async def on_timeout(self):
        if self.msg:
            try:
                for item in self.children: item.disabled = True
                await self.msg.edit(view=self)
            except Exception: pass
    @discord.ui.button(label="❌ Fermer", style=discord.ButtonStyle.red, row=1)
    async def fermer(self, interaction, button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return
        self.stop()
        try: await interaction.message.delete()
        except Exception: pass
        await interaction.response.send_message("👋 Configuration fermée.", ephemeral=True)


class _KeySelect(discord.ui.Select):
    def __init__(self, author_id, group, orig_msg):
        self.author_id = author_id; self.group = group; self.orig_msg = orig_msg
        options = [discord.SelectOption(label=label[:50], value=key, description=f"clé : {key}") for key, label, _ in CONFIG_GROUPS[group]]
        super().__init__(placeholder="🔑 Choisir la clé à modifier…", options=options[:25], custom_id="cfg_key_sel")

    async def callback(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return
        key     = self.values[0]
        label   = next((lbl for k, lbl, _ in CONFIG_GROUPS[self.group] if k == key), key)
        is_list = key in _LIST_KEYS
        is_num  = key in _NUM_KEYS
        is_salon = "salon" in key or "categorie" in key
        is_role  = "role" in key

        if is_list and is_salon:   action = "➕ `+nom-du-salon` · ➖ `-nom-du-salon` · 🔄 `salon1, salon2`"
        elif is_list and is_role:  action = "➕ `+NomDuRole` · ➖ `-NomDuRole` · 🔄 `Role1, Role2`"
        elif is_list:              action = "➕ `+valeur` · ➖ `-valeur` · 🔄 `val1, val2`"
        elif is_num:               action = "Tapez un **nombre entier** (ex: `30`)"
        elif is_salon:             action = "Tapez le **nom exact** du salon ou mentionnez-le avec `#`"
        elif is_role:              action = "Tapez le **nom exact** du rôle ou mentionnez-le avec `@`"
        else:                      action = "Tapez la nouvelle valeur"

        cfg = load_config(interaction.guild.id)
        cur = _fmt_cfg_val(interaction.guild, key, cfg.get(key, "—"))
        embed = discord.Embed(
            title=f"✏️ Modifier : {label}",
            description=f"**Clé :** `{key}`\n**Valeur actuelle :** {cur}\n\n{action}\n\n💬 Répondez dans ce salon **(60 secondes)**.\nTapez `annuler` pour abandonner.",
            color=0x3498DB, timestamp=now_utc()
        )
        embed.set_footer(text="⏱️ 60 secondes pour répondre")
        await interaction.response.edit_message(embed=embed, view=None)

        guild = interaction.guild
        def chk(m): return m.author.id == self.author_id and m.channel.id == interaction.channel.id
        try:    msg = await bot.wait_for("message", check=chk, timeout=60)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Temps écoulé.", ephemeral=True)
            await self.orig_msg.edit(embed=_build_group_embed(guild, self.group), view=_GroupView(self.author_id, self.group, self.orig_msg))
            return

        try: await msg.delete()
        except Exception: pass
        valeur = msg.content.strip()

        if valeur.lower() == "annuler":
            await interaction.followup.send("❌ Modification annulée.", ephemeral=True)
            await self.orig_msg.edit(embed=_build_group_embed(guild, self.group), view=_GroupView(self.author_id, self.group, self.orig_msg))
            return

        cfg = load_config(guild.id)
        if is_num:
            try: cfg[key] = float(valeur) if "." in valeur else int(valeur)
            except ValueError:
                await interaction.followup.send(f"❌ `{key}` attend un nombre.", ephemeral=True)
                await self.orig_msg.edit(embed=_build_group_embed(guild, self.group), view=_GroupView(self.author_id, self.group, self.orig_msg))
                return
        elif is_list:
            current = cfg.get(key, [])
            if isinstance(current, str): current = [current]
            if valeur.startswith("+"):
                to_add = valeur[1:].strip()
                if to_add and to_add not in current: current.append(to_add)
                cfg[key] = current
            elif valeur.startswith("-"):
                cfg[key] = [x for x in current if str(x).lower() != valeur[1:].strip().lower()]
            else:
                cfg[key] = [v.strip() for v in valeur.split(",") if v.strip()]
        else:
            # CORRECTION #1 : on retire uniquement les chevrons de mention (<, >, #, @, &)
            # mais on garde le contenu brut (nom ou ID) proprement
            cleaned = re.sub(r"[<#@&>]", "", valeur).strip()
            cfg[key] = cleaned

        save_config(guild.id, cfg)
        val_saved   = cfg[key]
        val_display = (", ".join(f"`{v}`" for v in val_saved) if isinstance(val_saved, list) else f"`{val_saved}`")
        await interaction.followup.send(embed=discord.Embed(title="✅ Mis à jour !", description=f"**{label}**\n`{key}` → {val_display}", color=0x2ECC71, timestamp=now_utc()), ephemeral=True)
        await self.orig_msg.edit(embed=_build_group_embed(guild, self.group), view=_GroupView(self.author_id, self.group, self.orig_msg))


class _GroupView(discord.ui.View):
    def __init__(self, author_id, group, orig_msg):
        super().__init__(timeout=300)
        self.author_id = author_id; self.group = group; self.orig_msg = orig_msg
        self.add_item(_KeySelect(author_id, group, orig_msg))
    async def on_timeout(self):
        try:
            for item in self.children: item.disabled = True
            await self.orig_msg.edit(view=self)
        except Exception: pass
    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.grey, row=1)
    async def retour(self, interaction, button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return
        await interaction.response.edit_message(embed=_build_home_embed(interaction.guild), view=_HomeView(self.author_id, interaction.message))
    @discord.ui.button(label="❌ Fermer", style=discord.ButtonStyle.red, row=1)
    async def fermer(self, interaction, button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return
        self.stop()
        try: await interaction.message.delete()
        except Exception: pass
        await interaction.response.send_message("👋 Configuration fermée.", ephemeral=True)