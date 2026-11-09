"""Otaku Kitchen Bot v2: text cards, favorites, surprise and persistent filters.

Runtime: Python 3.11+, standard library; Neon support lives in db_store.py.
A Telegram webhook receives updates from webhook.py (on Render).
"""
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

import db_store
from catalog import parse_post
from search_engine import find_recipes, ingredient_key, keys_for_ingredient, parse_products, plain, recipe_comparison, shopping_item

TOKEN = os.environ.get('BOT_TOKEN', '').strip()
if not TOKEN:
    sys.exit('BOT_TOKEN not set. Set it in Render Environment or your local shell.')
API = f'https://api.telegram.org/bot{TOKEN}/'
recipes = db_store.load_recipes()

CATEGORY_LABELS = {
    'завтрак': '🥞 Завтраки', 'обед': '🍜 Обеды', 'ужин': '🍱 Ужины',
    'десерт': '🍰 Десерты', 'напитки': '🥤 Напитки',
}
DIFF_NAMES = {'легко': '🟢 Легко', 'средне': '🟡 Средне', 'сложно': '🔴 Сложно'}
DIFF_CODES = {'any': None, 'easy': 'легко', 'medium': 'средне', 'hard': 'сложно'}
CHANNEL_URL = 'https://t.me/otakukitchen'


def esc(value):
    return html.escape(str(value), quote=False)


def tg(method, **params):
    data = json.dumps(params, ensure_ascii=False).encode('utf8')
    req = urllib.request.Request(API + method, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=48) as response:
            output = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Telegram API {method} failed: HTTP {exc.code}') from None
    if not output.get('ok'):
        raise RuntimeError(f'Telegram API {method} failed: {output.get("description", "unknown")}')
    return output.get('result')


def button(text, callback=None, url=None):
    if url:
        return {'text': text, 'url': url}
    return {'text': text, 'callback_data': callback}


