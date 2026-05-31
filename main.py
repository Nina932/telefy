import asyncio
import os
import sys
import json
import urllib.parse
from telethon import TelegramClient, events
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.sessions import StringSession
from telethon.tl.types import KeyboardButtonWebView, ReplyInlineMarkup, KeyboardButtonRow
from telethon.errors import FloodWaitError, SessionPasswordNeededError
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import database

telegram_login_clients = {}

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
WEBAPP_URL = os.getenv('WEBAPP_URL') or os.getenv('PUBLIC_URL') or 'http://127.0.0.1:8080'
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI') or f"{WEBAPP_URL.rstrip('/')}/callback"
APP_HOST = os.getenv('APP_HOST', '127.0.0.1')
APP_PORT = int(os.getenv('APP_PORT') or os.getenv('PORT', '8080'))

log_buffer = []

def add_log(msg):
    log_buffer.append(msg)
    if len(log_buffer) > 100:
        log_buffer.pop(0)
    print(msg, flush=True)

# Seed initial user into database to support transition seamlessly
default_telegram_id = "default_user"
if not database.get_user(default_telegram_id):
    session_str = ""
    if os.path.exists("spotify_user_session.session"):
        try:
            temp_client = TelegramClient('spotify_user_session', API_ID, API_HASH)
            session_str = "spotify_user_session"
        except Exception:
            pass
    database.save_user(
        telegram_id=default_telegram_id,
        phone=os.getenv('TELEGRAM_PHONE', '+995577222769'),
        session_string=session_str or None,
        first_name=os.getenv('ORIGINAL_FIRST_NAME', 'Nino'),
        last_name=os.getenv('ORIGINAL_LAST_NAME', 'Keshelava'),
        default_bio=os.getenv('DEFAULT_BIO', "Your default telegram bio goes here."),
        is_syncing=1 if session_str else 0,
        tier="premium"
    )
    add_log("Seeded default user into sqlite DB.")

users_playback_state = {}
MIN_PROFILE_UPDATE_SECONDS = int(os.getenv("MIN_PROFILE_UPDATE_SECONDS", "300"))

def get_spotify_client(refresh_token):
    if not refresh_token:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="user-read-currently-playing user-read-playback-state",
            cache_path=".spotify_token_cache"
        )
        return spotipy.Spotify(auth_manager=auth_manager)
        
    auth_manager = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope="user-read-currently-playing user-read-playback-state"
    )
    token_info = auth_manager.refresh_access_token(refresh_token)
    return spotipy.Spotify(auth=token_info['access_token'])

