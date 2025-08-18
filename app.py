from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import qrcode
import io
import base64
import os
import uuid
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ukr-drone-federation-secure-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////tmp/pilots.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Настройки безопасности сессии
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 час в секундах
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'  # True для HTTPS в продакшене
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Защита от XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Защита от CSRF

db = SQLAlchemy(app)

# Декоратор для проверки авторизации админа
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            flash('⚠️ Доступ заборонено! Необхідна авторизація для доступу до адмін-панелі', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Функция для генерации следующего ID пилота
def generate_next_pilot_id():
    try:
        last_pilot = Pilot.query.order_by(Pilot.id.desc()).first()
        if last_pilot and hasattr(last_pilot, 'pilot_id') and last_pilot.pilot_id:
            # Извлекаем номер из UAV-0001
            last_number = int(last_pilot.pilot_id.split('-')[1])
            next_number = last_number + 1
        else:
            next_number = 1
    except:
        # Если таблица еще не создана или ошибка
        next_number = 1
    return f"UAV-{next_number:04d}"

# Модели базы данных
class Pilot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pilot_id = db.Column(db.String(20), unique=True, nullable=False)  # UAV-0001 формат
    callsign = db.Column(db.String(100), nullable=False, unique=True)
    photo_url = db.Column(db.String(200), default='default-pilot.svg')
    category = db.Column(db.String(50), nullable=False)  # 'strike' или 'reconnaissance'
    join_date = db.Column(db.DateTime, default=datetime.now)
    points = db.Column(db.Integer, default=0)
    qr_code = db.Column(db.String(100), unique=True)
    
    def __repr__(self):
        return f'<Pilot {self.callsign}>'

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pilot_id = db.Column(db.Integer, db.ForeignKey('pilot.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    date_awarded = db.Column(db.DateTime, default=datetime.now)
    
    pilot = db.relationship('Pilot', backref=db.backref('achievements', lazy=True))

# Новая модель для логирования активности админки
class AdminActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(50), nullable=False)  # 'add_pilot', 'delete_pilot', 'edit_pilot', 'add_achievement'
    pilot_id = db.Column(db.Integer, db.ForeignKey('pilot.id'), nullable=True)
    pilot_name = db.Column(db.String(100), nullable=True)  # Сохраняем имя на случай удаления пилота
    description = db.Column(db.String(300), nullable=False)
    points_awarded = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
    pilot = db.relationship('Pilot', backref=db.backref('activity_logs', lazy=True))

# Функция для логирования активности админки
def log_admin_activity(action_type, pilot=None, description=None, points_awarded=None):
    pilot_name = pilot.callsign if pilot else None
    pilot_id = pilot.id if pilot else None
    
    log = AdminActivityLog(
        action_type=action_type,
        pilot_id=pilot_id,
        pilot_name=pilot_name,
        description=description,
        points_awarded=points_awarded
    )
    
    db.session.add(log)
    db.session.commit()

# Маршруты
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/rating')
def rating():
    all_pilots = Pilot.query.order_by(Pilot.points.desc()).all()
    strike_pilots = Pilot.query.filter_by(category='strike').order_by(Pilot.points.desc()).all()
    recon_pilots = Pilot.query.filter_by(category='reconnaissance').order_by(Pilot.points.desc()).all()
    
    return render_template('rating.html', 
                         all_pilots=all_pilots,
                         strike_pilots=strike_pilots,
                         recon_pilots=recon_pilots)

@app.route('/pilot/<string:qr_code>')
def pilot_profile(qr_code):
    pilot = Pilot.query.filter_by(qr_code=qr_code).first_or_404()
    achievements = Achievement.query.filter_by(pilot_id=pilot.id).order_by(Achievement.date_awarded.desc()).all()
    
    # Получаем списки для определения места в категории
    all_strike_pilots = Pilot.query.filter_by(category='strike').order_by(Pilot.points.desc()).all()
    all_recon_pilots = Pilot.query.filter_by(category='reconnaissance').order_by(Pilot.points.desc()).all()
    
    # Подсчитываем дни в федерации
    days_in_federation = (datetime.now() - pilot.join_date).days
    
    return render_template('pilot_profile.html', 
                         pilot=pilot, 
                         achievements=achievements,
                         all_strike_pilots=all_strike_pilots,
                         all_recon_pilots=all_recon_pilots,
                         days_in_federation=days_in_federation)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin13')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin1313')
        
        if username == admin_username and password == admin_password:
            session.permanent = True  # Применить тайм-аут сессии
            session['admin'] = True
            flash('Успешна авторизация!')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Неверные данные для входа')
    
    return render_template('admin_login.html')

@app.route('/admin')
@admin_required
def admin_dashboard():
    
    # Получаем статистику
    total_pilots = Pilot.query.count()
    strike_pilots = Pilot.query.filter_by(category='strike').count()
    recon_pilots = Pilot.query.filter_by(category='reconnaissance').count()
    
    # Получаем всех пилотов для возможности поиска
    top_pilots = Pilot.query.order_by(Pilot.points.desc()).all()
    
    # Получаем всех пилотов для поиска и преобразуем в словари
    all_pilots_query = Pilot.query.all()
    all_pilots = []
    for pilot in all_pilots_query:
        pilot_data = {
            'id': pilot.id,
            'pilot_id': pilot.pilot_id,
            'callsign': pilot.callsign,
            'category': pilot.category,
            'points': pilot.points,
            'photo_url': pilot.photo_url,
            'join_date': pilot.join_date.strftime('%d.%m.%Y'),
            'achievements': [{'description': ach.description, 'points': ach.points} for ach in pilot.achievements]
        }
        all_pilots.append(pilot_data)
    
    # Получаем последние 20 записей активности
    activity_logs = AdminActivityLog.query.order_by(AdminActivityLog.timestamp.desc()).limit(20).all()
    
    return render_template('admin_dashboard.html', 
                         pilots=top_pilots, 
                         all_pilots=all_pilots,
                         total_pilots=total_pilots,
                         strike_pilots=strike_pilots,
                         recon_pilots=recon_pilots,
                         activity_logs=activity_logs)

@app.route('/admin/pilot/add', methods=['GET', 'POST'])
@admin_required
def admin_add_pilot():
    
    if request.method == 'POST':
        callsign = request.form['callsign']
        category = request.form['category']
        photo_url = request.form.get('photo_url', 'default-pilot.svg')
        
        # Генерируем уникальный QR код и ID пилота
        qr_code = str(uuid.uuid4())
        pilot_id = generate_next_pilot_id()
        
        pilot = Pilot(
            pilot_id=pilot_id,
            callsign=callsign,
            category=category,
            photo_url=photo_url,
            qr_code=qr_code
        )
        
        db.session.add(pilot)
        db.session.commit()
        
        # Сохраняем QR код в файл
        save_pilot_qr_code(pilot)
        
        # Логируем активность
        log_admin_activity(
            action_type='add_pilot',
            pilot=pilot,
            description=f'Добавлен новый пилот {callsign} ({pilot_id}) в категории {category}'
        )
        
        flash(f'Пилот {callsign} (ID: {pilot_id}) успешно добавлен')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_add_pilot.html')

@app.route('/admin/pilot/<int:pilot_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_pilot(pilot_id):
    
    pilot = Pilot.query.get_or_404(pilot_id)
    
    if request.method == 'POST':
        old_callsign = pilot.callsign
        old_category = pilot.category
        
        pilot.callsign = request.form['callsign']
        pilot.category = request.form['category']
        pilot.photo_url = request.form.get('photo_url', pilot.photo_url)
        
        db.session.commit()
        
        # Логируем активность
        changes = []
        if old_callsign != pilot.callsign:
            changes.append(f'позивний: {old_callsign} → {pilot.callsign}')
        if old_category != pilot.category:
            changes.append(f'категорія: {old_category} → {pilot.category}')
        
        if changes:
            log_admin_activity(
                action_type='edit_pilot',
                pilot=pilot,
                description=f'Редагування пілота {pilot.callsign}: {", ".join(changes)}'
            )
        
        flash(f'Пилот {pilot.callsign} успешно обновлен')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_edit_pilot.html', pilot=pilot)

@app.route('/admin/pilot/<int:pilot_id>/delete', methods=['POST'])
@admin_required
def admin_delete_pilot(pilot_id):
    
    pilot = Pilot.query.get_or_404(pilot_id)
    pilot_callsign = pilot.callsign
    pilot_pilot_id = pilot.pilot_id
    
    # Логируем активность перед удалением
    log_admin_activity(
        action_type='delete_pilot',
        pilot=pilot,
        description=f'Видалено пілота {pilot_callsign} ({pilot_pilot_id})'
    )
    
    # Удаляем связанные достижения
    Achievement.query.filter_by(pilot_id=pilot_id).delete()
    
    db.session.delete(pilot)
    db.session.commit()
    
    flash(f'Пилот {pilot_callsign} успешно удален')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/pilot/<int:pilot_id>/add_achievement', methods=['POST'])
@admin_required
def admin_add_achievement(pilot_id):
    
    pilot = Pilot.query.get_or_404(pilot_id)
    description = request.form['description']
    points = int(request.form['points'])
    
    achievement = Achievement(
        pilot_id=pilot_id,
        description=description,
        points=points
    )
    
    # Обновляем общие очки пилота
    pilot.points += points
    
    db.session.add(achievement)
    db.session.commit()
    
    # Логируем активность
    log_admin_activity(
        action_type='add_achievement',
        pilot=pilot,
        description=f'Нараховано досягнення "{description}" для пілота {pilot.callsign}',
        points_awarded=points
    )
    
    flash(f'Достижение добавлено для {pilot.callsign}')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
@admin_required
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))



