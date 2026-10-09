"""CHANGELOG.md as HTML for the in-app Changelog page.

Only the little Markdown the changelog uses: headings, bullet lists, paragraphs, **bold**,
`code` and [links](https://...). Everything else is escaped, so it's shown, never run.
"""
import html
import re

INLINE = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)"), r'<a href="\2" target="_blank" rel="noopener">\1</a>'),
]


def inline(text):
    text = html.escape(text, quote=True)
    for pattern, replacement in INLINE:
        text = pattern.sub(replacement, text)
    return text


def render(markdown):
    out = []
    paragraph = []
    items = []

    def flush():
        if paragraph:
            out.append("<p>{}</p>".format(inline(" ".join(paragraph))))
            paragraph.clear()
        if items:
            out.append("<ul>{}</ul>".format("".join("<li>{}</li>".format(inline(i)) for i in items)))
            items.clear()

    for line in markdown.splitlines():
        line = line.rstrip()
        heading = re.match(r"(#{1,4}) (.+)", line)
        if heading:
            flush()
            level = len(heading.group(1)) + 2  # the page's own title is above it
            out.append("<h{0}>{1}</h{0}>".format(level, inline(heading.group(2))))
        elif line.startswith("- "):
            if paragraph:
                flush()
            items.append(line[2:])
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()  # a list item carried onto the next line
        elif not line:
            flush()
        else:
            if items:
                flush()
            paragraph.append(line)
    flush()
    return "\n".join(out)
