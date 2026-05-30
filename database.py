import sqlite3
import os
import base64
from cryptography.fernet import Fernet

DB_FILE = "database.db"

# Retrieve or generate encryption key from environment variable
ENCRYPTION_KEY = os.getenv("SECRET_ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # Fallback to local auto-generated key file for testing security
    if os.path.exists("secret.key"):
        with open("secret.key", "rb") as key_file:
            ENCRYPTION_KEY = key_file.read()
    else:
        ENCRYPTION_KEY = Fernet.generate_key()
        with open("secret.key", "wb") as key_file:
            key_file.write(ENCRYPTION_KEY)

cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_value(val):
    if not val:
        return val
    # Don't encrypt if it's already encrypted
    if val.startswith("gAAAAA"):
        return val
    try:
        return cipher_suite.encrypt(val.encode('utf-8')).decode('utf-8')
    except Exception:
        return val

def decrypt_value(val):
    if not val:
        return val
    try:
        return cipher_suite.decrypt(val.encode('utf-8')).decode('utf-8')
    except Exception:
        return val

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id TEXT PRIMARY KEY,
        phone TEXT,
        session_string TEXT,
        spotify_refresh_token TEXT,
        first_name TEXT,
        last_name TEXT,
        default_bio TEXT,
        is_syncing INTEGER DEFAULT 1,
        tier TEXT DEFAULT 'free',
        custom_emoji_id TEXT
    )
    """)
    conn.commit()
    conn.close()

def get_user(telegram_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        # Decrypt sensitive columns
        d["session_string"] = decrypt_value(d["session_string"])
        d["spotify_refresh_token"] = decrypt_value(d["spotify_refresh_token"])
        return d
    return None

def get_all_active_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE is_syncing = 1")
    rows = cursor.fetchall()
    conn.close()
    
    users = []
    for r in rows:
        d = dict(r)
        d["session_string"] = decrypt_value(d["session_string"])
        d["spotify_refresh_token"] = decrypt_value(d["spotify_refresh_token"])
        users.append(d)
    return users

def save_user(telegram_id, phone=None, session_string=None, spotify_refresh_token=None,
              first_name=None, last_name=None, default_bio=None, is_syncing=None, tier=None, custom_emoji_id=None):
    
    # Encrypt credentials before saving to database
    enc_session = encrypt_value(session_string)
    enc_spotify = encrypt_value(spotify_refresh_token)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM users WHERE telegram_id = ?", (telegram_id,))
    exists = cursor.fetchone()
    
    if not exists:
        cursor.execute("""
        INSERT INTO users (telegram_id, phone, session_string, spotify_refresh_token, first_name, last_name, default_bio, is_syncing, tier, custom_emoji_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (telegram_id, phone, enc_session, enc_spotify, first_name, last_name, default_bio, is_syncing or 1, tier or 'free', custom_emoji_id))
    else:
        updates = []
        params = []
        for field, val in [("phone", phone), ("session_string", enc_session), 
                           ("spotify_refresh_token", enc_spotify), ("first_name", first_name), 
                           ("last_name", last_name), ("default_bio", default_bio), 
                           ("is_syncing", is_syncing), ("tier", tier), ("custom_emoji_id", custom_emoji_id)]:
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if updates:
            params.append(telegram_id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ?", params)
            
    conn.commit()
    conn.close()

def clear_field(telegram_id, field_name):
    """Set a sensitive field to NULL so bool() checks correctly return False."""
    allowed_fields = {"session_string", "spotify_refresh_token", "custom_emoji_id"}
    if field_name not in allowed_fields:
        raise ValueError(f"Field '{field_name}' is not clearable.")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {field_name} = NULL WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

init_db()
