"""Deterministic ingredient search, no AI calls and no external libraries."""
import re

PANTRY = {"вода", "соль", "перец черный"}


def plain(s):
    return re.sub(r"\s+", " ", str(s).lower().replace("ё", "е").replace("‐", "-").strip())


def ingredient_key(value):
    s = plain(value)
    # Strongly distinctive ingredients first to avoid false equivalences.
    special = [
        (r"сахарн\w* пудр", 'сахарная пудра'),
        (r"ванильн\w* сахар", 'ванильный сахар'),
        (r"сух\w* дрожж\w*|дрожж\w* сух\w*", 'сухие дрожжи'),
        (r"свеж\w* дрожж\w*|дрожж\w* свеж\w*|прессованн\w* дрожж\w*", 'свежие дрожжи'),
        (r"дрожж", 'дрожжи'),
        (r"рисов\w* мук", 'рисовая мука'),
        (r"миндальн\w* мук", 'миндальная мука'),
        (r"кукурузн\w* мук", 'кукурузная мука'),
        (r"гречнев\w* мук", 'гречневая мука'),
        (r"картофельн\w* крахмал", 'картофельный крахмал'),
        (r"кукурузн\w* крахмал", 'кукурузный крахмал'),
        (r"томатн\w* паст|паста из томат", 'томатная паста'),
        (r"соус томатн|томатн\w* пассат|пассат", 'томатный соус'),
        (r"сливочн\w* масл|масл\w* сливочн", 'сливочное масло'),
        (r"оливков\w* масл|растительн\w* масл|подсолнечн\w* масл|рафинированн\w* масл", 'растительное масло'),
        (r"кокосов\w* молок", 'кокосовое молоко'),
        (r"сгущенн\w* молок|сгущенк", 'сгущёнка'),
        (r"сливочн\w* сыр|творожн\w* сыр|сыр\w* (?:сливочн\w*|творожн\w*)|крем.сыр|маскарпоне|филадельф", 'сливочный сыр'),
        (r"соев\w* соус", 'соевый соус'),
        (r"рыбн\w* соус", 'рыбный соус'),
        (r"кунжутн\w* соус", 'кунжутный соус'),
        (r"сырн\w* соус", 'сырный соус'),
        (r"зелен\w* лук|лук зелен", 'зелёный лук'),
        (r"лук порей", 'лук-порей'),
        (r"лук репчат|луковиц|\bлук\b", 'лук'),
        (r"зелен\w* горош|консервирован\w* горош|\bгорошек\b", 'горошек'),
        (r"курин\w* бульон", 'куриный бульон'),
        (r"овощн\w* бульон", 'овощной бульон'),
        (r"говяж\w* бульон", 'говяжий бульон'),
        (r"говяж\w* фарш", 'говяжий фарш'),
        (r"курин\w* фарш", 'куриный фарш'),
        (r"свин\w* фарш", 'свиной фарш'),
        (r"фарш", 'фарш'),
        (r"молот\w* перец|черн\w* перец|перец черн", 'перец черный'),
        (r"болгарск\w* перец|сладк\w* перец", 'болгарский перец'),
        (r"чили|остр\w* перец", 'перец чили'),
        (r"кунжутн\w* паст", 'кунжутная паста'),
        (r"паста анко|\bанко\b", 'паста анко'),
        (r"круглозерн\w* рис|кругл\w* рис|японск\w* рис|рис\w* для суши", 'рис'),
        (r"лапш\w* соба|\bсоба\b", 'лапша соба'),
        (r"\bудон\b", 'удон'),
        (r"лапш\w* быстр\w* приготовлен|cup noodle|доширак|роллтон", 'лапша быстрого приготовления'),
        (r"рыб\w* бел\w*|бел\w* рыб", 'белая рыба'),
        (r"лосос|семг", 'лосось'),
        (r"мед\b", 'мёд'),
        (r"персик|персич", 'персик'),
        (r"сливк", 'сливки'),
        (r"сметан", 'сметана'),
        (r"томат|помидор", 'помидор'),
        (r"картоф|картош", 'картофель'),
        (r"сахар", 'сахар'),
        (r"крахмал", 'крахмал'),
        (r"мук", 'мука'),
        (r"яйц|яичн|желток|белок яйца", 'яйцо'),
        (r"молок", 'молоко'),
        (r"куриц|курин\w* филе|курин\w* бедр|курин\w* груд", 'курица'),
        (r"говядин|говяж", 'говядина'),
        (r"свин|свинин", 'свинина'),
        (r"морков", 'морковь'),
        (r"чеснок", 'чеснок'),
        (r"гриб|шампиньон|шиитаке|вешенк", 'грибы'),
        (r"рис", 'рис'),
        (r"капуст", 'капуста'),
        (r"бекон", 'бекон'),
        (r"ветчин", 'ветчина'),
        (r"сосис", 'сосиски'),
        (r"колбас", 'колбаса'),
        (r"сыр|моцарелл|чеддер|пармезан|гауд", 'сыр'),
        (r"хлеб|тост", 'хлеб'),
        (r"макарон|спагетт", 'спагетти'),
        (r"огур", 'огурец'),
        (r"уксус", 'уксус'),
        (r"ванил", 'ваниль'),
        (r"соль|соли|солен|соле", 'соль'),
        (r"вода|воды|водой|кипяток", 'вода'),
        (r"разрыхлител", 'разрыхлитель'),
        (r"сод\b|сода\b", 'сода'),
        (r"нори", 'нори'),
        (r"салат", 'салат'),
        (r"перец", 'перец'),
    ]
    for pattern, key in special:
        if re.search(pattern, s):
            return key
    # Small inflection-tolerant fallback for recipes using rare Japanese ingredients.
    s = re.sub(r"\([^)]*\)", " ", s)
    words = re.findall(r"[a-zа-я]+", s)
    remove = {'для', 'или', 'и', 'по', 'вкусу', 'шт', 'свежий', 'свежая', 'свежие', 'средний', 'большой', 'маленький', 'немного', 'листья', 'сушеный', 'крупный', 'мелкий', 'тертый', 'твердый', 'измельченный'}
    words = [w for w in words if w not in remove]
    if not words:
        return s[:50]
    def stem(w):
        for suffix in ('иями','ями','ами','ого','ему','ыми','ими','ающего','ная','ное','ные','ная','овать','ого','ный','ная','овые','овая','ый','ий','ая','яя','ое','ей','ой','ом','ем','ов','ев','ам','ям','ах','ях','а','я','и','ы','у','ю','е','о'):
            if len(w) > len(suffix)+3 and w.endswith(suffix):
                return w[:-len(suffix)]
        return w
    return ' '.join(stem(w) for w in words[:3])


