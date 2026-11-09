"""Import a Telegram Desktop JSON export into a searchable Otaku Kitchen catalog.

Conservative extraction: anything uncertain is flagged for later review.
No external packages needed.
"""
import json
import re
import sys
from pathlib import Path

CATEGORIES = ("завтрак", "обед", "ужин", "десерт", "напитки")
DIFFICULTIES = ("легко", "средне", "сложно")
ALIASES = {"напиток": "напитки"}
IGNORE_TAGS = set(CATEGORIES) | set(DIFFICULTIES) | set(ALIASES)
RECIPES_WITHOUT_CATEGORY = {87: ["обед"], 139: ["десерт"], 144: ["завтрак"], 150: ["обед"]}  # Manual classification not verified; disabled by default.


def flatten_text(value):
    if isinstance(value, str):
        return value
    return "".join(x if isinstance(x, str) else x.get("text", "") for x in (value or []))


def hashtags(text):
    return [s.lower() for s in re.findall(r"(?<!\w)#([^\s@#]+)(?:@otakukitchen)?", text)]


def decorative(line):
    s = line.strip().replace("\ufe0f", "").replace("\u200d", "")
    if not 7 <= len(s) <= 150 or re.search(r"[\w\d]", s):
        return False
    # Most recipe separators are the same emoji repeated 10+ times.
    return len(set(s)) <= 4 and (max((s.count(c) for c in s), default=0) >= 6)


INSTRUCTION = re.compile(r"^\s*(?:(?:\W){0,4})\s*(?:приготовлени[ея]|пошагов(?:ое|ый)|способ приготовления|инструкци[яи]|как готовить|как приготовить|рецепт\s*:?\s*$|шаг\s*1\b|1[.)]\s*\S+)", re.I)
SECTION = re.compile(r"^(?:для\s+[\w\s()\-,/]+|(?:основа|начинка|соус|тесто|украшение|сборка|подача|крем|глазурь|бульон|маринад|панировка|наполнение|сироп|топпинг|корзинки|для подачи|ингредиенты|порции|приправы))\s*:?[ ]*$", re.I)
NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b|[½¼¾⅓⅔⅛⅜]|\b(?:пол[а-уы]?|щепотк\w*|ст\.?\s*л\.?|ч\.?\s*л\.?)\b", re.I)
QUANTITY_LEAD = re.compile(r"^\s*(?:(?:около|примерно|по|до|от)\s+)?(?:\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?|[½¼¾⅓⅔⅛⅜]|\d+/\d+|половин\w*|щепотк\w*)(?:\s*(?:г|гр|грамм\w*|кг|мл|л|шт\.?|ст\.?\s*л\.?|ч\.?\s*л\.?|стакан\w*|зубчик\w*|кусоч\w*|ломтик\w*|лист\w*|веточ\w*|капл\w*))?\s+", re.I)


def ingredient_section(text):
    lines = text.splitlines()
    deco = [i for i, x in enumerate(lines) if decorative(x)]
    if len(deco) >= 2 and deco[0] < 16:
        return lines[deco[0]+1:deco[1]], "separators"
    if len(deco) == 1 and deco[0] < 16:
        # Some posts only have one separator: rely on instruction boundary.
        lines = lines[deco[0]+1:]
    else:
        ix = next((i for i, x in enumerate(lines[:30]) if re.search(r"\bингредиент\w*\b", x, re.I)), None)
        lines = lines[ix+1:] if ix is not None else lines[1:]
    output = []
    for line in lines:
        x = line.strip()
        if INSTRUCTION.search(x) and len(output) >= 2:
            break
        if decorative(x) and len(output) >= 2:
            break
        if re.match(r"^(?:\s*[-•]?\s*)?(?:1[.)]|①|1️⃣)\s*\S+", x) and len(output) >= 2:
            break
        if re.match(r"^https?://|^#|^❤️\s*поддержать|^😆\s*поддержать", x, re.I):
            break
        # Ingredient portions are short; a long line is a procedure paragraph.
        if len(x) > 190 and len(output) >= 2:
            break
        output.append(line)
    return output, "heading-or-position"


def trim_emoji_prefix(line):
    s = line.strip().lstrip("•*- ").strip()
    m = re.search(r"[A-Za-zА-Яа-яЁё0-9½¼¾⅓⅔⅛⅜]", s)
    return s[m.start():].strip() if m else ""


def clean_ingredient(line):
    s = trim_emoji_prefix(line)
    if not s or len(s)>115 or s.startswith('#') or 'http' in s:
        return None
    if SECTION.fullmatch(s) or re.match(r"^(?:ингридиенты|ингредиенты|порци[яий]|\d+\s*(?:[-–]\s*\d+)?\s+порци[яий]|форма\s*:)", s, re.I) or re.match(r"^(?:на\s+\d+\s+порц|ингредиент|по желанию:|примечани|совет|приготовлени|рецепт|вкусный|сервировк|способ приготовления)", s, re.I):
        return None
    if s.endswith((':', '：')):
        return None
    if not NUMBER.search(s) and not re.match(r"^[^A-Za-zА-Яа-яЁё0-9]*[\u2600-\u27BF\U0001F300-\U0001FAFF]", line):
        # A short plain-text line without an amount is usually a section title.
        return None
    if re.match(r"^(?:из оставш|выключи|залей|наполни|нареж|добав|смеша|приготов|просей|постав|перелож|отжми|выпек|посып|сделай|выжми)", s, re.I):
        return None
    if re.match(r"^(?:\d+[.)]|шаг\s+\d|добавь|смешай|нарежь|разогрей|возьми|положи|перемешай|отвари|обжарь|выпекай|растопи|влей|всыпь|подготовь|свари|сделай|готовим)", s, re.I):
        return None
    # Strip inline notes and links after quantity, but preserve raw for shopping.
    parts = re.split(r"\s+[—–-]\s+", s, maxsplit=1)
    if len(parts) == 2:
        name, amount = parts
    else:
        m = QUANTITY_LEAD.match(s)
        if m:
            name, amount = s[m.end():], s[:m.end()].strip()
        else:
            # E.g. "Соль 7 г" or "Растительное масло 500 мл".
            m2 = re.match(r"^(.*?)\s+(\d+(?:[.,]\d+)?\s*(?:г|гр|мл|кг|л|шт\.?|ст\.?\s*л\.?|ч\.?\s*л\.?))(?:\s*)$", s, re.I)
            name, amount = (m2.group(1), m2.group(2)) if m2 else (s, "")
    name = name.strip("\t ,;.-:—–")
    if not name or name.strip().lower() in {"салат", "тонкацу", "основа", "крем", "начинка"} and not amount:
        return None
    # Don't mistake paragraphs as ingredient names.
    if len(name) > 77 or len(name.split()) > 11:
        return None
    if not amount and not NUMBER.search(s) and len(name.split()) > 12:
        return None
    return {"name": name, "quantity": amount, "original": s}


def parse_post(post, add_untagged=False):
    if post.get('type') != 'message':
        return None
    text = flatten_text(post.get('text')) or post.get('caption', '')
    if not text.strip():
        return None
    tags = hashtags(text)
    categories = list(dict.fromkeys(ALIASES.get(tag, tag) for tag in tags if tag in CATEGORIES or tag in ALIASES))
    if not categories:
        if not add_untagged or int(post['id']) not in RECIPES_WITHOUT_CATEGORY:
            return None
        categories = RECIPES_WITHOUT_CATEGORY[int(post['id'])]
    if post['id'] == 3:  # Pinned channel navigation, not a recipe.
        return None
    chunks, method = ingredient_section(text)
    # A few older posts put two ingredients on the same line with emoji separators.
    chunks = [piece for line in chunks for piece in re.split(r"(?:(?<=мл)|(?<=шт)|(?<=г))\s+(?=[\U0001F300-\U0001FAFF]\s*[А-Яа-яЁё])", line) if piece.strip()]
    items = [clean_ingredient(x) for x in chunks]
    items = [item for item in items if item]
    # Keep first appearance of same product; repeat if distinct ingredients parts needed.
    title = next((x.strip() for x in text.splitlines() if x.strip()), 'Без названия')
    diff = next((x for x in DIFFICULTIES if x in tags), None)
    anime = [x for x in tags if x not in IGNORE_TAGS and x not in {'анименедели', 'рецепт'}]
    return {
        "id": int(post['id']), "title": title, "url": f"https://t.me/otakukitchen/{post['id']}",
        "categories": categories, "difficulty": diff, "anime_tags": anime,
        "ingredients": items, "ingredient_count": len(items), "needs_review": len(items) < 2 or int(post["id"]) == 125,
        "extraction_method": method,
    }


def import_export(path, add_untagged=False):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('type') != 'public_channel' or 'otaku kitchen' not in data.get('name','').lower():
        raise ValueError('This export does not look like the Otaku Kitchen channel')
    posts = [parse_post(p, add_untagged=add_untagged) for p in data['messages']]
    return [p for p in posts if p]


def main():
    export = sys.argv[1] if len(sys.argv)>1 else '../result.json'
    path = Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).with_name('recipes.json')
    posts = import_export(export)
    path.write_text(json.dumps(posts, ensure_ascii=False, indent=2),encoding='utf8')
    from collections import Counter
    print(f'Imported {len(posts)} posts -> {path}')
    print('Categories:',dict(Counter(c for p in posts for c in p['categories'])))
    print('Flagged for review:',sum(p['needs_review'] for p in posts))
    print('Ingredient lines:',sum(p['ingredient_count'] for p in posts))

if __name__ == '__main__': main()
