"""Build the demo deck. Run: python3 build/build_deck.py"""
import os
import shutil
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # deck/source
PKG = os.path.dirname(ROOT)           # deck/  (the folder that gets shared)
IMAGES = os.path.join(PKG, 'images')
os.makedirs(IMAGES, exist_ok=True)
ICONS = os.path.join(ROOT, 'icons')
SHOTS = os.environ.get('SHOTS', os.path.join(ROOT, 'shots'))
OUT = os.path.join(PKG, 'UP-Excise-Ask-the-Data-Demo.pptx')

# Palette taken from the department flag (yellow over blue), softened to pastels.
BLUE = RGBColor(0x24, 0x3B, 0x7A)        # headings and key figures
BLUE_MID = RGBColor(0x3E, 0x5C, 0xA8)    # icon badges
PASTEL_BLUE = RGBColor(0xEA, 0xF0, 0xFB)  # card and header ground
PASTEL_BLUE_2 = RGBColor(0xC9, 0xD9, 0xF3)  # title-slide blue field
BORDER = RGBColor(0xD0, 0xDB, 0xF0)
PASTEL_YELLOW = RGBColor(0xFF, 0xF3, 0xC4)  # highlight bars
PASTEL_YELLOW_2 = RGBColor(0xFF, 0xE9, 0x8F)  # title-slide yellow field
GOLD = RGBColor(0xE0, 0xB1, 0x2A)
DARK_GOLD = RGBColor(0x8A, 0x63, 0x00)
INK = RGBColor(0x1F, 0x29, 0x37)
GREY = RGBColor(0x4B, 0x55, 0x63)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
VIOLET, SAFFRON, TINT, GREEN = BLUE, GOLD, PASTEL_BLUE, BLUE
FONT = 'Calibri'
HINDI_FONT = 'Nirmala UI'  # ships with Windows 10+; Office falls back to Mangal / Devanagari Sangam MN

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
state = {'n': 0}


def text(slide, x, y, w, h, s, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=None, hindi=False):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    lines = s if isinstance(s, list) else [s]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
        r.font.color.rgb = color
        if hindi:
            # Unicode Devanagari: set the complex-script and East Asian faces, and the language.
            rpr = r._r.get_or_add_rPr()
            rpr.set('lang', 'hi-IN')
            r.font.name = HINDI_FONT
            for tag in ('a:ea', 'a:cs'):
                el = rpr.makeelement(qn(tag), {'typeface': HINDI_FONT})
                rpr.append(el)
    return tb


def box(slide, x, y, w, h, fill=TINT, line='auto', shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line == 'auto':
        line = BORDER if fill == TINT else None
    if line:
        s.line.color.rgb = line
        s.line.width = Pt(1.25)
    else:
        s.line.fill.background()
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.shadow.inherit = False
    return s


def icon(slide, name, x, y, size=0.5, color='violet'):
    slide.shapes.add_picture(os.path.join(ICONS, f'{name}-{color}.png'),
                             Inches(x), Inches(y), Inches(size), Inches(size))


def badge(slide, name, x, y, d=0.8, fill=BLUE_MID):
    box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    pad = d * 0.22
    icon(slide, name, x + pad, y + pad, d - 2 * pad, 'white')


def arrow(slide, x, y, w=0.5, h=0.4, fill=SAFFRON):
    s = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def new_slide(title):
    state['n'] += 1
    s = prs.slides.add_slide(BLANK)
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(1.0))
    band.fill.solid(); band.fill.fore_color.rgb = PASTEL_BLUE; band.line.fill.background()
    acc = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(1.0), prs.slide_width, Inches(0.07))
    acc.fill.solid(); acc.fill.fore_color.rgb = GOLD; acc.line.fill.background()
    text(s, 0.6, 0.12, 11.4, 0.76, title, 30, True, BLUE, anchor=MSO_ANCHOR.MIDDLE)
    s.shapes.add_picture(os.path.join(ICONS, 'emblem-dark.png'), Inches(12.3), Inches(0.1),
                         height=Inches(0.8))
    text(s, 0.6, 7.06, 9, 0.3, 'Government of Uttar Pradesh  |  Department of Excise  |  Ask the Data: proof of concept',
         10, False, GREY)
    text(s, 12.0, 7.06, 0.8, 0.3, str(state['n']), 10, False, GREY, PP_ALIGN.RIGHT)
    return s