# Recognize common multi-word products before splitting a space-separated list.
# This avoids treating «сливочное масло» as two independent products while
# still accepting «молоко мука яйца» without punctuation.
COMPOUND_PRODUCTS = [re.compile(pattern) for pattern in (
    r"(?:сливочн\w*|растительн\w*|оливков\w*|подсолнечн\w*|кокосов\w*|кунжутн\w*|топлен\w*) масл\w*",
    r"масл\w* (?:сливочн\w*|растительн\w*|оливков\w*|подсолнечн\w*)",
    r"(?:рисов\w*|миндальн\w*|кукурузн\w*|гречнев\w*|пшеничн\w*) мук\w*",
    r"(?:картофельн\w*|кукурузн\w*) крахмал\w*",
    r"(?:соев\w*|рыбн\w*|томатн\w*|кунжутн\w*|сырн\w*|устричн\w*|остр\w*) соус\w*",
    r"соус\w* (?:соев\w*|томатн\w*)",
    r"(?:томатн\w*|кунжутн\w*|арахисов\w*) паст\w*",
    r"паст\w* (?:анко|из томатов)",
    r"сахарн\w* пудр\w*",
    r"ванильн\w* сахар\w*",
    r"(?:сгущенн\w*|кокосов\w*|овсян\w*|миндальн\w*|соев\w*) молок\w*",
    r"(?:творожн\w*|сливочн\w*|плавлен\w*|тверд\w*) сыр\w*",
    r"сыр\w* (?:творожн\w*|сливочн\w*|тверд\w*)",
    r"(?:репчат\w*|зелен\w*|красн\w*|порей) лук\w*",
    r"лук\w* (?:репчат\w*|зелен\w*|порей)",
    r"(?:курин\w*|индейк\w*|говяж\w*|свин\w*|рыбн\w*) фарш\w*",
    r"фарш\w* (?:курин\w*|говяж\w*|свин\w*)",
    r"(?:курин\w*|индейк\w*) (?:филе|грудк\w*|бедр\w*)",
    r"(?:болгарск\w*|сладк\w*|остр\w*|черн\w*|молот\w*) перец\w*",
    r"перец\w* (?:черн\w*|болгарск\w*|молот\w*)",
    r"(?:яичн\w*|курин\w*) (?:желток|белок|яйц\w*)",
    r"яйц\w* курин\w*",
    r"(?:сух\w*|свеж\w*) дрожж\w*",
    r"(?:зелен\w*|замороженн\w*) (?:горош\w*|овощ\w*)",
    r"(?:японск\w*|круглозерн\w*) рис\w*",
    r"рис\w* для суши",
    r"крем сыр",
)]


