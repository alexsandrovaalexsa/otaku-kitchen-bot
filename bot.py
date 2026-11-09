"""Otaku Kitchen Telegram bot, Python standard library only.

Run: BOT_TOKEN=<TOKEN> python bot.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from pathlib import Path
from catalog import parse_post
from search_engine import find_recipes, shopping_item, parse_products

TOKEN = os.environ.get('BOT_TOKEN', '').strip()
if not TOKEN:
    sys.exit('BOT_TOKEN not set. Create a bot in @BotFather, then set environment variable BOT_TOKEN.')
API = f'https://api.telegram.org/bot{TOKEN}/'
RECIPES_PATH = Path(__file__).with_name('recipes.json')


def read_recipes():
    return json.loads(RECIPES_PATH.read_text(encoding='utf-8'))


def save_recipes(data):
    temporary = RECIPES_PATH.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(RECIPES_PATH)


recipes = read_recipes()
user_state = {}  # Memory-only conversation state. Recipes persist to file.


def tg(method, **params):
    data = json.dumps(params, ensure_ascii=False).encode('utf8')
    req = urllib.request.Request(API + method, data=data,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=48) as resp:
            res = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Telegram API {method} failed: HTTP {exc.code}') from None
    if not res.get('ok'):
        raise RuntimeError(f'Telegram API error in {method}: {res.get("description", "unknown")}')
    return res.get('result')


def button(name, callback=None, url=None):
    out = {'text': name}
    if url: out['url'] = url
    else: out['callback_data'] = callback
    return out


def send(chat, text, keyboard=None):
    kwargs = {'chat_id': chat, 'text': text, 'disable_web_page_preview': True}
    if keyboard is not None:
        kwargs['reply_markup'] = {'inline_keyboard': keyboard}
    return tg('sendMessage', **kwargs)


def menu(chat):
    categories = Counter(c for r in recipes if not r.get('needs_review') for c in r['categories'])
    rows = [
        [button(f'🥞 Завтраки · {categories["завтрак"]}', 'cat:завтрак:0'),
         button(f'🍜 Обеды · {categories["обед"]}', 'cat:обед:0')],
        [button(f'🍱 Ужины · {categories["ужин"]}', 'cat:ужин:0'),
         button(f'🍰 Десерты · {categories["десерт"]}', 'cat:десерт:0')],
        [button(f'🥤 Напитки · {categories["напитки"]}', 'cat:напитки:0')],
        [button('🔎 Найти по продуктам', 'search'), button('🎬 Поиск по аниме', 'anime')],
        [button('📢 Открыть канал', url='https://t.me/otakukitchen')],
    ]
    send(chat, '🍡 Добро пожаловать в Otaku Kitchen!\n\nВыбери категорию или напиши, какие продукты у тебя есть.\n\n📖 Все полные рецепты открываются в моём Telegram-канале.', rows)


def recipe_title(r):
    return r['title'].strip()[:65]


def category_page(chat, category, page=0):
    chosen = [r for r in recipes if category in r['categories'] and not r.get('needs_review')]
    chosen.sort(key=lambda r:r['id'],reverse=True)
    per_page = 7
    pages = max(1,(len(chosen)+per_page-1)//per_page)
    page = max(0,min(page,pages-1))
    sel = chosen[page*per_page:(page+1)*per_page]
    title = {'завтрак':'🥞 Завтраки','обед':'🍜 Обеды','ужин':'🍱 Ужины','десерт':'🍰 Десерты','напитки':'🥤 Напитки'}.get(category,category)
    lines = [f'{title} — {len(chosen)} рецептов',f'Страница {page+1} из {pages}', '']
    for i,r in enumerate(sel, start=page*per_page+1):
        lines.append(f'{i}. {recipe_title(r)}')
    buttons = [[button('📖 '+recipe_title(r)[:48],url=r['url'])] for r in sel]
    nav = []
    if page>0: nav.append(button('◀️ Назад',f'cat:{category}:{page-1}'))
    if page+1<pages: nav.append(button('Дальше ▶️',f'cat:{category}:{page+1}'))
    if nav: buttons.append(nav)
    buttons.append([button('🏠 Меню','menu')])
    send(chat, '\n'.join(lines), buttons)


def prompt_search(chat):
    user_state[chat]={'mode':'ingredients','query':None}
    send(chat, '🔎 Напиши продукты, которые у тебя есть, через запятую или пробел.\n\nНапример: яйца молоко мука картофель\n\nЯ покажу рецепты и то, что нужно докупить. Количество имеющихся продуктов бот пока не проверяет.')


def prompt_anime(chat):
    user_state[chat]={'mode':'anime','query':None}
    send(chat, '🎬 Напиши название аниме, например: Наруто, ДжоДжо или Genshin Impact.')


def search_page(chat, page=0):
    state = user_state.get(chat, {})
    query = state.get('query')
    if not query:
        return prompt_search(chat)
    hits = find_recipes(recipes, query)
    if not hits:
        return send(chat, 'Пока не нашла рецептов по этим продуктам. Попробуй указать ещё 1–2 продукта через запятую.', [[button('🔎 Новый поиск','search'),button('🏠 Меню','menu')]])
    size=3
    pages=max(1,(len(hits)+size-1)//size)
    page=max(0,min(page,pages-1))
    chosen=hits[page*size:(page+1)*size]
    lines=[f'🔎 В наличии: {", ".join(parse_products(query))}',f'Подходящих рецептов: {len(hits)}. Страница {page+1}/{pages}.','']
    for j,item in enumerate(chosen,start=page*size+1):
        r,have,need=item['recipe'],item['have'],item['need']
        lines.append(f'{j}. {recipe_title(r)}')
        lines.append(f'✅ Есть ({len(have)}): '+', '.join(x['name'] for x in have[:5]) + ('…' if len(have) > 5 else ''))
        if need:
            texts=[shopping_item(x)[:68] for x in need[:6]]
            lines.append(f'🛒 Докупить ({len(need)}): '+ '; '.join(texts))
            if len(need)>6: lines.append(f'   …и ещё {len(need)-6} (смотри рецепт)')
        else:
            lines.append('🎉 Ничего докупать не нужно по указанному составу!')
        lines.append('')
    kb = [[button('📖 '+recipe_title(x['recipe'])[:48], url=x['recipe']['url'])] for x in chosen]
    nav=[]
    if page>0: nav.append(button('◀️ Назад',f'res:{page-1}'))
    if page+1<pages: nav.append(button('Дальше ▶️',f'res:{page+1}'))
    if nav: kb.append(nav)
    kb.append([button('🔎 Новый поиск','search'),button('🏠 Меню','menu')])
    send(chat, '\n'.join(lines)[:4000], kb)


def anime_page(chat, q, page=0):
    needle=q.strip().lower().replace('ё','е').replace(' ','').replace('-','')
    chosen=[r for r in recipes if not r.get('needs_review') and (needle in r['title'].lower().replace('ё','е').replace(' ','').replace('-','') or any(needle in tag.replace('-','') for tag in r['anime_tags']))]
    chosen.sort(key=lambda r:r['id'],reverse=True)
    size=7
    pages=max(1,(len(chosen)+size-1)//size)
    page=max(0,min(page,pages-1))
    sel=chosen[page*size:(page+1)*size]
    if not sel:
        return send(chat, f'Пока не нашла рецептов по запросу «{q}».', [[button('🎬 Другой тайтл','anime'),button('🏠 Меню','menu')]])
    lines=[f'🎬 «{q}»: {len(chosen)} рецептов (страница {page+1}/{pages})','']
    lines += [f'{i+page*size+1}. {recipe_title(r)}' for i,r in enumerate(sel)]
    kb=[[button('📖 '+recipe_title(r)[:48],url=r['url'])] for r in sel]
    nav=[]
    if page>0: nav.append(button('◀️ Назад',f'anp:{page-1}'))
    if page+1<pages: nav.append(button('Дальше ▶️',f'anp:{page+1}'))
    if nav: kb.append(nav)
    kb.append([button('🎬 Другой тайтл','anime'),button('🏠 Меню','menu')])
    send(chat,'\n'.join(lines),kb)


def handle_channel_post(item):
    global recipes
    chat=item.get('chat', {})
    if chat.get('username','').lower() != 'otakukitchen':
        return
    post = {'id':item['message_id'],'type':'message','text':item.get('text') or item.get('caption','')}
    new = parse_post(post)
    if not new:
        return
    idx = next((i for i,r in enumerate(recipes) if r['id']==new['id']), None)
    if idx is None:
        recipes.append(new)
        print('New recipe:',new['id'],flush=True)
    else:
        recipes[idx]=new
        print('Recipe updated:',new['id'],flush=True)
    save_recipes(recipes)


def handle_callback(cb):
    chat=cb['message']['chat']['id']
    tg('answerCallbackQuery',callback_query_id=cb['id'])
    code=cb.get('data','')
    if code=='menu': menu(chat)
    elif code=='search': prompt_search(chat)
    elif code=='anime': prompt_anime(chat)
    elif code.startswith('cat:'):
        _,category,page=code.split(':',2)
        category_page(chat,category,int(page))
    elif code.startswith('res:'):search_page(chat,int(code[4:]))
    elif code.startswith('anp:'):
        state=user_state.get(chat,{})
        anime_page(chat,state.get('query',''),int(code[4:]))


def handle_message(m):
    chat=m['chat']['id']
    txt=(m.get('text') or '').strip()
    if not txt: return
    command=txt.split(' ')[0].split('@')[0].lower()
    if command in ('/start','/menu','/help'):
        user_state.pop(chat,None)
        return menu(chat)
    if command in ('/find','/search'):
        return prompt_search(chat)
    if command=='/anime':
        return prompt_anime(chat)
    if command in ('/categories',):
        return menu(chat)
    state=user_state.get(chat,{})
    if state.get('mode')=='ingredients':
        state['query']=txt
        return search_page(chat)
    if state.get('mode')=='anime':
        state['query']=txt
        return anime_page(chat,txt)
    menu(chat)


def run():
    print('Bot started. Loaded recipes:',len(recipes),flush=True)
    offset=None
    while True:
        try:
            batch=tg('getUpdates',offset=offset,timeout=30,allowed_updates=['message','callback_query','channel_post','edited_channel_post'])
            for update in batch:
                offset=update['update_id']+1
                try:
                    if 'channel_post' in update: handle_channel_post(update['channel_post'])
                    elif 'edited_channel_post' in update: handle_channel_post(update['edited_channel_post'])
                    elif 'callback_query' in update: handle_callback(update['callback_query'])
                    elif 'message' in update: handle_message(update['message'])
                except Exception as exc:
                    # Do not leak bot token (it appears in API URLs).
                    print(f'Update {update["update_id"]} failed: {type(exc).__name__}: {str(exc)[:160]}',flush=True)
        except KeyboardInterrupt:
            print('Stopped.');break
        except Exception as exc:
            print(f'Temporary polling error: {type(exc).__name__}: {str(exc)[:160]}',flush=True)
            time.sleep(4)

if __name__=='__main__': run()