async def handle_client(reader, writer):
    try:
        header_data = bytearray()
        while b'\r\n\r\n' not in header_data:
            chunk = await reader.read(1024)
            if not chunk:
                break
            header_data.extend(chunk)
            if len(header_data) > 8192:
                break
                
        if not header_data:
            writer.close()
            return
            
        parts = header_data.split(b'\r\n\r\n', 1)
        headers_part = parts[0]
        body_part = parts[1] if len(parts) > 1 else b''
        
        request_str = headers_part.decode('utf-8', errors='ignore')
        lines = request_str.split('\r\n')
        request_line = lines[0]
        request_parts = request_line.split(' ')
        if len(request_parts) < 2:
            writer.close()
            return
            
        method, path_raw = request_parts[0], request_parts[1]
        url_parsed = urllib.parse.urlparse(path_raw)
        path = url_parsed.path
        query = urllib.parse.parse_qs(url_parsed.query)
        
        user_id = query.get("user_id", [default_telegram_id])[0]
        
        content_length = 0
        for line in lines[1:]:
            if line.lower().startswith('content-length:'):
                content_length = int(line.split(':', 1)[1].strip())
                break
                
        body_data = bytearray(body_part)
        while len(body_data) < content_length:
            chunk = await reader.read(content_length - len(body_data))
            if not chunk:
                break
            body_data.extend(chunk)
            
        body_str = body_data.decode('utf-8', errors='ignore')
        
        if method == 'OPTIONS':
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                "Access-Control-Allow-Headers: Content-Type\r\n"
                "Content-Length: 0\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write(response.encode('utf-8'))
            await writer.drain()
            writer.close()
            return
            
        response_body = ""
        content_type = "text/plain"
        status_code = "200 OK"
        
        if method == 'GET' and path == '/':
            if os.path.exists("dashboard.html"):
                with open("dashboard.html", "r", encoding="utf-8") as f:
                    response_body = f.read()
                content_type = "text/html; charset=utf-8"
            else:
                response_body = "Dashboard file not found. Ensure dashboard.html exists."
                status_code = "404 Not Found"
        elif method == 'GET' and path == '/api/status':
            usr = database.get_user(user_id)
            if not usr:
                database.save_user(
                    telegram_id=user_id,
                    first_name="New User",
                    last_name="",
                    default_bio="Spotify-Telegram Sync Status"
                )
                usr = database.get_user(user_id)
            
            track = users_playback_state.get(user_id, {
                "playing": False, "title": "", "artist": "", "progress_ms": 0, "duration_ms": 0, "album_art": "", "song_url": ""
            })
            status_data = {
                "is_syncing": bool(usr["is_syncing"]),
                "spotify_connected": bool(usr["spotify_refresh_token"]),
                "telegram_connected": bool(usr["session_string"]),
                "current_track": track,
                "first_name": usr["first_name"],
                "last_name": usr["last_name"],
                "default_bio": usr["default_bio"],
                "tier": usr["tier"],
                "custom_emoji_id": usr["custom_emoji_id"]
            }
            response_body = json.dumps(status_data)
            content_type = "application/json"
        elif method == 'GET' and path == '/api/logs':
            response_body = json.dumps({"logs": log_buffer})
            content_type = "application/json"
        elif method == 'POST' and path == '/api/toggle':
            usr = database.get_user(user_id)
            if usr:
                new_state = 0 if usr["is_syncing"] else 1
                database.save_user(user_id, is_syncing=new_state)
                add_log(f"Sync toggled for {user_id} to: {'ACTIVE' if new_state else 'PAUSED'}")
                response_body = json.dumps({"success": True, "is_syncing": bool(new_state)})
            else:
                status_code = "404 Not Found"
                response_body = json.dumps({"error": "User not found"})
            content_type = "application/json"
        elif method == 'POST' and path == '/api/settings':
            try:
                data = json.loads(body_str)
                database.save_user(
                    telegram_id=user_id,
                    first_name=data.get('first_name'),
                    last_name=data.get('last_name'),
                    default_bio=data.get('default_bio'),
                    custom_emoji_id=data.get('custom_emoji_id')
                )
                add_log(f"Profile config updated in sqlite for user {user_id}")
                response_body = json.dumps({"success": True})
            except Exception as e:
                response_body = json.dumps({"success": False, "error": str(e)})
            content_type = "application/json"
        elif method == 'POST' and path == '/api/upgrade':
            database.save_user(user_id, tier="premium")
            add_log(f"User {user_id} upgraded to premium tier using Stars (Mocked)!")
            response_body = json.dumps({"success": True, "tier": "premium"})
            content_type = "application/json"
        elif method == 'GET' and path == '/api/spotify/auth-url':
            try:
                auth_manager = SpotifyOAuth(
                    client_id=SPOTIFY_CLIENT_ID,
                    client_secret=SPOTIFY_CLIENT_SECRET,
                    redirect_uri=SPOTIFY_REDIRECT_URI,
                    scope="user-read-currently-playing user-read-playback-state",
                    state=user_id
                )
                auth_url = auth_manager.get_authorize_url()
                response_body = json.dumps({"success": True, "auth_url": auth_url})
            except Exception as e:
                response_body = json.dumps({"success": False, "error": str(e)})
            content_type = "application/json"
        elif method == 'GET' and path == '/callback':
            code = query.get("code", [None])[0]
            state = query.get("state", [default_telegram_id])[0]
            if code:
                try:
                    auth_manager = SpotifyOAuth(
                        client_id=SPOTIFY_CLIENT_ID,
                        client_secret=SPOTIFY_CLIENT_SECRET,
                        redirect_uri=SPOTIFY_REDIRECT_URI,
                        scope="user-read-currently-playing user-read-playback-state"
                    )
                    token_info = auth_manager.get_access_token(code, as_dict=True)
                    refresh_token = token_info.get("refresh_token")
                    if refresh_token:
                        database.save_user(telegram_id=state, spotify_refresh_token=refresh_token)
                        add_log(f"Spotify account paired successfully for user {state}")
                        status_code = "302 Found"
                        response_body = "Redirecting..."
                        content_type = "text/plain"
                    else:
                        status_code = "400 Bad Request"
                        response_body = "Failed to obtain Spotify refresh token."
                except Exception as e:
                    status_code = "500 Internal Server Error"
                    response_body = f"OAuth exchange error: {str(e)}"
            else:
                status_code = "400 Bad Request"
                response_body = "Missing Spotify authorization code."
        elif method == 'POST' and path == '/api/spotify/disconnect':
            usr = database.get_user(user_id)
            if usr:
                database.clear_field(user_id, "spotify_refresh_token")
                add_log(f"Spotify disconnected for user {user_id}")
                response_body = json.dumps({"success": True})
            else:
                status_code = "404 Not Found"
                response_body = json.dumps({"error": "User not found"})
            content_type = "application/json"
        elif method == 'POST' and path == '/api/telegram/send-code':
            try:
                data = json.loads(body_str)
                phone = data.get("phone")
                if not phone:
                    response_body = json.dumps({"success": False, "error": "Phone number is required."})
                else:
                    session = StringSession()
                    client = TelegramClient(session, API_ID, API_HASH)
                    await client.connect()
                    sent_code = await client.send_code_request(phone)
                    telegram_login_clients[user_id] = {
                        "client": client,
                        "phone": phone,
                        "phone_code_hash": sent_code.phone_code_hash
                    }
                    add_log(f"Verification code sent to {phone} for user {user_id}")
                    response_body = json.dumps({"success": True})
            except Exception as e:
                response_body = json.dumps({"success": False, "error": str(e)})
            content_type = "application/json"
        elif method == 'POST' and path == '/api/telegram/verify-code':
            try:
                data = json.loads(body_str)
                code = data.get("code")
                entry = telegram_login_clients.get(user_id)
                if not entry:
                    response_body = json.dumps({"success": False, "error": "Pairing session not found or expired. Please request a new code."})
                else:
                    client = entry["client"]
                    phone = entry["phone"]
                    phone_code_hash = entry["phone_code_hash"]
                    try:
                        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                        session_str = client.session.save()
                        me = await client.get_me()
                        first_name = me.first_name or "User"
                        last_name = me.last_name or ""
                        
                        from telethon.tl.functions.users import GetFullUserRequest
                        full_user = await client(GetFullUserRequest(me.id))
                        bio = full_user.full_user.about or ""
                        
                        database.save_user(
                            telegram_id=user_id,
                            session_string=session_str,
                            first_name=first_name,
                            last_name=last_name,
                            default_bio=bio
                        )
                        await client.disconnect()
                        del telegram_login_clients[user_id]
                        add_log(f"Telegram account paired successfully for user {user_id}")
                        response_body = json.dumps({"success": True})
                    except SessionPasswordNeededError:
                        add_log(f"2FA Password required for user {user_id}")
                        response_body = json.dumps({"success": True, "password_required": True})
            except Exception as e:
                response_body = json.dumps({"success": False, "error": str(e)})
            content_type = "application/json"
        elif method == 'POST' and path == '/api/telegram/verify-password':
            try:
                data = json.loads(body_str)
                password = data.get("password")
                entry = telegram_login_clients.get(user_id)
                if not entry:
                    response_body = json.dumps({"success": False, "error": "Pairing session not found."})
                else:
                    client = entry["client"]
                    try:
                        await client.sign_in(password=password)
                        session_str = client.session.save()
                        me = await client.get_me()
                        first_name = me.first_name or "User"
                        last_name = me.last_name or ""
                        
                        from telethon.tl.functions.users import GetFullUserRequest
                        full_user = await client(GetFullUserRequest(me.id))
                        bio = full_user.full_user.about or ""
                        
                        database.save_user(
                            telegram_id=user_id,
                            session_string=session_str,
                            first_name=first_name,
                            last_name=last_name,
                            default_bio=bio
                        )
                        await client.disconnect()
                        del telegram_login_clients[user_id]
                        add_log(f"Telegram account (2FA) paired successfully for user {user_id}")
                        response_body = json.dumps({"success": True})
                    except Exception as e:
                        response_body = json.dumps({"success": False, "error": str(e)})
            except Exception as e:
                response_body = json.dumps({"success": False, "error": str(e)})
            content_type = "application/json"
        elif method == 'POST' and path == '/api/telegram/disconnect':
            usr = database.get_user(user_id)
            if usr:
                database.clear_field(user_id, "session_string")
                add_log(f"Telegram session disconnected for user {user_id}")
                response_body = json.dumps({"success": True})
            else:
                status_code = "404 Not Found"
                response_body = json.dumps({"error": "User not found"})
            content_type = "application/json"
        else:
            response_body = "Not Found"
            status_code = "404 Not Found"
            
        response_headers = [
            f"Content-Type: {content_type}",
            "Access-Control-Allow-Origin: *",
            f"Content-Length: {len(response_body.encode('utf-8'))}",
            "Connection: close"
        ]
        if status_code.startswith("302"):
            response_headers.append(f"Location: /?user_id={state}&spotify_success=true")
            
        response = (
            f"HTTP/1.1 {status_code}\r\n"
            + "\r\n".join(response_headers) + "\r\n\r\n"
            + response_body
        )
        writer.write(response.encode('utf-8'))
        await writer.drain()
    except Exception as e:
        print(f"Error handling request: {e}", flush=True)
    finally:
        writer.close()

