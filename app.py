import os, random, time, secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import db as database
from db import upload_photo, USE_SUPABASE

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', secrets.token_hex(32))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED

# ── Sensor Station Data ───────────────────────────────────────────────────────
STATIONS = [
    {"id": 1, "name": "Palla",       "lat": 28.877, "lng": 77.175, "stretch": "Upstream"},
    {"id": 2, "name": "Wazirabad",   "lat": 28.739, "lng": 77.218, "stretch": "Urban Entry"},
    {"id": 3, "name": "Nizamuddin",  "lat": 28.610, "lng": 77.248, "stretch": "Urban Core"},
    {"id": 4, "name": "Okhla",       "lat": 28.535, "lng": 77.272, "stretch": "Urban Exit"},
    {"id": 5, "name": "Agra Canal",  "lat": 28.430, "lng": 77.300, "stretch": "Downstream"},
]

STATION_PROFILES = {
    1: dict(bod=(3,8),    do=(6,9),    ph=(7.2,7.8), turb=(10,40),  nit=(2,10),  phos=(0.5,3)),
    2: dict(bod=(30,70),  do=(1.5,4),  ph=(6.9,7.6), turb=(50,150), nit=(10,30), phos=(3,12)),
    3: dict(bod=(60,120), do=(0.5,2),  ph=(6.8,7.5), turb=(80,200), nit=(20,45), phos=(8,22)),
    4: dict(bod=(50,100), do=(0.8,2.5),ph=(6.8,7.5), turb=(70,180), nit=(15,40), phos=(6,18)),
    5: dict(bod=(20,50),  do=(2,5),    ph=(7.0,7.6), turb=(30,100), nit=(8,25),  phos=(3,10)),
}
COLIFORM_LEVELS = {1:("LOW","MODERATE"), 2:("HIGH","VERY HIGH"), 3:("VERY HIGH","CRITICAL"),
                   4:("VERY HIGH","CRITICAL"), 5:("HIGH","VERY HIGH")}

def station_reading(sid, seed_offset=0):
    random.seed(int(time.time() / 10) + seed_offset)
    p = STATION_PROFILES[sid]
    bod  = round(random.uniform(*p['bod']),  1)
    do   = round(random.uniform(*p['do']),   1)
    ph   = round(random.uniform(*p['ph']),   2)
    turb = round(random.uniform(*p['turb']), 1)
    nit  = round(random.uniform(*p['nit']),  1)
    phos = round(random.uniform(*p['phos']), 1)
    col  = random.choice(COLIFORM_LEVELS[sid])
    score = max(0, min(100, int((do/9)*45 + max(0,(1-bod/120))*30 + (1-turb/200)*15 + 10)))
    label = "GOOD" if score>=70 else "MODERATE" if score>=45 else "POOR" if score>=25 else "CRITICAL"
    return dict(bod=bod, do=do, ph=ph, turbidity=turb, nitrates=nit,
                phosphates=phos, coliform=col, score=score, label=label)

# ── Auth helpers ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('index.html')
    return render_template('login.html')

@app.route('/app')
def main_app():
    if 'user_id' not in session:
        from flask import redirect
        return redirect('/')
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/static/uploads/<path:fn>')
def uploaded_file(fn):
    return send_from_directory(UPLOAD_FOLDER, fn)

# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/auth/register', methods=['POST'])
def register():
    d = request.get_json()
    name  = d.get('name', '').strip()
    email = d.get('email', '').strip().lower()
    pw    = d.get('password', '')
    if not name or not email or not pw:
        return jsonify({'error': 'All fields required'}), 400
    if len(pw) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    try:
        db = database.get_db()
        user = db.create_user(name, email, generate_password_hash(pw))
        session['user_id']   = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
        return jsonify({'success': True, 'name': name, 'role': user['role']})
    except Exception as e:
        if 'unique' in str(e).lower() or 'UNIQUE' in str(e):
            return jsonify({'error': 'Email already registered'}), 409
        return jsonify({'error': str(e)}), 500

@app.route('/auth/login', methods=['POST'])
def login():
    d     = request.get_json()
    email = d.get('email', '').strip().lower()
    pw    = d.get('password', '')
    try:
        db   = database.get_db()
        user = db.get_user_by_email(email)
        if not user or not check_password_hash(user['password'], pw):
            return jsonify({'error': 'Invalid email or password'}), 401
        session['user_id']   = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
        return jsonify({'success': True, 'name': user['name'], 'role': user['role']})
    except RuntimeError as e:
        # Tables don't exist in Supabase yet
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        return jsonify({'error': f'Login error: {str(e)}'}), 500

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/auth/me')
def me():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'name': session['user_name'],
                        'role': session['user_role'], 'id': session['user_id']})
    return jsonify({'logged_in': False})

