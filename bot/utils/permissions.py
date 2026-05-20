import discord

from bot.utils.config import load_config, resolve_role, resolve_roles


def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = load_config(member.guild.id)
    staff_names = cfg.get("role_staff", [])
    if isinstance(staff_names, str):
        staff_names = [staff_names]
    return any(r in member.roles for r in resolve_roles(member.guild, staff_names))


def is_staff_market(member: discord.Member) -> bool:
    cfg = load_config(member.guild.id)
    role = resolve_role(member.guild, cfg.get("role_staff_market"))
    vendeur = resolve_role(member.guild, cfg.get("role_vendeur"))
    return (role and role in member.roles) or (vendeur and vendeur in member.roles) or is_staff(member)


def is_vendeur(member: discord.Member) -> bool:
    cfg = load_config(member.guild.id)
    role = resolve_role(member.guild, cfg.get("role_vendeur"))
    return (role and role in member.roles) or is_staff(member)
