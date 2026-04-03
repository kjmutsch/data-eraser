# Flask dashboard that shows which brokers have been contacted, which have been confirmed, and which are pending
# I added three different pages: Dashboard, which shows overall stats
# Brokers: which shows the status of each broker (searchable, filterable)
# Hardest: which tells us how difficult it was to get a response from each broker
# All three pages refresh every 30 seconds

import os
from flask import Flask, render_template, jsonify
from tracker import get_report_data, get_connection

# we will use this connection to get the data for the dashboard, but we won't keep it open since we want to open and close connections as needed to avoid locking issues
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates', 'dashboard'))

def get_all_brokers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM requests
        ORDER BY 
            CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END ASC,
            broker_name ASC
    ''')
    # dict is needed to convert from sqlite row object to a regular dict that can be easily used in the frontend
    # cursor.fetchall() returns a list of rows, and each row is a sqlite3.Row object which is like a dict but not exactly, so we convert each row to a dict
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results # results is a list of dicts

def get_hardest_brokers():
    conn = get_connection()
    cursor = conn.cursor()
    # how we decide difficulty is by looking at who never responded, then ordering by response time
    cursor.execute('''
        SELECT 
            broker_name,
            method,
            status,
            priority,
            response_time_hours,
            sent_at,
            updated_at
        FROM requests
        ORDER BY
            CASE 
                WHEN status IN ('needs_manual', 'captcha_blocked', 'failed') THEN 0
                WHEN response_time_hours IS NULL THEN 1
                ELSE 2
            END ASC,
            response_time_hours DESC NULLS LAST
    ''')
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results

def get_response_time_buckets():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT response_time_hours
        FROM requests
        WHERE response_time_hours IS NOT NULL
        AND status = 'confirmed'
    ''')
    rows = cursor.fetchall()
    conn.close()

    # build buckets of response times in 24 hour increments (0-24, 24-48, 48-72, 72+)
    buckets = {f"{i}-{i+1}h": 0 for i in range(24)}
    buckets['24-48h'] = 0
    buckets['48-72h'] = 0
    buckets['1-2 weeks'] = 0
    buckets['2-4 weeks'] = 0
    buckets['30+ days'] = 0
    buckets['never'] = 0 # for when they never responded

    for row in rows:
        hours = row['response_time_hours']
        if hours is None:
            buckets['never'] += 1
        elif hours < 24:
            bucket_key = f"{int(hours)}-{int(hours)+1}h"
            buckets[bucket_key] += 1
        elif hours < 48:
            buckets['24-48h'] += 1
        elif hours < 72:
            buckets['48-72h'] += 1
        elif hours < 336:
            buckets['1-2 weeks'] += 1
        elif hours < 672:
            buckets['2-4 weeks'] += 1
        else:
            buckets['30+ days'] += 1

    # count brokers that never responded
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as count FROM requests
        WHERE status IN ('sent', 'needs_manual', 'captcha_blocked', 'failed')
        AND response_time_hours IS NULL
    ''')
    never_responded_count = cursor.fetchone()['count']
    conn.close()
    buckets['never'] = never_responded_count

    return buckets

def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM requests')
    total = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM requests WHERE status IN ('confirmed', 'form_submitted')")
    successful = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM requests WHERE status IN ('needs_manual', 'captcha_blocked')")
    needs_attention = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM requests WHERE status IN ('needs_manual', 'captcha_blocked') AND priority = 'high'")
    high_priority = cursor.fetchone()['count']

    cursor.execute("SELECT AVG(response_time_hours) as avg FROM requests WHERE response_time_hours IS NOT NULL")
    avg_response = cursor.fetchone()['avg']
    avg_response = round(avg_response, 1) if avg_response else 'N/A'

    conn.close()
    return {
        'total': total,
        'successful': successful,
        'needs_attention': needs_attention,
        'high_priority': high_priority,
        'avg_response_time': avg_response
    }

@app.route('/')
def index():
    stats = get_stats()
    data = get_report_data() # this includes the lists of successful, high priority issues, and lower priority issues that we can use to populate the tables on the dashboard
    successful = [dict(row) for row in data['successful']] # casting to dict so we can easily use in frontend
    high_priority_issues = [dict(row) for row in data['high_priority_issues']]
    lower_priority_issues = [dict(row) for row in data['lower_priority_issues']]
    return render_template('index.html', stats=stats, successful=successful, high_priority_issues=high_priority_issues, lower_priority_issues=lower_priority_issues)

@app.route('/brokers')
def brokers():
    brokers = get_all_brokers()
    return render_template('brokers.html', brokers=brokers)

@app.route('/hardest')
def hardest():
    brokers = get_hardest_brokers()
    buckets = get_response_time_buckets()
    return render_template('hardest.html', brokers=brokers, buckets=buckets)

# API endpoint for auto-refresh — returns fresh stats as JSON
@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())

@app.route('/api/brokers')
def api_brokers():
    return jsonify(get_all_brokers())

@app.route('/api/report')
def api_report():
    data = get_report_data()
    return jsonify({
        'successful': [dict(row) for row in data['successful']],
        'high_priority_issues': [dict(row) for row in data['high_priority_issues']],
        'lower_priority_issues': [dict(row) for row in data['lower_priority_issues']]
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)