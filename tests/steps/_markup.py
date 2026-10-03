import re
from html import unescape

DATA = re.compile(r'data-([a-z0-9_-]+)="([^"]*)"')
ROW = re.compile(r"<li\b([^>]*)>(.*?)</li>", re.S)
FIELD = re.compile(r'data-field="([a-z0-9_-]+)">(.*?)<', re.S)
PAIR = re.compile(r"<dt>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
HREF = re.compile(r'href="([^"]*)"')
TAG = re.compile(r"<[^>]+>")
ROLE = re.compile(r'<[a-z]+\b([^>]*\bdata-role="([a-z0-9_-]+)"[^>]*)>')


def reads_page(response):
    return response.get_data(as_text=True)


def strips_tags(fragment):
    return " ".join(unescape(TAG.sub(" ", fragment)).split())


def reads_fields(fragment):
    return {name: strips_tags(value) for name, value in FIELD.findall(fragment)}


def reads_field(page, name):
    return reads_fields(page).get(name)


def reads_rows(page, role):
    found = []
    for match in ROW.finditer(page):
        attributes = dict(DATA.findall(match.group(1)))
        if attributes.get("row") != role:
            continue
        found.append(
            {
                **attributes,
                **reads_fields(match.group(2)),
                "text": strips_tags(match.group(2)),
                "links": HREF.findall(match.group(2)),
            }
        )
    return found


def reads_pairs(page):
    return {strips_tags(label): strips_tags(value) for label, value in PAIR.findall(page)}


def reads_field_link(page, name):
    found = re.search(rf'<a\b[^>]*href="([^"]*)"[^>]*data-field="{name}"', page)
    return unescape(found.group(1)) if found else None


def reads_links(page):
    return HREF.findall(page)


def reads_roles(page):
    return {role: dict(DATA.findall(attributes)) for attributes, role in ROLE.findall(page)}


def reads_role(page, role):
    return reads_roles(page).get(role)
