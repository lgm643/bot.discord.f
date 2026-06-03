import io

import discord

from bot.utils.helpers import now_utc, now_str
from bot.utils.logs import get_log_channel


async def generate_transcript(channel: discord.TextChannel) -> str:
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        ts = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
        author = discord.utils.escape_markdown(str(msg.author))
        content = msg.content.replace("<", "&lt;").replace(">", "&gt;") or "<em>embed/fichier</em>"
        messages.append(f'<tr><td class="ts">{ts}</td><td class="author">{author}</td><td>{content}</td></tr>')
    rows = "\n".join(messages)
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<title>Transcript – {channel.name}</title><style>
body{{font-family:Arial,sans-serif;background:#1e1e2e;color:#cdd6f4;padding:20px}}
h1{{color:#cba6f7}}table{{width:100%;border-collapse:collapse;margin-top:16px}}
th{{background:#313244;color:#89b4fa;padding:8px 12px;text-align:left}}
td{{padding:6px 12px;border-bottom:1px solid #313244;vertical-align:top}}
.ts{{color:#a6adc8;white-space:nowrap;width:160px}}.author{{color:#f38ba8;white-space:nowrap;width:180px}}
</style></head><body>
<h1>📄 Transcript – #{channel.name}</h1>
<p>Généré le {now_utc().strftime("%d/%m/%Y à %H:%M UTC")}</p>
<table><thead><tr><th>Horodatage</th><th>Auteur</th><th>Message</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""


async def send_ticket_log(guild, ticket_channel, closer):
    ch = await get_log_channel(guild)
    if not ch:
        return
    html = await generate_transcript(ticket_channel)
    file = discord.File(fp=io.BytesIO(html.encode("utf-8")), filename=f"transcript-{ticket_channel.name}.html")
    embed = discord.Embed(title="📁 Ticket fermé", color=0x9B59B6, timestamp=now_utc())
    embed.add_field(name="🎫 Ticket", value=ticket_channel.name, inline=True)
    embed.add_field(name="👤 Fermé par", value=closer.mention, inline=True)
    embed.add_field(name="🕐 Date", value=now_str(), inline=True)
    try:
        await ch.send(embed=embed, file=file)
    except Exception as e:
        print(f"[LOG] Erreur ticket : {e}")