async def start_web_server():
    server = await asyncio.start_server(handle_client, APP_HOST, APP_PORT)
    add_log(f"Dashboard server running at http://{APP_HOST}:{APP_PORT}")
    async with server:
        await server.serve_forever()

def compute_profile_fields(usr, track_name, artist_name, track_id, scroll_offset=0):
    if not track_id:
        return usr["last_name"], usr["default_bio"]
    
    prefix = "🎧 "
    full_info = f"{track_name} - {artist_name}"
    available = 64 - len(prefix)
    
    if len(full_info) <= available:
        display_last_name = prefix + full_info
    else:
        padded = full_info + "   "
        start = scroll_offset % len(padded)
        window = "".join(padded[(start + i) % len(padded)] for i in range(available))
        display_last_name = prefix + window
        
    about_text = f"{track_name} - {artist_name}\nhttps://open.spotify.com/track/{track_id}"
    if len(about_text) > 70:
        url_part = f"\nhttps://open.spotify.com/track/{track_id}"
        max_details_len = 70 - len(url_part)
        details = f"{track_name} - {artist_name}"
        if len(details) > max_details_len:
            details = details[:max_details_len-3] + "..."
        about_text = details + url_part
        
    return display_last_name, about_text

async def sync_single_user(usr, client_cache):
    telegram_id = usr["telegram_id"]
    try:
        if not usr["session_string"] or not usr["spotify_refresh_token"]:
            return

        client = client_cache.get(telegram_id)
        if not client:
            if usr["session_string"] == "spotify_user_session":
                client = TelegramClient('spotify_user_session', API_ID, API_HASH)
            else:
                client = TelegramClient(StringSession(usr["session_string"]), API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                add_log(f"User {telegram_id} is unauthorized. Skipping profile update.")
                return
            client_cache[telegram_id] = client

        sp = get_spotify_client(usr["spotify_refresh_token"])
        current_track = sp.current_user_playing_track()
        
        scroll_key = f"scroll_{telegram_id}"
        last_song_key = f"last_song_{telegram_id}"
        profile_key = f"profile_{telegram_id}"
        profile_update_key = f"profile_update_{telegram_id}"
        flood_until_key = f"flood_until_{telegram_id}"
        flood_log_key = f"flood_log_{telegram_id}"
        scroll_offset = client_cache.get(scroll_key, 0)
        last_song_id = client_cache.get(last_song_key, None)
        now = asyncio.get_running_loop().time()

        async def update_profile_if_allowed(first_name, last_name, about_text, emoji_status=None):
            profile_signature = (first_name or "", last_name or "", about_text or "", emoji_status or "")
            if client_cache.get(profile_key) == profile_signature:
                return

            flood_until = client_cache.get(flood_until_key, 0)
            if now < flood_until:
                return

            last_update = client_cache.get(profile_update_key, 0)
            if last_update and now - last_update < MIN_PROFILE_UPDATE_SECONDS:
                return

            try:
                await client(UpdateProfileRequest(
                    first_name=first_name,
                    last_name=last_name,
                    about=about_text
                ))

                if emoji_status == "clear":
                    try:
                        from telethon.tl.functions.account import UpdateEmojiStatusRequest
                        from telethon.tl.types import EmojiStatusEmpty
                        await client(UpdateEmojiStatusRequest(emoji_status=EmojiStatusEmpty()))
                    except Exception:
                        pass
                elif emoji_status:
                    try:
                        from telethon.tl.functions.account import UpdateEmojiStatusRequest
                        from telethon.tl.types import EmojiStatus
                        await client(UpdateEmojiStatusRequest(
                            emoji_status=EmojiStatus(document_id=int(emoji_status))
                        ))
                    except Exception:
                        pass

                client_cache[profile_key] = profile_signature
                client_cache[profile_update_key] = now
                client_cache.pop(flood_log_key, None)
            except FloodWaitError as e:
                wait_seconds = int(getattr(e, "seconds", 300))
                client_cache[flood_until_key] = now + wait_seconds + 5
                last_log = client_cache.get(flood_log_key, 0)
                if now - last_log > 60:
                    minutes = max(1, round(wait_seconds / 60))
                    add_log(f"Telegram rate limit active for user {telegram_id}; profile updates paused for about {minutes} min.")
                    client_cache[flood_log_key] = now

        if current_track and current_track.get('is_playing'):
            track_name = current_track['item']['name']
            artist_name = current_track['item']['artists'][0]['name']
            track_id = current_track['item']['id']

            if track_id != last_song_id:
                scroll_offset = 0
                client_cache[last_song_key] = track_id

            users_playback_state[telegram_id] = {
                "playing": True,
                "title": track_name,
                "artist": artist_name,
                "progress_ms": current_track.get('progress_ms', 0),
                "duration_ms": current_track['item'].get('duration_ms', 0),
                "album_art": current_track['item']['album']['images'][0]['url'] if current_track['item'].get('album') and current_track['item']['album'].get('images') else "",
                "song_url": current_track['item']['external_urls']['spotify'] if current_track['item'].get('external_urls') and 'spotify' in current_track['item']['external_urls'] else ""
            }

            new_last_name, new_bio = compute_profile_fields(usr, track_name, artist_name, track_id, scroll_offset)
            emoji_status = usr["custom_emoji_id"] if usr["tier"] == "premium" and usr["custom_emoji_id"] else None
            await update_profile_if_allowed(usr["first_name"], new_last_name, new_bio, emoji_status)

            prefix_len = len("🎧 ")
            full_info = f"{track_name} - {artist_name}"
            if len(full_info) > 64 - prefix_len:
                scroll_offset = (scroll_offset + 3) % len(full_info + "   ")
                client_cache[scroll_key] = scroll_offset
        else:
            client_cache[scroll_key] = 0
            client_cache[last_song_key] = None
            users_playback_state[telegram_id] = {
                "playing": False, "title": "", "artist": "", "progress_ms": 0, "duration_ms": 0, "album_art": "", "song_url": ""
            }
            emoji_status = "clear" if usr["tier"] == "premium" else None
            await update_profile_if_allowed(usr["first_name"], usr["last_name"], usr["default_bio"], emoji_status)
    except Exception as e:
        add_log(f"Error syncing user {telegram_id}: {e}")

async def run_sync_scheduler():
    client_cache = {}
    add_log("Background Multi-User Sync Scheduler initialized")
    while True:
        try:
            active_users = database.get_all_active_users()
            tasks = [sync_single_user(usr, client_cache) for usr in active_users]
            if tasks:
                await asyncio.gather(*tasks)
        except Exception as e:
            add_log(f"Scheduler loop error: {e}")
        await asyncio.sleep(10)

async def run_telegram_bot():
    if not BOT_TOKEN:
        add_log("No Telegram Bot Token provided. Skipping Bot listener.")
        return
        
    bot_client = TelegramClient('bot_session', API_ID, API_HASH)
    await bot_client.start(bot_token=BOT_TOKEN)
    add_log("Telegram Bot initialized using token successfully!")
    
    if "127.0.0.1" in WEBAPP_URL or "localhost" in WEBAPP_URL:
        add_log("💡 WARNING: WEBAPP_URL is using localhost / 127.0.0.1. Telegram Mini Apps strictly require a secure public HTTPS URL (like Ngrok) to render inside Telegram. Set WEBAPP_URL in .env to pair on mobile!")
    else:
        add_log(f"🚀 Telegram Mini App WebApp URL configured to: {WEBAPP_URL}")

    @bot_client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        telegram_id = str(event.sender_id)
        if not database.get_user(telegram_id):
            database.save_user(
                telegram_id=telegram_id,
                first_name=event.sender.first_name or "User",
                last_name=event.sender.last_name or "",
                default_bio="Spotify-Telegram Sync User"
            )
            add_log(f"New user registered via bot: {telegram_id}")

        webapp_url = f"{WEBAPP_URL}/?user_id={telegram_id}"
        
        # Build the WebApp Inline button correctly using KeyboardButtonWebView inside ReplyInlineMarkup
        button = KeyboardButtonWebView(
            text="Open Telefy App",
            url=webapp_url
        )
        markup = ReplyInlineMarkup(
            rows=[
                KeyboardButtonRow(buttons=[button])
            ]
        )

        await bot_client.send_message(
            event.chat_id,
            "Welcome to **Telefy**! 🎧\n\nClick the button below to open your personal dashboard and connect Spotify & Telegram.",
            buttons=markup
        )

    await bot_client.run_until_disconnected()

async def main():
    await asyncio.gather(
        start_web_server(),
        run_sync_scheduler(),
        run_telegram_bot()
    )

if __name__ == "__main__":
    asyncio.run(main())
