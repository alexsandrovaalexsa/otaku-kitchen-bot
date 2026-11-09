"""Run the Otaku Kitchen Telegram bot as a secure HTTPS webhook on Render.

Render provides HTTPS and the RENDER_EXTERNAL_URL environment variable.
It uses psycopg to save channel recipes in Neon PostgreSQL.
"""
import hashlib
import hmac
import json
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import bot
import db_store

# Derive a valid Telegram webhook secret; there is no need to copy it into GitHub.
WEBHOOK_SECRET = hashlib.sha256(bot.TOKEN.encode('utf-8')).hexdigest()
WORK_QUEUE = queue.Queue(maxsize=1000)


def worker():
    """Handle user messages and callbacks; keep their flow sequential."""
    while True:
        update = WORK_QUEUE.get()
        try:
            if 'callback_query' in update:
                bot.handle_callback(update['callback_query'])
            elif 'message' in update:
                bot.handle_message(update['message'])
        except Exception as ex:
            print(f'Update failed: {type(ex).__name__}: {str(ex)[:160]}', flush=True)
        finally:
            WORK_QUEUE.task_done()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Safe health-check. No token, database URL, or user messages.
        if urlparse(self.path).path != '/':
            self.send_error(404)
            return
        body = b'Otaku Kitchen Telegram webhook is running.'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        if urlparse(self.path).path != '/':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path != '/telegram':
            self.send_error(404)
            return
        supplied = self.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not hmac.compare_digest(supplied, WEBHOOK_SECRET):
            self.send_error(403)
            return
        try:
            n = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.send_error(400)
            return
        if not 0 < n <= 1024 * 1024:
            self.send_error(413)
            return
        try:
            update = json.loads(self.rfile.read(n).decode('utf-8'))
            if not isinstance(update, dict) or 'update_id' not in update:
                raise ValueError('Invalid Telegram update')
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self.send_error(400)
            return
        # Channel updates must reach the persistent database BEFORE we reply
        # 200. If Neon is temporarily unavailable, return 503 and let Telegram
        # retry. UPSERT and DELETE are idempotent for repeated deliveries.
        try:
            if 'channel_post' in update:
                bot.handle_channel_post(update['channel_post'])
            elif 'edited_channel_post' in update:
                bot.handle_channel_post(update['edited_channel_post'], edited=True)
            else:
                WORK_QUEUE.put_nowait(update)
        except queue.Full:
            self.send_error(503)
            return
        except Exception as ex:
            print(f'Cannot persist channel update: {type(ex).__name__}', flush=True)
            self.send_error(503)
            return
        # User messages remain fast and asynchronous; channel posts are now
        # stored durably before they are acknowledged.
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, fmt, *args):
        # Do not log chat messages or authentication header values.
        print('HTTP', fmt % args, flush=True)


def register_webhook():
    public_url = os.environ.get('RENDER_EXTERNAL_URL', '').strip().rstrip('/')
    if not public_url:
        public_url = os.environ.get('PUBLIC_URL', '').strip().rstrip('/')
    parsed = urlparse(public_url)
    if parsed.scheme != 'https' or not parsed.hostname:
        print('ERROR: Set PUBLIC_URL to the https URL of your web service.', flush=True)
        return
    for i in range(6):
        try:
            bot.tg(
                'setWebhook',
                url=public_url + '/telegram',
                secret_token=WEBHOOK_SECRET,
                allowed_updates=['message', 'callback_query', 'channel_post', 'edited_channel_post'],
                drop_pending_updates=False,
                max_connections=1,
            )
            print('Webhook configured: ' + public_url + '/telegram', flush=True)
            return
        except Exception as ex:
            print(f'Webhook registration attempt {i+1} failed: {type(ex).__name__}: {str(ex)[:120]}', flush=True)
            time.sleep(min(2**i, 30))
    print('Webhook registration failed; check BOT_TOKEN and Render logs.', flush=True)


def main():
    if not db_store.database_enabled():
        raise SystemExit('DATABASE_URL not set. Configure Neon in Render Environment before deploying.')
    port = int(os.environ.get('PORT', '10000'))
    threading.Thread(target=worker, name='telegram-worker', daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    threading.Thread(target=register_webhook, name='register-webhook', daemon=True).start()
    print(f'Listening on port {port}, recipes loaded: {len(bot.recipes)}', flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == '__main__':
    main()
