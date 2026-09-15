"""Helpers for building Telegram messages out of untrusted text.

Everything that comes from Amazon or from a user — product names, seller
names, URLs — has to be escaped before it goes into a formatted message.

These helpers use HTML rather than Markdown on purpose. Telegram's legacy
Markdown parser also scans the URL inside `[label](url)` for entity markers,
so an Amazon link containing `ref=zg_bs_g123_d_sccl_9` has its underscores
eaten as italics: the href that reaches the user is a different, broken URL.
The same bug mangles a `t.me/<bot>?start=edit_<id>` deep link (both the bot
username and the `edit_<id>` payload lose their underscores, which is why
such links resolve to "username not found"), and drops the link entirely
when the mangled URL no longer parses, leaving bare grey text.
"""

import html


def esc(text) -> str:
    """Escape text for parse_mode="HTML" (also correct inside an attribute)."""
    return html.escape(str(text), quote=True)


def link(label: str, url: str) -> str:
    """An <a> tag with both label and href escaped."""
    return f'<a href="{esc(url)}">{esc(label)}</a>'
