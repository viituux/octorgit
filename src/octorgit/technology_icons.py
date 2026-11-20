"""Bundled technology marks; no network requests and no user-controlled SVG markup."""
from functools import lru_cache
from importlib.resources import files
import json
import re


@lru_cache(maxsize=1)
def catalog():
    data = json.loads(files('octorgit').joinpath('static/icons/catalog.json').read_text(encoding='utf-8'))
    for slug, icon in data['icons'].items():
        if not re.fullmatch(r'[a-z0-9]+', slug) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', icon['color']):
            raise ValueError('Invalid bundled technology icon.')
        if not icon['paths'] or not all(re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9eE.,+\-\s]+', path) for path in icon['paths']):
            raise ValueError('Invalid bundled technology path.')
    if not all(slug in data['icons'] for slug in data['aliases'].values()):
        raise ValueError('Invalid bundled icon alias.')
    return data


def resolve_icon(name):
    key = re.sub(r'\s+\((?:cliente|driver)\)$', '', name.split(' · ',1)[0].strip().lower())
    slug = catalog()['aliases'].get(key)
    return catalog()['icons'].get(slug)


def svg_mark(name, x, y, size=46):
    icon = resolve_icon(name)
    if not icon:
        return ''
    # Only validated numerical path commands and hexadecimal fills enter SVG.
    paths = ''.join('<path d="'+path+'"/>' for path in icon['paths'])
    return f'<g transform="translate({x} {y}) scale({size/24})" fill="{icon["color"]}">{paths}</g>'
