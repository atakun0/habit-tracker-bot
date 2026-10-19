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

def get_habit_stats(user_id: int):
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT habit_name, COUNT(date) 
        FROM habit_logs 
        WHERE user_id = ? 
        GROUP BY habit_name
    ''', (user_id,))
    
    stats = cursor.fetchall() 
    conn.close()
    
    return stats

def check_habit_logged_today(user_id: int, habit_name: str) -> bool:
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    
    today = datetime.date.today().isoformat()
    
    cursor.execute('''
        SELECT 1 FROM habit_logs 
        WHERE user_id = ? AND habit_name = ? AND date = ?
    ''', (user_id, habit_name, today))
    
    result = cursor.fetchone()
    conn.close()
    
    return bool(result)

def get_habit_streak(user_id: int, habit_name: str) -> int:
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT date FROM habit_logs 
        WHERE user_id = ? AND habit_name = ? 
        ORDER BY date DESC
    ''', (user_id, habit_name))
    
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return 0

    dates = sorted(list(set([datetime.date.fromisoformat(row[0]) for row in rows])), reverse=True)

    streak = 0
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    if dates[0] not in (today, yesterday):
        return 0

    check_date = dates[0]
    for d in dates:
        if d == check_date:
            streak += 1
            check_date -= datetime.timedelta(days=1)
        else:
            break

    return streak

def get_all_users() -> list[int]:
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT user_id FROM habits')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def rename_habit(user_id: int, old_name: str, new_name: str):
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE habits SET habit_name = ? 
        WHERE user_id = ? AND habit_name = ?
    ''', (new_name, user_id, old_name))
    
    cursor.execute('''
        UPDATE habit_logs SET habit_name = ? 
        WHERE user_id = ? AND habit_name = ?
    ''', (new_name, user_id, old_name))
    
    conn.commit()
    conn.close()

def get_all_logs(user_id: int) -> list[tuple]:
    conn = sqlite3.connect('habits.db')
    cursor = conn.cursor()
    # Забираем название привычки и дату, сортируем от новых к старым
    cursor.execute('''
        SELECT habit_name, date FROM habit_logs 
        WHERE user_id = ? 
        ORDER BY date DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows