# tracker.py is for SQLite management. It's where I wrote the read/write helpers
import sqlite3
import os


# Set up SQLite connection and create tables
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'history.db')

# returns a connection to the SQLite database
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This allows us to access columns by name
    return conn

# initializes the database and creates the contacts table if it doesn't exist
def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker_id TEXT NOT NULL UNIQUE,
            broker_name TEXT NOT NULL,
            method TEXT NOT NULL, -- email, form, or manual
            status TEXT NOT NULL, -- pending, sent, confirmed, failed, captcha_blocked, needs_manual
            priority TEXT NOT NULL, -- high, medium, low
            opt_out_url TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NULL, -- let it remain null until we run the second script
            comments TEXT,
            response_time_hours REAL DEFAULT NULL -- how long it took to get a confirmation email back, in hours
        )
    ''')
    conn.commit()
    conn.close()

# pass in all parameters, opt_out_url and comments are optional, and sent_at is automatically filled, updated_at is to null until the second script runs. This function logs a new request to the database
def log_request(broker_id, broker_name, method, status, priority, opt_out_url=None, comments=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO requests (broker_id, broker_name, method, status, priority, opt_out_url, comments)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (broker_id, broker_name, method, status, priority, opt_out_url, comments))
    conn.commit()
    conn.close()

def update_status(broker_id, new_status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE requests
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE broker_id = ?
    ''', (new_status, broker_id))
    conn.commit()
    conn.close()

# pending means not yet sent but scheduled to be sent, 
# sent means email blast or form submission has been completed but not yet confirmed, 
# confirmed means we found the confirmation email in Gmail inbox and marked it as confirmed, 
# failed means we attempted to send but got an error back, needs_manual means we attempted
#  to send but got an error that requires manual review (like captcha or multi step form), 
# captcha_blocked means we attempted to send but got blocked by a captcha that we couldn't solve
def get_pending():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM requests
        WHERE status = 'pending'
        ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END ASC
    ''')
    results = cursor.fetchall()
    conn.close()
    return results

def get_report_data():
    conn = get_connection()
    cursor = conn.cursor()
    # succcessful query
    successful = cursor.execute('''
        SELECT * FROM requests 
        WHERE status IN ('confirmed', 'form_submitted')
        ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END ASC
    ''').fetchall()

    # high priority manual/captcha_blocked
    high_priority_issues = cursor.execute('''
        SELECT * FROM requests 
        WHERE status IN ('needs_manual', 'captcha_blocked') AND priority = 'high'
    ''').fetchall()

    lower_priority_issues = cursor.execute('''
        SELECT * FROM requests 
        WHERE status IN ('needs_manual', 'captcha_blocked') AND priority != 'high'
    ''').fetchall()

    conn.close()
    return {
        "successful": successful,
        "high_priority_issues": high_priority_issues,
        "lower_priority_issues": lower_priority_issues
    }

def reset_db():
    confirm = input("Are you sure you want to reset the database? This will delete all records. Type 'yes' to confirm: ")
    if confirm.lower() != 'yes':
        print('Cancelled.')
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS requests')
    conn.commit()
    conn.close()
    print("Database cleared.")

def log_confirmation(broker_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE requests
        SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP,
            response_time_hours = (julianday('now') - julianday(sent_at)) * 24
        WHERE broker_id = ?
    ''', (broker_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    reset_db()