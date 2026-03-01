import sqlite3
import os
import logging
from multivol.api_server.config import STORAGE_DIR

def get_db_connection():
    db_path = os.path.join(STORAGE_DIR, 'scans.db')
    conn = sqlite3.connect(db_path, timeout=10.0) # wait up to 10s if db is locked
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Create tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS scans (
            uuid TEXT PRIMARY KEY,
            name TEXT,
            status TEXT,
            filepath TEXT,
            dump_path TEXT,
            size INTEGER,
            image TEXT,
            os TEXT,
            volatility_version TEXT,
            output_dir TEXT,
            error TEXT,
            config_json TEXT, -- Store extra scan parameters (e.g., {"fetch_symbol": true})
            created_at REAL
        )
    ''')
    # Track the status of individual modules for a scan
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_module_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT,
            module TEXT,
            status TEXT,
            error_message TEXT,
            updated_at REAL,
            FOREIGN KEY (scan_id) REFERENCES scans (uuid)
        )
    ''')
    # Use UNIQUE index to prevent duplicates instead of INSERT OR IGNORE logic manually
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_scan_module ON scan_module_status(scan_id, module)')

    # Track results independently of status
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT,
            module TEXT,
            content TEXT,
            created_at REAL,
            FOREIGN KEY (scan_id) REFERENCES scans (uuid)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS dump_tasks (
            task_id TEXT PRIMARY KEY,
            scan_id TEXT,
            status TEXT,
            output_path TEXT,
            error TEXT,
            created_at REAL,
            FOREIGN KEY (scan_id) REFERENCES scans (uuid)
        )
    ''')


    # ---------------------------------------------------------
    # Schema Migration Logic 
    # (If adding columns to existing tables where they might not exist)
    # ---------------------------------------------------------
    
    # 1. Add dump_path to scans if missing (from previous updates)
    c.execute("PRAGMA table_info(scans)")
    columns = [col[1] for col in c.fetchall()]
    if 'dump_path' not in columns:
        logging.info("Adding 'dump_path' column to 'scans' table.")
        c.execute("ALTER TABLE scans ADD COLUMN dump_path TEXT")
        # Migrate filepath -> dump_path
        c.execute("UPDATE scans SET dump_path = filepath")

    # 2. Add config_json to scans if missing
    if 'config_json' not in columns:
         logging.info("Adding 'config_json' column to 'scans' table.")
         c.execute("ALTER TABLE scans ADD COLUMN config_json TEXT")

    # 3. Rename case_name to name in scans if missing
    if 'name' not in columns and 'case_name' in columns:
        logging.info("Translating 'case_name' -> 'name'.")
        try:
             c.execute("ALTER TABLE scans RENAME COLUMN case_name TO name")
        except Exception as e:
             logging.error(f"Could not rename column: {e}. If 'name' is missing, schema might be corrupt or older SQLite.")
    elif 'name' not in columns:
         logging.warning("'name' column missing. Attempting ADD COLUMN.")
         try:
             c.execute("ALTER TABLE scans ADD COLUMN name TEXT")
         except:
             pass

    # 4. Add mode to scans if missing
    if 'mode' not in columns:
        logging.info("Adding 'mode' column to 'scans' table.")
        c.execute("ALTER TABLE scans ADD COLUMN mode TEXT DEFAULT 'full'")

    conn.commit()
    conn.close()
