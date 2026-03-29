import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="highlight_match")
def highlight_match(value, query):
    """
    Highlight query matches with <mark> while keeping output escaped.
    """
    if value in (None, ""):
        return ""

    text = str(value)
    search = (query or "").strip()
    if not search:
        return conditional_escape(text)

    pattern = re.compile(re.escape(search), re.IGNORECASE)
    highlighted_parts = []
    start = 0

    for match in pattern.finditer(text):
        highlighted_parts.append(conditional_escape(text[start:match.start()]))
        highlighted_parts.append(f"<mark>{conditional_escape(match.group(0))}</mark>")
        start = match.end()

    highlighted_parts.append(conditional_escape(text[start:]))
    return mark_safe("".join(map(str, highlighted_parts)))
