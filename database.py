import sqlite3

def connect_db():
    conn = sqlite3.connect('interview.db')
    return conn

def create_table():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            violations INTEGER,
            risk_score INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def insert_result(name, violations, risk_score):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO results (name, violations, risk_score)
        VALUES (?, ?, ?)
    ''', (name, violations, risk_score))

    conn.commit()
    conn.close()

def get_all_results():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM results')
    data = cursor.fetchall()

    conn.close()
    return data