import sqlite3

def init_db():
    conn = sqlite3.connect('project.db')
    cursor = conn.cursor()

    # Table to store main activities/nonprofits/clubs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            organization TEXT,
            category TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()
    print("Database and 'activities' table initialized successfully!")

if __name__ == '__main__':
    init_db()