# ── Live sensor API ───────────────────────────────────────────────────────────
@app.route('/api/live')
def live():
    sid  = int(request.args.get('station', 3))
    data = station_reading(sid)
    st   = next(s for s in STATIONS if s['id'] == sid)
    # Persist reading to DB
    try:
        db = database.get_db()
        db.insert_reading({
            'station_id': sid, 'bod': data['bod'], 'do_level': data['do'],
            'ph': data['ph'], 'turbidity': data['turbidity'],
            'nitrates': data['nitrates'], 'phosphates': data['phosphates'],
            'score': data['score']
        })
    except Exception as e:
        print(f"[Readings] Insert error: {e}")
    return jsonify({**data, 'station': st['name'], 'station_id': sid,
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'storage': 'Supabase' if USE_SUPABASE else 'SQLite (local)'})

@app.route('/api/stations')
def stations():
    result = []
    for st in STATIONS:
        r = station_reading(st['id'], seed_offset=st['id'])
        result.append({**st, **r})
    return jsonify(result)

@app.route('/api/history')
def history():
    sid  = int(request.args.get('station', 3))
    db   = database.get_db()
    rows = db.get_readings(sid, limit=15)
    if rows:
        key = 'recorded_at' if 'recorded_at' in rows[0] else 'created_at'
        return jsonify({
            'labels': [str(r.get(key, ''))[-13:-8] for r in rows],
            'bod':    [r['bod'] for r in rows],
            'do':     [r['do_level'] for r in rows]
        })
    # Simulated fallback
    labels, bod_v, do_v = [], [], []
    base = int(time.time() / 10)
    for i in range(12):
        t = datetime.now() - timedelta(minutes=10*(11-i))
        labels.append(t.strftime('%H:%M'))
        random.seed(base - (11-i)*3 + sid)
        p = STATION_PROFILES[sid]
        bod_v.append(round(random.uniform(*p['bod']), 1))
        do_v.append(round(random.uniform(*p['do']), 1))
    return jsonify({'labels': labels, 'bod': bod_v, 'do': do_v})

# ── Reports ───────────────────────────────────────────────────────────────────
@app.route('/api/reports', methods=['GET'])
def get_reports():
    status  = request.args.get('status', 'ALL')
    mine    = request.args.get('mine') == '1'
    db      = database.get_db()
    user_id = session.get('user_id') if mine else None
    return jsonify(db.get_reports(status=status, user_id=user_id))

@app.route('/api/reports', methods=['POST'])
@login_required
def create_report():
    photo_url = ''
    if 'photo' in request.files:
        f = request.files['photo']
        if f and f.filename and allowed_file(f.filename):
            ext      = f.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"{int(time.time())}_{f.filename}")
            file_bytes   = f.read()
            content_type = f.mimetype or f'image/{ext}'
            photo_url = upload_photo(file_bytes, filename, content_type)

    db = database.get_db()
    report = db.insert_report({
        'user_id':     session['user_id'],
        'type':        request.form.get('type', 'Other'),
        'station':     request.form.get('station', ''),
        'location':    request.form.get('location', ''),
        'description': request.form.get('description', ''),
        'severity':    request.form.get('severity', 'MEDIUM'),
        'photo_url':   photo_url,
        'lat':         float(request.form.get('lat') or 0),
        'lng':         float(request.form.get('lng') or 0),
    })
    return jsonify({'success': True, 'id': report.get('id'), 'photo_url': photo_url})

@app.route('/api/reports/<int:rid>', methods=['PATCH'])
@login_required
def update_status(rid):
    status = request.json.get('status')
    database.get_db().update_report_status(rid, status)
    return jsonify({'success': True})

# ── Alerts ─────────────────────────────────────────────────────────────────
@app.route('/api/alerts')
def get_alerts():
    return jsonify(database.get_db().get_alerts())

# ── Profile stats ─────────────────────────────────────────────────────────────
@app.route('/api/profile/stats')
@login_required
def profile_stats():
    return jsonify(database.get_db().profile_stats(session['user_id']))

# ── System info ───────────────────────────────────────────────────────────────
@app.route('/api/system')
def system_info():
    return jsonify({
        'storage': 'Supabase Cloud' if USE_SUPABASE else 'SQLite (local)',
        'db_type':  'PostgreSQL' if USE_SUPABASE else 'SQLite',
        'images':   'Supabase Storage' if USE_SUPABASE else 'Local /static/uploads',
    })

if __name__ == '__main__':
    mode = "☁️  Supabase Cloud" if USE_SUPABASE else "🗄️  SQLite (local fallback)"
    print(f"\n  YamunaWatch — Storage: {mode}\n")
    app.run(debug=True, port=5002)
