import sqlite3

# Update this path if your database is elsewhere
DB_PATH = '/home/WHSDTECH/Digitaltech_portal/your_database.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Create user_roles table (edit columns as needed)
    c.execute('''
    CREATE TABLE IF NOT EXISTS user_roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        role TEXT NOT NULL
    )
    ''')
    conn.commit()
    conn.close()
    print('Database initialized and user_roles table created.')

if __name__ == '__main__':
    init_db()