def send(chat, text, keyboard=None, *, edit_id=None):
    params = {
        'chat_id': chat, 'text': text, 'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }
    if keyboard is not None:
        params['reply_markup'] = {'inline_keyboard': keyboard}
    if edit_id is not None:
        params['message_id'] = edit_id
        try:
            return tg('editMessageText', **params)
        except RuntimeError as exc:
            # Telegram returns a non-critical error when the output is unchanged.
            if 'message is not modified' in str(exc):
                return None
            # The old message can be too old or invalid: send a new one.
            return tg('sendMessage', **{k: v for k, v in params.items() if k != 'message_id'})
    return tg('sendMessage', **params)


def read_user(uid):
    u = db_store.read_user(uid)
    u.setdefault('difficulty', None)
    u.setdefault('excluded', [])
    u.setdefault('excluded_labels', [])
    u.setdefault('favorites', [])
    u.setdefault('session', {})
    return u


def save_user(uid, user):
    db_store.save_user(uid, user)


def clean_recipes():
    return [r for r in recipes if not r.get('needs_review')]


def parse_exclusions(s):
    """Normalize exclusions as product names, including multiword names."""
    bits = re.split(r'[,;\n]+', s)
    if len(bits) == 1:
        return parse_products(s)
    values = []
    for part in bits:
        p = plain(part).strip(' .:-')
        if not p:
            continue
        key = ingredient_key(p)
        if key and key not in values:
            values.append(key)
    return values[:30]


def violates_exclusions(recipe, excludes):
    """Conservative preference filter, not an allergen safety checker."""
    if not excludes:
        return False
    for item in recipe.get('ingredients', []):
        name = plain(item['name'])
        keys = keys_for_ingredient(item['name'])
        for term in excludes:
            if term in keys:
                return True
            # A generic exclusion also filters derived forms (e.g. corn starch).
            if term == 'кукуруз' and 'кукуруз' in name:
                return True
            if term == 'мука' and re.search(r'\bмук\w*\b', name):
                return True
            if term == 'молоко' and re.search(r'\bмолок\w*\b', name):
                return True
            if term == 'яйцо' and re.search(r'яйц|яичн|желтк|белок', name):
                return True
            if term == 'сахар' and re.search(r'сахар', name):
                return True
            if term == 'сыр' and re.search(r'сыр|моцарелл|чеддер|пармезан', name):
                return True
            if term == 'орех' and re.search(r'орех|миндал|фундук|грецк', name):
                return True
            if term == 'кинз' and re.search(r'кинз|кориандр\s*(?:свеж|зелень)', name):
                return True
    return False


def matches_prefs(recipe, user):
    return (not recipe.get('needs_review') and
            (not user.get('difficulty') or recipe.get('difficulty') == user['difficulty']) and
            not violates_exclusions(recipe, user.get('excluded', [])))


def menu(chat, uid, *, edit_id=None):
    user = read_user(uid)
    counts = Counter(c for r in recipes if matches_prefs(r, user) for c in r['categories'])
    kb = [
        [button(f'🥞 Завтраки · {counts["завтрак"]}', 'category:завтрак'), button(f'🍜 Обеды · {counts["обед"]}', 'category:обед')],
        [button(f'🍱 Ужины · {counts["ужин"]}', 'category:ужин'), button(f'🍰 Десерты · {counts["десерт"]}', 'category:десерт')],
        [button(f'🥤 Напитки · {counts["напитки"]}', 'category:напитки')],
        [button('🔎 Поиск по продуктам', 'search'), button('🎬 Поиск по аниме', 'anime')],
        [button('🎲 Случайный рецепт', 'random'), button('❤️ Избранное', 'favorites')],
        [button('⚙️ Мои фильтры', 'filters')],
        [button('📢 Мой Telegram-канал', url=CHANNEL_URL)],
    ]
    diff = DIFF_NAMES.get(user['difficulty'], 'Любая')
    notes = f'\n\n⚙️ Сложность: {esc(diff)} · Исключений: {len(user["excluded"])}' if user['difficulty'] or user['excluded'] else ''
    text = ('🍡 <b>Добро пожаловать в Otaku Kitchen!</b>\n\n'
            'Здесь ты найдёшь блюда из любимых аниме! 🥢\n'
            'Выбирай категорию, ищи по продуктам или доверь выбор мне.\n\n'
            '📖 Все полные рецепты открываются в <b>моём Telegram-канале</b>.') + notes
    return send(chat, text, kb, edit_id=edit_id)


def start_session(uid, *, source, category='', query=''):
    user = read_user(uid)
    user['session'] = {'source': source, 'category': category, 'query': query}
    save_user(uid, user)
    return user


def title_for(recipe):
    return (recipe.get('title') or 'Без названия').strip()


def anime_name(recipe):
    title = title_for(recipe)
    m = re.search(r'[«“"]([^»”"]+)[»”"]', title)
    if m:
        return m.group(1)
    return None


def filtered_candidates(uid, user=None):
    user = user or read_user(uid)
    state = user.get('session', {})
    source = state.get('source')
    if source == 'category':
        category = state.get('category')
        chosen = [r for r in recipes if category in r['categories'] and matches_prefs(r, user)]
        chosen.sort(key=lambda r: r['id'], reverse=True)
        return [{'recipe': r, 'have': None, 'need': None} for r in chosen]
    if source == 'search':
        # No arbitrary 100-result cutoff; allow full pagination.
        return [hit for hit in find_recipes(recipes, state.get('query', ''), limit=len(recipes)+1)
                if matches_prefs(hit['recipe'], user)]
    if source == 'anime':
        needle = plain(state.get('query', '')).replace(' ', '').replace('-', '')
        chosen = [r for r in recipes if needle and matches_prefs(r, user) and
                  (needle in plain(title_for(r)).replace(' ', '').replace('-', '') or
                   any(needle in plain(t).replace('-', '') for t in r.get('anime_tags', [])))]
        chosen.sort(key=lambda r: r['id'], reverse=True)
        return [{'recipe': r, 'have': None, 'need': None} for r in chosen]
    if source == 'favorites':
        ids = {int(x) for x in user.get('favorites', [])}
        chosen = [r for r in clean_recipes() if int(r['id']) in ids]
        chosen.sort(key=lambda r: r['id'], reverse=True)
        return [{'recipe': r, 'have': None, 'need': None} for r in chosen]
    if source == 'random':
        eligible = [r for r in recipes if matches_prefs(r, user)]
        return [{'recipe': r, 'have': None, 'need': None} for r in eligible]
    return []


def source_name(state):
    source = state.get('source', '')
    if source == 'category':
        return CATEGORY_LABELS.get(state.get('category'), '🍱 Категория')
    if source == 'search':
        return '🔎 Поиск по продуктам'
    if source == 'anime':
        return '🎬 Поиск по аниме'
    if source == 'favorites':
        return '❤️ Избранное'
    if source == 'random':
        return '🎲 Случайный рецепт'
    return '🍡 Otaku Kitchen'


def card_text(item, state, position, total):
    recipe = item['recipe']
    cat = ' · '.join(CATEGORY_LABELS.get(c, c).split(' ', 1)[-1] for c in recipe.get('categories', []))
    difficulty = DIFF_NAMES.get(recipe.get('difficulty'), 'Не указано')
    anime = anime_name(recipe)
    txt = [f'<b>🍡 {esc(source_name(state))}</b>  ·  {position}/{total}', '',
           f'🍱 <b>{esc(title_for(recipe))}</b>']
    if anime:
        txt.append(f'🎬 <i>{esc(anime)}</i>')
    txt += [f'🏷 {esc(cat)}   |   {esc(difficulty)}', '']
    if item.get('have') is not None:
        have, need = item['have'], item['need']
        txt.append(f'✅ <b>Есть ({len(have)}):</b>')
        txt.append(esc(', '.join(p['name'] for p in have) if have else '—'))
        txt.append('')
        if need:
            txt.append(f'🛒 <b>Докупить ({len(need)}):</b>')
            txt.extend('• ' + esc(shopping_item(p)) for p in need[:12])
            if len(need) > 12:
                txt.append(f'…и ещё {len(need)-12} (смотри оригинал)')
        else:
            txt.append('🎉 По указанному составу ничего докупать не нужно!')
    else:
        ingredients = recipe.get('ingredients', [])
        if ingredients:
            txt.append(f'🥢 <b>Ингредиенты ({len(ingredients)}):</b>')
            txt.append(esc(', '.join(x['name'] for x in ingredients[:9])) + ('…' if len(ingredients)>9 else ''))
    txt += ['', '📖 <i>Полный рецепт — в моём Telegram-канале.</i>']
    return '\n'.join(txt)[:3900]


def show_card(chat, uid, index=0, *, edit_id=None):
    user = read_user(uid)
    state = user.get('session', {})
    source = state.get('source')
    found = filtered_candidates(uid, user)
    if not found:
        if source == 'favorites':
            msg = '❤️ <b>Избранное пока пустое.</b>\n\nДобавляй блюда через кнопку 🤍 под рецептом.'
        else:
            msg = '😿 Ничего не нашлось с текущими фильтрами. Попробуй снять ограничения или изменить поиск.'
        return send(chat, msg, [[button('⚙️ Изменить фильтры', 'filters'), button('🏠 Меню', 'menu')]], edit_id=edit_id)
    index = max(0, min(int(index), len(found)-1))
    item = found[index]
    recipe = item['recipe']
    is_favorite = int(recipe['id']) in {int(x) for x in user.get('favorites', [])}
    kb = [
        [button('📖 Открыть рецепт в канале', url=recipe['url'])],
        [button('❤️ Убрать из избранного' if is_favorite else '🤍 В избранное', f'fav:{recipe["id"]}:{index}')],
    ]
    if source == 'random':
        kb.append([button('🎲 Ещё один рецепт', 'random')])
    else:
        nav = []
        if index > 0:
            nav.append(button('◀️ Назад', f'page:{index-1}'))
        if index+1 < len(found):
            nav.append(button('Далее ▶️', f'page:{index+1}'))
        if nav:
            kb.append(nav)
    kb.append([button('⚙️ Фильтры', 'filters'), button('🏠 Меню', 'menu')])
    return send(chat, card_text(item, state, index+1, len(found)), kb, edit_id=edit_id)


def begin_search(chat, uid, kind='search'):
    user = read_user(uid)
    user['session'] = {'source': kind, 'mode': 'awaiting_query'}
    save_user(uid, user)
    if kind == 'search':
        text = ('🔎 <b>Что есть у тебя дома?</b>\n\nНапиши продукты через запятую или пробел.\n'
                'Например: <code>яйца, молоко, мука</code>\n\n'
                'Я покажу, что есть и что нужно докупить. Количество продуктов пока не проверяю.')
    else:
        text = '🎬 <b>Поиск по аниме</b>\n\nНапиши название аниме, например: <code>Наруто</code> или <code>ДжоДжо</code>.'
    return send(chat, text, [[button('🏠 Меню', 'menu')]])


def random_card(chat, uid, *, edit_id=None):
    user = start_session(uid, source='random')
    chosen = filtered_candidates(uid, user)
    if not chosen:
        return show_card(chat, uid, edit_id=edit_id)
    previous = user.get('last_random')
    options = [i for i, entry in enumerate(chosen) if entry['recipe']['id'] != previous]
    idx = random.choice(options or list(range(len(chosen))))
    user['last_random'] = chosen[idx]['recipe']['id']
    save_user(uid, user)
    return show_card(chat, uid, index=idx, edit_id=edit_id)


def favorites(chat, uid, *, edit_id=None):
    start_session(uid, source='favorites')
    return show_card(chat, uid, edit_id=edit_id)


def filter_panel(chat, uid, *, edit_id=None):
    user = read_user(uid)
    diff = DIFF_NAMES.get(user.get('difficulty'), '✨ Любая')
    excluded = user.get('excluded', [])
    excluded_labels = user.get('excluded_labels') or excluded
    text = ('⚙️ <b>Мои фильтры</b>\n\n'
            f'🍳 Сложность: <b>{esc(diff)}</b>\n'
            f'🚫 Не хочу видеть: <b>{esc(", ".join(excluded_labels) or "ничего")}</b>\n\n'
            'Настройки применяются к категориям, поиску и случайным блюдам, '
            'а в избранном всегда остаются сохранённые рецепты.\n\n'
            '⚠️ Исключения основаны на тексте рецептов и <b>не подходят для проверки аллергенов</b>.')
    kb = [
        [button(('✅ ' if user.get('difficulty') is None else '')+'✨ Любая', 'diff:any')],
        [button(('✅ ' if user.get('difficulty')=='легко' else '')+'🟢 Легко', 'diff:easy'),
         button(('✅ ' if user.get('difficulty')=='средне' else '')+'🟡 Средне', 'diff:medium'),
         button(('✅ ' if user.get('difficulty')=='сложно' else '')+'🔴 Сложно', 'diff:hard')],
        [button('🚫 Изменить нежелательные продукты', 'edit_exclusions')],
        [button('🧹 Сбросить все фильтры', 'clear_filters')],
        [button('🏠 Меню', 'menu')],
    ]
    return send(chat, text, kb, edit_id=edit_id)


def choose_difficulty(chat, uid, code, edit_id=None):
    user = read_user(uid)
    user['difficulty'] = DIFF_CODES[code]
    save_user(uid, user)
    return filter_panel(chat, uid, edit_id=edit_id)


def toggle_favorite(chat, uid, recipe_id, index, *, edit_id=None):
    user = read_user(uid)
    ids = {int(x) for x in user.get('favorites', [])}
    if recipe_id in ids:
        ids.remove(recipe_id)
    else:
        if not any(r['id'] == recipe_id for r in clean_recipes()):
            return send(chat, 'Этот рецепт пока недоступен. Попробуй выбрать другой.')
        ids.add(recipe_id)
    user['favorites'] = sorted(ids)
    save_user(uid, user)
    return show_card(chat, uid, index=index, edit_id=edit_id)


def handle_channel_post(item, edited=False):
    """Save channel posts before Telegram gets a webhook HTTP 200."""
    global recipes
    if item.get('chat', {}).get('username', '').lower() != 'otakukitchen':
        return
    message_id = item.get('message_id')
    if not isinstance(message_id, int):
        return
    post = {'id': message_id, 'type': 'message', 'text': item.get('text') or item.get('caption') or ''}
    new = parse_post(post)
    if new is None:
        if edited and any(r['id'] == message_id for r in recipes):
            if db_store.database_enabled():
                db_store.delete_recipe(message_id)
            recipes = [r for r in recipes if r['id'] != message_id]
            if not db_store.database_enabled():
                db_store.save_local_recipes(recipes)
            print('Recipe removed after edit:', message_id, flush=True)
        return
    if db_store.database_enabled():
        db_store.upsert_recipe(new)
    recipes = [r for r in recipes if r['id'] != new['id']] + [new]
    if not db_store.database_enabled():
        db_store.save_local_recipes(recipes)
    print('Recipe stored:', new['id'], '(needs review)' if new['needs_review'] else '', flush=True)


def handle_callback(callback):
    chat = callback['message']['chat']['id']
    uid = callback.get('from', {}).get('id', chat)
    edit_id = callback['message'].get('message_id')
    code = callback.get('data', '')
    try:
        tg('answerCallbackQuery', callback_query_id=callback['id'])
    except RuntimeError:
        # After a cold start the callback may be too old to answer, but we
        # can still perform the requested action and send/edit the card.
        pass
    if code == 'menu':
        user = read_user(uid)
        user['session'] = {}
        save_user(uid, user)
        return menu(chat, uid, edit_id=edit_id)
    if code == 'search':
        return begin_search(chat, uid, 'search')
    if code == 'anime':
        return begin_search(chat, uid, 'anime')
    if code.startswith('category:'):
        category = code.split(':', 1)[1]
        if category in CATEGORY_LABELS:
            start_session(uid, source='category', category=category)
            return show_card(chat, uid, edit_id=edit_id)
    if code == 'favorites':
        return favorites(chat, uid, edit_id=edit_id)
    if code == 'random':
        return random_card(chat, uid, edit_id=edit_id)
    if code == 'filters':
        user = read_user(uid)
        if user.get('session', {}).get('mode') == 'awaiting_exclusions':
            user['session'] = {}
            save_user(uid, user)
        return filter_panel(chat, uid, edit_id=edit_id)
    if code == 'edit_exclusions':
        user = read_user(uid)
        user['session'] = {'source': 'filters', 'mode': 'awaiting_exclusions'}
        save_user(uid, user)
        return send(chat, '🚫 <b>Какие продукты исключить?</b>\n\n'
                    'Напиши через запятую, например: <code>кукуруза, кинза, мёд</code>.\n'
                    'Новый список полностью заменит старый.\n'
                    'Для очистки отправь <code>нет</code>.\n\n'
                    '⚠️ Это фильтр предпочтений, не проверка пищевой аллергии.',
                    [[button('⚙️ Назад к фильтрам', 'filters')]])
    if code == 'clear_filters':
        user = read_user(uid)
        user['difficulty'] = None
        user['excluded'] = []
        user['excluded_labels'] = []
        user['session'] = {}
        save_user(uid, user)
        return filter_panel(chat, uid, edit_id=edit_id)
    if code.startswith('diff:') and code[5:] in DIFF_CODES:
        return choose_difficulty(chat, uid, code[5:], edit_id=edit_id)
    if code.startswith('page:'):
        return show_card(chat, uid, int(code[5:]), edit_id=edit_id)
    if code.startswith('fav:'):
        _, rid, index = code.split(':', 2)
        return toggle_favorite(chat, uid, int(rid), int(index), edit_id=edit_id)
    return menu(chat, uid)


def handle_message(message):
    if message.get('chat', {}).get('type') not in (None, 'private'):
        return
    chat = message['chat']['id']
    uid = message.get('from', {}).get('id', chat)
    txt = (message.get('text') or '').strip()
    if not txt:
        return
    if len(txt) > 700:
        return send(chat, 'Список получился слишком длинным. Отправь, пожалуйста, до 700 символов за раз.')
    cmd = txt.split()[0].split('@')[0].lower()
    if cmd in ('/start', '/menu', '/help', '/categories'):
        user = read_user(uid)
        user['session'] = {}
        save_user(uid, user)
        return menu(chat, uid)
    if cmd in ('/search', '/find'):
        return begin_search(chat, uid)
    if cmd == '/anime':
        return begin_search(chat, uid, 'anime')
    if cmd == '/random':
        return random_card(chat, uid)
    if cmd == '/favorites':
        return favorites(chat, uid)
    if cmd == '/filters':
        return filter_panel(chat, uid)
    if cmd == '/delete_my_data':
        db_store.delete_user(uid)
        return send(chat, '✅ Твои фильтры, избранное и история поиска удалены из базы.',
                    [[button('🏠 Меню', 'menu')]])
    user = read_user(uid)
    session = user.get('session', {})
    mode = session.get('mode')
    if mode == 'awaiting_exclusions':
        if txt.lower() in ('нет', 'очистить', '-', 'нету'):
            user['excluded'] = []
            user['excluded_labels'] = []
        else:
            user['excluded'] = parse_exclusions(txt)
            split_text = [plain(x).strip(' .:-') for x in re.split(r'[,;\n]+', txt) if x.strip()]
            user['excluded_labels'] = split_text if len(split_text)>1 or len(user['excluded'])<=1 else user['excluded']
        user['session'] = {}
        save_user(uid, user)
        return filter_panel(chat, uid)
    if mode == 'awaiting_query':
        source = session.get('source')
        if source == 'search' and not parse_products(txt):
            return send(chat, 'Попробуй перечислить названия продуктов, например: яйца, рис, курица.')
        if source in ('search', 'anime'):
            user['session'] = {'source': source, 'query': txt}
            save_user(uid, user)
            return show_card(chat, uid)
    # A bare ingredients message is treated as a fresh search, as in v1.
    if not txt.startswith('/'):
        user['session'] = {'source': 'search', 'query': txt}
        save_user(uid, user)
        return show_card(chat, uid)
    return menu(chat, uid)


def run():
    """Local Windows polling mode; production uses webhook.py."""
    print('Bot started. Loaded recipes:', len(recipes), flush=True)
    offset = None
    while True:
        try:
            batch = tg('getUpdates', offset=offset, timeout=30,
                       allowed_updates=['message', 'callback_query', 'channel_post', 'edited_channel_post'])
            for update in batch:
                offset = update['update_id']+1
                try:
                    if 'channel_post' in update:
                        handle_channel_post(update['channel_post'])
                    elif 'edited_channel_post' in update:
                        handle_channel_post(update['edited_channel_post'], edited=True)
                    elif 'callback_query' in update:
                        handle_callback(update['callback_query'])
                    elif 'message' in update:
                        handle_message(update['message'])
                except Exception as exc:
                    print(f'Update {update["update_id"]} failed: {type(exc).__name__}', flush=True)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f'Temporary polling error: {type(exc).__name__}', flush=True)
            time.sleep(4)


if __name__ == '__main__':
    run()