def parse_products(text):
    raw = plain(text)
    # Accept natural Russian lists, with commas, conjunctions, or just spaces.
    raw = re.sub(r"^(?:у меня есть|у меня|дома есть|в холодильнике есть|в наличии|есть|дома|продукты:?)\s+", "", raw)
    chunks = re.split(r"[,;\n]+|\s+(?:и|плюс|а также)\s+", raw)
    result = []
    ignored = {"г", "гр", "кг", "мл", "л", "шт", "штук", "продукты", "имеются"}
    for chunk in chunks:
        # A lone entry like «сливочное масло» remains one product. If several
        # ingredients are written without commas, match known phrases greedily.
        words = re.findall(r"[a-zа-я0-9]+(?:-[a-zа-я0-9]+)?", chunk)
        i = 0
        while i < len(words):
            if words[i].isdigit() or words[i] in ignored:
                i += 1
                continue
            phrase = None
            consumed = 1
            for count in (3, 2):
                if i + count > len(words):
                    continue
                candidate = " ".join(words[i:i + count])
                if any(pattern.fullmatch(candidate) for pattern in COMPOUND_PRODUCTS):
                    phrase, consumed = candidate, count
                    break
            key = ingredient_key(phrase or words[i])
            if key and key not in result:
                result.append(key)
            i += consumed
    return result


def keys_for_ingredient(name):
    s = plain(name)
    # Alternatives explicitly present in the original recipe.
    options = [s] + [x for x in re.split(r"\s+или\s+|\s*/\s*", s) if x]
    return {ingredient_key(x) for x in options}


def recipe_comparison(recipe, available, pantry=PANTRY):
    owned = set(available)
    found = []
    missing = []
    seen = set()
    for item in recipe.get('ingredients', []):
        keys = keys_for_ingredient(item['name'])
        if any(key in seen for key in keys):
            continue
        seen |= keys
        if owned & keys:
            found.append(item)
        elif set(pantry) & keys:
            # Common pantry staples are neither "owned" matches nor shopping needs.
            pass
        else:
            missing.append(item)
    return found, missing


def find_recipes(recipes, entered, limit=100):
    available = parse_products(entered)
    if not available:
        return []
    matches = []
    for recipe in recipes:
        if recipe.get('needs_review'):
            continue
        found, missing = recipe_comparison(recipe, available)
        if found:
            matches.append({'recipe': recipe, 'have': found, 'need': missing,
                            'score': (len(missing), -len(found), recipe['title'].lower())})
    return sorted(matches, key=lambda x: x['score'])[:limit]


def shopping_item(item):
    name = item['name']
    # The attached post is the authoritative source for amounts.
    amount = item.get('quantity', '').strip(' ;,')
    return f'{name} — {amount}' if amount else name
