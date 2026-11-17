"""Minimal HTML -> text using only the standard library."""
import re
from html.parser import HTMLParser

_SKIP = {"script", "style", "noscript", "svg", "template"}
_BLOCK = {"p", "br", "div", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr",
          "section", "article"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self.skip, self.in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "title":
            self.in_title = False
        elif tag in _BLOCK or tag == "li":
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title += data
        else:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    """Returns (text, title)."""
    p = _Extractor()
    p.feed(html)
    p.close()
    text = "".join(p.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, p.title.strip()