def crop_shot(name, left_px=512, top_px=0, bottom_px=None):
    """Crop the app sidebar off a 3200x2000 screenshot; return path or None."""
    src = os.path.join(SHOTS, name)
    if not os.path.exists(src):
        return None
    dst = os.path.join(HERE, 'crops', name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im = Image.open(src)
    im.crop((left_px, top_px, im.width, bottom_px or im.height)).save(dst)
    return dst


def shot(slide, name, x, y, w, h, left_px=512, bottom_px=None, top_px=0, link=None):
    """Place a screenshot inside the w x h frame, keeping its aspect ratio."""
    path = crop_shot(name, left_px, top_px, bottom_px)
    box(slide, x - 0.05, y - 0.05, w + 0.1, h + 0.1, fill=WHITE, line=RGBColor(0xD5, 0xD2, 0xE8))
    if not path:
        text(slide, x, y + h / 2 - 0.2, w, 0.4, f'[screenshot pending: {name}]', 14, False, GREY,
             PP_ALIGN.CENTER)
        return
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    pic = slide.shapes.add_picture(path, Inches(x + (w - pw) / 2), Inches(y + (h - ph) / 2),
                                   Inches(pw), Inches(ph))
    if link:
        # The full-size original goes in images/ beside the deck; a click opens it in the
        # system image viewer (relative link, so the folder works on any OS and location).
        shutil.copy(os.path.join(SHOTS, name), os.path.join(IMAGES, link))
        pic.click_action.hyperlink.address = f'images/{link}'


def bullets(slide, x, y, w, items, size=18, gap=10, color=INK):
    tb = text(slide, x, y, w, 0.5, items, size, False, color, spacing=gap)
    return tb


# 1 ---------------------------------------------------------------- title
state['n'] += 1
s = prs.slides.add_slide(BLANK)
W, H = prs.slide_width, prs.slide_height
yel = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
yel.fill.solid(); yel.fill.fore_color.rgb = PASTEL_YELLOW_2; yel.line.fill.background()
# blue field below the flag's diagonal: from the bottom-left corner up to the right edge
fb = s.shapes.build_freeform(0, H)
fb.add_line_segments([(W, Inches(1.2)), (W, H)], close=True)
blue = fb.convert_to_shape()
blue.fill.solid(); blue.fill.fore_color.rgb = PASTEL_BLUE_2; blue.line.fill.background()
s.shapes.add_picture(os.path.join(ICONS, 'emblem-dark.png'), Inches(0.8), Inches(0.7), height=Inches(1.6))
text(s, 2.8, 0.75, 9.5, 0.5, 'Government of Uttar Pradesh', 22, False, INK)
text(s, 2.8, 1.25, 9.5, 0.7, 'Department of Excise', 36, True, BLUE)
text(s, 2.8, 1.95, 9.5, 0.5, 'उत्तर प्रदेश आबकारी विभाग', 22, False, INK, hindi=True)
text(s, 0.8, 3.0, 11.5, 1.2, 'Ask the Data', 60, True, BLUE)
text(s, 0.8, 4.15, 9.0, 1.6, ['Ask a question in plain language.',
     'The answer comes from the department\'s own figures and rules, on the department\'s own server.'],
     24, False, INK, spacing=6)
text(s, 0.8, 6.55, 11.5, 0.5, 'Proof of concept', 18, False, BLUE)
notes(s, 'Welcome. This is a working proof of concept, not a mock-up. Everything in the demo slides came '
         'from the live system running in the department\'s office. It answered real questions against '
         'real department data.')

# 2 ---------------------------------------------------------------- problem
s = new_slide('The problem: a simple question can take days')
cards = [
    ('sheet', 'Figures sit in many files', 'Revenue, dispatch, shop and enforcement figures are held in separate '
     'workbooks, reports and portals.'),
    ('clock', 'Each question needs an analyst', 'An officer asks, an analyst finds the files, builds the table and '
     'sends it back. A new angle starts the cycle again.'),
    ('books', 'Rules live in another place', 'Acts, rules and policy orders are published as documents. '
     'Linking a rule to a figure is done by hand.'),
]
for i, (ic, h, b) in enumerate(cards):
    x = 0.6 + i * 4.1
    box(s, x, 1.6, 3.85, 3.6)
    badge(s, ic, x + 0.3, 1.9)
    text(s, x + 0.25, 2.9, 3.4, 0.8, h, 22, True, VIOLET)
    text(s, x + 0.25, 3.7, 3.4, 1.6, b, 16, False, INK)
text(s, 0.6, 5.55, 12.1, 1.2, 'An officer who needs a number for a meeting today should get it today, '
     'with its source, without waiting for a report.', 20, True, INK)
notes(s, 'Set the scene in the department\'s own terms. Two examples to mention: a district total needed before '
         'a review meeting, and a rule position needed alongside a figure.')

# 3 ---------------------------------------------------------------- what it does
s = new_slide('What this proof of concept does')
text(s, 0.6, 1.3, 12.1, 0.8, 'An officer types a question in everyday English. The system finds the answer in the '
     'department\'s data, draws a chart where it helps, and shows the exact query it used.', 20, False, INK)
three = [
    ('question', 'Ask', 'One question, one answer page: the figure, a chart, a plain summary and the query behind it.'),
    ('chat', 'Chat', 'A conversation that can look up figures and rules as it goes, and take follow-up questions.'),
    ('books', 'Knowledge library', 'Excise acts, rules and policy orders, searchable in the same chat.'),
]
for i, (ic, h, b) in enumerate(three):
    x = 0.6 + i * 4.1
    box(s, x, 2.6, 3.85, 3.0)
    badge(s, ic, x + 0.3, 2.85)
    text(s, x + 1.25, 2.95, 2.5, 0.6, h, 24, True, VIOLET, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.3, 3.9, 3.35, 1.7, b, 17, False, INK)
text(s, 0.6, 5.85, 12.1, 1.0, ['It runs on the departmental server, completely local.',
     'No external AI service provider and no closed-source or proprietary tool is used. All models run locally.'],
     19, True, GREEN, spacing=4)
notes(s, 'We built three entry points on one engine. Ask takes a single well-formed question. Chat is for '
         'exploring. The knowledge library lets the same chat quote the department\'s published rules.')

# 4 ---------------------------------------------------------------- how an answer is made
s = new_slide('How an answer is made')
steps = [
    ('question', '1  You ask', 'Type the question the way you would put it to a colleague.'),
    ('brain', '2  The system understands', 'An AI model turns the question into a precise search of the data.'),
    ('database', '3  The data answers', 'The search runs against the department\'s data bank, read-only.'),
    ('chart', '4  You see the result', 'A figure, a chart, a short summary and the exact query used.'),
]
for i, (ic, h, b) in enumerate(steps):
    x = 0.55 + i * 3.2
    box(s, x, 1.7, 2.75, 3.7)
    badge(s, ic, x + 0.97, 1.95, 0.85)
    text(s, x + 0.1, 2.95, 2.55, 0.6, h, 19, True, VIOLET, PP_ALIGN.CENTER)
    text(s, x + 0.15, 3.6, 2.45, 1.7, b, 16, False, INK, PP_ALIGN.CENTER)
    if i < 3:
        arrow(s, x + 2.78, 3.35, 0.38, 0.4)
box(s, 0.55, 5.75, 12.2, 1.05, fill=PASTEL_YELLOW, line=GOLD)
text(s, 0.8, 5.8, 11.7, 0.95, 'Every answer shows its working. The query is visible and can be copied, so an officer '
     'or an auditor can check where a number came from.', 19, True, BLUE, anchor=MSO_ANCHOR.MIDDLE)
notes(s, 'This is the one picture to remember. The key point for this audience: the AI does not invent figures. '
         'It writes a search; the database returns the numbers. The query is always displayed.')

# 5 ---------------------------------------------------------------- demo ask 1
s = new_slide('Live example: how many shops, and of which kind?')
text(s, 0.6, 1.25, 4.3, 0.9, '"How many country liquor and composite shops are in Lucknow in August 2026?"',
     18, True, VIOLET)
bullets(s, 0.6, 2.35, 4.3, [
    'Total: 1,006 shops.',
    'Split: 589 country liquor and 417 composite.',
    'The database counts the total; the AI does not add it up.',
    'Source: the monthly dispatch report from the Integrated Excise Supply Chain Management System (IESCMS).',
], 16, 12)
shot(s, 'ask-1-view.png', 5.15, 1.3, 7.6, 5.55, left_px=1360, top_px=145, link='slide-05-shop-count.png')
notes(s, 'Click the screenshot to open it full size. Read the question aloud, then point to the total and the two parts. This question was chosen because '
         'it has a split and a total. Earlier versions gave one combined number; we fixed that so each part is shown.')

# 6 ---------------------------------------------------------------- demo ask 2
s = new_slide('Live example: revenue by district and for a product')
shot(s, 'ask-2-view.png', 0.6, 1.95, 6.0, 3.95, link='slide-06a-top-district-revenue.png')
shot(s, 'ask-3-view.png', 6.75, 1.95, 6.0, 3.95, link='slide-06b-beer-revenue.png')
text(s, 0.6, 1.2, 6.0, 0.6, '"Which district generated the highest revenue in FY2025-26?"', 15, True, VIOLET)
text(s, 6.75, 1.2, 6.0, 0.6, '"How much revenue came from beer sale across Uttar Pradesh in FY2025-26?"', 15, True, VIOLET)
text(s, 0.6, 6.1, 6.0, 0.9, 'Lucknow is the highest, at ₹2,860.80 crore out of a state total of about ₹55,463 crore.',
     16, False, INK)
text(s, 6.75, 6.1, 6.0, 0.9, 'Beer revenue is ₹7,142.87 crore: ₹6,740.18 crore from composite shops and '
     '₹402.69 crore from country liquor shops that also sell beer (CL5CC).', 16, False, INK)
notes(s, 'Click either screenshot to open it full size. Money is shown in rupees with lakh and crore, never in dollars. The system converts the figures in code, '
         'not by asking the AI to do the arithmetic, after an early version got a crore conversion wrong.')

# 7 ---------------------------------------------------------------- demo chat 1
s = new_slide('Live example: a conversation with a chart')
text(s, 0.6, 1.25, 4.3, 0.9, '"Which district generated the highest revenue in FY2025-26?"', 18, True, VIOLET)
bullets(s, 0.6, 2.35, 4.3, [
    'The same question in Chat: the answer first, then the chart.',
    'Lucknow is highest at ₹2,860.80 crore, from all 75 districts.',
    'The chart downloads as PNG, SVG or PDF, and the whole conversation exports as a PDF.',
    'The query behind the answer stays one click away.',
], 16, 12)
shot(s, 'chat-3-view.png', 5.15, 1.3, 7.6, 5.55, left_px=1090, top_px=145, link='slide-07-chat-top-district.png')
notes(s, 'Click the screenshot to open it full size. Point at the chart, then the "Show query" control under the answer. The chart toggle in the message box '
         'asks for a chart explicitly.')

# 9 ---------------------------------------------------------------- data
s = new_slide('The data behind the answers')
tiles = [
    ('truck' if False else 'receipt', '9,322', 'dispatch records for Lucknow, August 2026, from the Integrated Excise Supply Chain Management System'),
    ('pin', '28,405', 'shops with FY2025-26 revenue, across all 75 districts'),
    ('rupee', '3,455', 'district revenue records from the Rajkosh and Koshwani portal data'),
    ('chart', '3,812', 'sales-volume records by liquor type and year'),
    ('shield', '11,124', 'enforcement records: raids, seizures, convictions'),
    ('books', '330+', 'acts, rules and policy documents in the knowledge library'),
]
for i, (ic, n, label) in enumerate(tiles):
    col, row = i % 3, i // 3
    x, y = 0.6 + col * 4.1, 1.5 + row * 2.45
    box(s, x, y, 3.85, 2.2)
    badge(s, ic, x + 0.25, y + 0.25, 0.7)
    text(s, x + 1.1, y + 0.2, 2.6, 0.8, n, 34, True, VIOLET, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.25, y + 1.1, 3.4, 1.0, label, 14, False, INK)
text(s, 0.6, 6.45, 12.1, 0.5, 'All of it is held on the department\'s own server, in a database the AI can read but never change.',
     16, True, GREEN)
notes(s, 'These are the row counts loaded so far. The data bank is a copy; the source systems are untouched. '
         'We can add more sources without changing how officers ask questions.')

# 10 --------------------------------------------------------------- models
s = new_slide('The AI models')
text(s, 0.6, 1.25, 12.1, 0.7, 'Two open-source models run on the office server. Each has one job. Nothing is sent to an outside service.',
     19, False, INK)
for i, (ic, h, sub, b) in enumerate([
    ('chat', 'Llama 3.1  (8 billion)', 'The conversationalist',
     'Talks with the officer, decides when to look something up, and writes the plain-language summary.'),
    ('cpu', 'Qwen 2.5 Coder  (7 billion)', 'The specialist',
     'Writes the database search and the chart code. It sees the data layout, not the officer\'s chat.'),
]):
    x = 0.6 + i * 6.15
    box(s, x, 2.2, 5.9, 3.0)
    badge(s, ic, x + 0.3, 2.45)
    text(s, x + 1.3, 2.4, 4.4, 0.55, h, 22, True, VIOLET)
    text(s, x + 1.3, 2.95, 4.4, 0.4, sub, 15, False, DARK_GOLD)
    text(s, x + 0.3, 3.65, 5.3, 1.5, b, 17, False, INK)
box(s, 0.6, 5.5, 12.1, 1.3, fill=PASTEL_YELLOW, line=GOLD)
text(s, 0.85, 5.55, 11.6, 1.2, ['A conversational model and a code-writing model each do their own job better, so we use two.',
     'Both run locally: the department\'s questions and figures never leave the building.'], 17, True, BLUE,
     anchor=MSO_ANCHOR.MIDDLE, spacing=4)
notes(s, 'Both models are open weights, run through Ollama on the office server. Neither is a DeepSeek model. '
         'The server has no graphics card today, so answers take one to three minutes.')

# 11 --------------------------------------------------------------- safety
s = new_slide('Safety and control')
layers = [
    ('lock', 'Sign-in', 'Email one-time code. Each person has a role: Admin or Analyst.'),
    ('eye', 'Read-only data', 'The AI connects with a database account that can read but cannot change anything.'),
    ('search', 'Checked queries', 'Every query is inspected first. Only a single read request is allowed.'),
    ('shield', 'Locked box for charts', 'Chart code runs in an isolated space: no network, limited time and memory.'),
    ('report', 'Full record', 'Every question, query and action is logged for audit.'),
]
for i, (ic, h, b) in enumerate(layers):
    y = 1.4 + i * 1.08
    box(s, 0.6, y, 12.1, 0.95)
    badge(s, ic, 0.8, y + 0.1, 0.75)
    text(s, 1.75, y + 0.05, 3.3, 0.85, h, 21, True, VIOLET, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 5.0, y + 0.05, 7.6, 0.85, b, 16, False, INK, anchor=MSO_ANCHOR.MIDDLE)
notes(s, 'Each layer works on its own: if one failed, the next would still stop a harmful action. '
         'Be ready for the question "can it change our data?" The answer is no: the database itself refuses any write from this account.')

# 11b -------------------------------------------------------------- admin
s = new_slide('What administrators see')
shot(s, 'admin-kb.png', 0.6, 1.5, 6.0, 4.1, link='slide-11a-admin-knowledge-base.png')
shot(s, 'admin-health.png', 6.75, 1.5, 6.0, 4.1, bottom_px=1200, link='slide-11b-admin-system-health.png')
text(s, 0.6, 5.85, 6.0, 1.0, 'Knowledge base: upload a rule note, see every document the chat can quote, and withdraw one.',
     16, False, INK)
text(s, 6.75, 5.85, 6.0, 1.0, 'System health: whether the AI service is up, the queue, the server load, and how much each model was used.',
     16, False, INK)
notes(s, 'Click either screenshot to open it full size. Administrators also have screens for users, the activity log, data loading runs and a data dictionary '
         'where a plain-language note can be attached to any table or column to guide the AI.')

# 12 --------------------------------------------------------------- how we built it
s = new_slide('How we built it, and how we tested it')
steps = [
    ('database', 'Data bank', 'Department data loaded and cleaned. Rows that fail checks are set aside, not guessed.'),
    ('brain', 'Question engine', 'Question to query to answer, with a retry when the first attempt fails.'),
    ('books', 'Knowledge library', 'Published rules split into searchable sections.'),
    ('chat', 'Chat and Ask screens', 'Web screens for officers and for administrators.'),
    ('check', 'Real-question testing', 'Each demo question was run live and the answer checked against the source.'),
]
for i, (ic, h, b) in enumerate(steps):
    x = 0.45 + i * 2.5
    box(s, x, 1.6, 2.35, 3.9)
    badge(s, ic, x + 0.8, 1.85, 0.75)
    text(s, x + 0.08, 2.75, 2.2, 0.7, h, 17, True, VIOLET, PP_ALIGN.CENTER)
    text(s, x + 0.12, 3.45, 2.1, 2.0, b, 14, False, INK, PP_ALIGN.CENTER)
text(s, 0.6, 5.8, 12.1, 1.0, ['The automated tests cover the safety checks, the data loaders and the chat flow.',
     'Live testing on real questions found problems the tests could not. Each one was fixed and recorded.'],
     17, False, INK, spacing=4)
notes(s, 'We followed a written plan with milestones, and every live failure found in testing is documented. '
         'Honest testing is part of the case for trusting the results.')

# 13 --------------------------------------------------------------- limits
s = new_slide('What we learned, and the limits today')
box(s, 0.6, 1.4, 5.95, 5.4)
text(s, 0.85, 1.5, 5.5, 0.5, 'What we learned', 22, True, VIOLET)
bullets(s, 0.85, 2.15, 5.5, [
    'A language model can give a confident wrong answer. We added checks so an empty result is reported as empty.',
    'District revenue after 2018 in the Rajkosh and Koshwani portal data is booked at the central treasury in Lucknow.',
    'We cross-checked against shop-level revenue and now point the system to the correct source.',
    'Money conversions are done in code. A model got one crore figure wrong by ten times.',
], 15, 10)
box(s, 6.75, 1.4, 5.95, 5.4)
text(s, 7.0, 1.5, 5.5, 0.5, 'Limits today', 22, True, DARK_GOLD)
bullets(s, 7.0, 2.15, 5.5, [
    'The server has no graphics card, so an answer takes one to three minutes.',
    'Shop-level monthly detail is loaded for Lucknow only (August 2026).',
    'Shop-level Bhang data has no source yet.',
    'Answers should be treated as a fast first reading, to be checked against the source for formal use.',
], 15, 10)
notes(s, 'We are open about limits deliberately. The audience will ask what can go wrong; this slide answers first.')

# 14 --------------------------------------------------------------- roadmap
s = new_slide('What comes next')
road = [
    ('server', 'High-performance compute', 'A high-performance computing (HPC) node with high-end GPU servers runs larger, more capable models and shortens response times.'),
    ('database', 'More data', 'Monthly feeds for every district, and the missing sources such as Bhang shops.'),
    ('doc', 'Saved analyses and reports', 'Re-run a favourite question each month and export a report with the data date on it.'),
    ('users', 'Wider access', 'Roles for district and division officers, with their own question history.'),
]
for i, (ic, h, b) in enumerate(road):
    col, row = i % 2, i // 2
    x, y = 0.6 + col * 6.15, 1.5 + row * 2.6
    box(s, x, y, 5.95, 2.35)
    badge(s, ic, x + 0.3, y + 0.3, 0.8)
    text(s, x + 1.35, y + 0.3, 4.4, 0.6, h, 22, True, VIOLET, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.3, y + 1.2, 5.4, 1.1, b, 16, False, INK)
notes(s, 'Roadmap items come from the project plan. Saved analyses and offline reading are planned, not built.')

# 15 --------------------------------------------------------------- decision
s = new_slide('The decision we are asking for')
box(s, 0.6, 1.5, 12.1, 2.2, fill=TINT)
badge(s, 'bulb', 0.9, 1.9, 0.9)
text(s, 2.1, 1.7, 10.4, 1.9, ['This proof of concept shows that officers can get sourced answers from the '
     'department\'s own data in minutes, on the department\'s own server.',
     'We ask the respected authorities for a decision on the next step.'], 20, True, INK, spacing=8)
text(s, 0.6, 4.1, 12.1, 0.5, 'Proposed next steps', 22, True, VIOLET)
bullets(s, 0.6, 4.7, 12.1, [
    '1.  A pilot with a small group of district and division officers.',
    '2.  A high-performance GPU compute node.',
    '3.  Monthly data feeds from the source systems and involved stakeholders.',
], 18, 8)
notes(s, 'DECISION REQUEST: to be written after the review with the project lead. Replace the next steps '
         'above with the specific approval being sought.')

prs.save(OUT)
print('saved', OUT, 'slides:', len(prs.slides._sldIdLst))
