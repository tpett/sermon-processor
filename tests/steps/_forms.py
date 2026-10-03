import re
from html import unescape

from steps import _web

FORM = re.compile(r'<form\b([^>]*)>(.*?)</form>', re.S)
ACTION = re.compile(r'action="([^"]*)"')
INPUT = re.compile(r"<input\b([^>]*)>")
SELECT = re.compile(r'<select\b[^>]*name="([^"]+)"[^>]*>(.*?)</select>', re.S)
SELECTED = re.compile(r'<option value="([^"]*)" selected>')
ATTRIBUTE = re.compile(r'([a-z-]+)(?:="([^"]*)")?')


def finds_form(page, containing):
    """The rendered form whose markup carries `containing`, as a browser holds it."""
    for attributes, inside in FORM.findall(page):
        if containing in inside or containing in attributes:
            return unescape(ACTION.search(attributes).group(1)), inside
    raise AssertionError(f"the page renders no form carrying {containing!r}")


def fields_of(inside):
    sent = {}
    for raw in INPUT.findall(inside):
        held = dict(ATTRIBUTE.findall(raw))
        if "name" not in held:
            continue
        if held.get("type") == "checkbox" and "checked" not in held:
            continue
        sent[held["name"]] = unescape(held.get("value", ""))
    for name, options in SELECT.findall(inside):
        chosen = SELECTED.search(options)
        if chosen:
            sent[name] = chosen.group(1)
    return sent


def offers_field(inside, name):
    return any(dict(ATTRIBUTE.findall(raw)).get("name") == name for raw in INPUT.findall(inside))


def submits(store, page, containing, **changed):
    action, inside = finds_form(page, containing)
    return _web.posts(store, action, **{**fields_of(inside), **changed})
