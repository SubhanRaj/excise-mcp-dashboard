"""Render Tabler icon-font glyphs to transparent PNGs for the deck."""
from PIL import Image, ImageDraw, ImageFont
import os, sys
FONT = os.path.expanduser('~/Sites/excise-mcp-dashboard/web/public/vendor/tabler-icons/fonts/tabler-icons.ttf')
ICONS = {
 'question':'f98b','database':'ea88','cpu':'ef8e','shield':'ed58','chart':'ea59','books':'eff2',
 'server':'eb1f','doc':'eaa2','users':'ebf2','clock':'ea70','check':'ea67','search':'eb1c',
 'lock':'eae2','eye':'ea9a','cloudoff':'ed3e','pin':'eae8','rupee':'ebad','bank':'ebe2',
 'bulb':'ea51','alert':'ea06','rocket':'ec45','brain':'f59f','sheet':'f03e','chat':'f38a',
 'receipt':'edfd','line':'ea5c','report':'eecb','cert':'ed4d',
}
COLORS = {'white':(255,255,255)}
out = os.path.join(os.path.dirname(__file__), '..', 'icons')
f = ImageFont.truetype(FONT, 320)
for name, cp in ICONS.items():
    for cname, rgb in COLORS.items():
        im = Image.new('RGBA', (400, 400), (0,0,0,0))
        d = ImageDraw.Draw(im)
        d.text((200,200), chr(int(cp,16)), font=f, fill=rgb+(255,), anchor='mm')
        im.save(os.path.join(out, f'{name}-{cname}.png'))
print(len(ICONS)*len(COLORS), 'icons')
