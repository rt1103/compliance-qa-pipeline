import sqlite3
import json
import hashlib
import os
import logging

logger = logging.getLogger("brand-guardian-cache")

# Define where the local database file will be stored
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/video_cache.db"))

def init_db():
    """Initializes the SQLite database and creates the cache table if it doesn't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_cache (
            url_hash TEXT PRIMARY KEY,
            video_url TEXT,
            clean_data JSON
        )
    ''')
    conn.commit()
    conn.close()

def get_url_hash(video_url: str) -> str:
    """Generates a SHA-256 hash of the YouTube URL."""
    return hashlib.sha256(video_url.encode('utf-8')).hexdigest()

def get_cached_video(video_url: str):
    """Retrieves cached extraction data if the video URL hash exists."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    url_hash = get_url_hash(video_url)
    
    c.execute('SELECT clean_data FROM video_cache WHERE url_hash = ?', (url_hash,))
    row = c.fetchone()
    conn.close()
    
    if row:
        logger.info(f"CACHE HIT: Data found for URL {video_url}")
        return json.loads(row[0])
    
    logger.info(f"CACHE MISS: No data found for URL {video_url}")
    return None

def save_to_cache(video_url: str, clean_data: dict):
    """Saves the extracted clean data to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    url_hash = get_url_hash(video_url)
    
    c.execute('''
        INSERT OR REPLACE INTO video_cache (url_hash, video_url, clean_data)
        VALUES (?, ?, ?)
    ''', (url_hash, video_url, json.dumps(clean_data)))
    
    conn.commit()
    conn.close()
    logger.info(f"CACHE SAVED: Data stored for URL {video_url}")