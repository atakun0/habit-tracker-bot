import sqlite3
import datetime

def init_db():
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            habit_name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            habit_name TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_habit(user_id: int, habit_name: str):
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO habits (user_id, habit_name) VALUES (?, ?)', (user_id, habit_name))
    conn.commit()
    conn.close()

def get_habits(user_id: int):
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    cursor.execute('SELECT habit_name FROM habits WHERE user_id = ?', (user_id,))
    habits = cursor.fetchall()
    conn.close()
    
    return [habit[0] for habit in habits]

def delete_habit(user_id: int, habit_name: str):
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM habits WHERE user_id = ? AND habit_name = ?', (user_id, habit_name))
    conn.commit()
    conn.close()

def log_habit(user_id: int, habit_name: str):
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    
    # Получаем сегодняшнюю дату в формате YYYY-MM-DD (например, 2026-10-07)
    today = datetime.date.today().isoformat()
    
    cursor.execute('INSERT INTO habit_logs (user_id, habit_name, date) VALUES (?, ?, ?)', (user_id, habit_name, today))
    conn.commit()
    conn.close()