@app.route('/qr/<string:qr_code>')
def generate_qr(qr_code):
    pilot = Pilot.query.filter_by(qr_code=qr_code).first_or_404()
    
    # Путь к файлу QR кода
    qr_filename = f"{pilot.pilot_id}.png"
    qr_filepath = os.path.join('static', 'qr_codes', qr_filename)
    
    # Проверяем, существует ли файл, если нет - создаем
    if not os.path.exists(qr_filepath):
        # Создаем QR код
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(request.url_root + f'pilot/{qr_code}')
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Сохраняем в файл
        img.save(qr_filepath)
    
    # Возвращаем HTML с изображением
    return f'<img src="{url_for("static", filename=f"qr_codes/{qr_filename}")}" alt="QR Code for {pilot.callsign}" style="width: 150px; height: 150px;">'

# Функция для сохранения QR кода при создании пилота
def save_pilot_qr_code(pilot):
    qr_filename = f"{pilot.pilot_id}.png"
    qr_filepath = os.path.join('static', 'qr_codes', qr_filename)
    
    # Создаем QR код
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
    qr.add_data(f'{base_url}/pilot/{pilot.qr_code}')
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_filepath)
    
    return qr_filename

if __name__ == '__main__':
    # Создаем необходимые директории
    os.makedirs('/tmp', exist_ok=True)
    os.makedirs('static/qr_codes', exist_ok=True)
    
    with app.app_context():
        db.create_all()
        
        # Создаем тестовых пилотов, если их нет
        if Pilot.query.count() == 0:
            test_pilots = [
                {
                    'pilot_id': 'UAV-0001',
                    'callsign': 'Орел',
                    'category': 'strike',
                    'photo_url': 'default-pilot.svg',
                    'points': 1250,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'pilot_id': 'UAV-0002',
                    'callsign': 'Сокол',
                    'category': 'reconnaissance',
                    'photo_url': 'default-pilot.svg',
                    'points': 980,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'pilot_id': 'UAV-0003',
                    'callsign': 'Беркут',
                    'category': 'strike',
                    'photo_url': 'default-pilot.svg',
                    'points': 1400,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'pilot_id': 'UAV-0004',
                    'callsign': 'Ястреб',
                    'category': 'reconnaissance',
                    'photo_url': 'default-pilot.svg',
                    'points': 1120,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'pilot_id': 'UAV-0005',
                    'callsign': 'Кондор',
                    'category': 'strike',
                    'photo_url': 'default-pilot.svg',
                    'points': 750,
                    'qr_code': str(uuid.uuid4())
                }
            ]
            
            for pilot_data in test_pilots:
                pilot = Pilot(**pilot_data)
                db.session.add(pilot)
            
            db.session.commit()
            
            # Создаем QR коды для всех тестовых пилотов
            for pilot in Pilot.query.all():
                save_pilot_qr_code(pilot)
            
            print("Тестовые пилоты созданы с QR кодами")
    
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)
