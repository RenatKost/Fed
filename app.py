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

# Функция для генерации следующего ID участника
def generate_next_participant_id():
    try:
        # Получаем все ID из обеих таблиц
        participant_ids = []
        
        # Новые участники
        participants = Participant.query.all()
        for p in participants:
            if p.participant_id and p.participant_id.startswith('UAV-'):
                try:
                    num = int(p.participant_id.split('-')[1])
                    participant_ids.append(num)
                except:
                    continue
        
        # Старые пилоты
        pilots = Pilot.query.all()
        for p in pilots:
            if p.pilot_id and p.pilot_id.startswith('UAV-'):
                try:
                    num = int(p.pilot_id.split('-')[1])
                    participant_ids.append(num)
                except:
                    continue
        
        # Находим следующий доступный номер
        if participant_ids:
            next_number = max(participant_ids) + 1
        else:
            next_number = 1
            
    except Exception as e:
        print(f"Ошибка при генерации ID: {e}")
        # Если ошибка, начинаем с 1
        next_number = 1
        
    return f"UAV-{next_number:04d}"

# Для обратной совместимости
def generate_next_pilot_id():
    return generate_next_participant_id()

# Новые константы для категорий и подкатегорий
CATEGORIES = {
    'military': {
        'name': 'MILITARY',
        'emoji': '🔴',
        'color': '#FF6B6B',
        'subcategories': {
            'pilot_reconnaissance': 'військові пілоти - розвідувальні',
            'pilot_strike': 'військові пілоти - ударні',
            'pilot_interceptor': 'військові пілоти - перехоплювачі',
            'instructor': 'військові інструктори',
            'engineer': 'військові техніки-інженери',
            'operator': 'військові оператори/штурмани',
            'federation_team': 'команда федерації'
        }
    },
    'civil': {
        'name': 'CIVIL',
        'emoji': '🔵',
        'color': '#4A90E2',
        'subcategories': {
            'pilot': 'цивільні пілоти',
            'pilot_interceptor': 'цивільні пілоти - перехоплювачі',
            'instructor': 'цивільні інструктори',
            'engineer': 'цивільні інженери-розробники',
            'student': 'студенти/курсанти',
            'federation_team': 'команда федерації'
        }
    },
    'deftech': {
        'name': 'DEFTECH',
        'emoji': '🟢',
        'color': '#00D4AA',
        'subcategories': {
            'manufacturer': 'виробники обладнання',
            'drone_manufacturer': 'виробник БПЛА',
            'developer': 'розробники софту та систем управління',
            'rd_lab': 'R&D лабораторії',
            'integrator': 'інтегратори та сервісні компанії',
            'federation_team': 'команда федерації'
        }
    },
    'donor_partner': {
        'name': 'DONOR / PARTNER',
        'emoji': '🟡',
        'color': '#F5A623',
        'subcategories': {
            'partner': 'партнери',
            'donor': 'меценати',
            'volunteer': 'волонтери',
            'organization': 'організації (державні, обласні та районні органи влади, міжнародні структури)',
            'federation_team': 'команда федерації'
        }
    },
    'media_education': {
        'name': 'MEDIA / EDUCATION',
        'emoji': '🟣',
        'color': '#9B59B6',
        'subcategories': {
            'media_officer': 'медіа-офіцери, SMM',
            'journalist': 'журналісти-партнери',
            'educator': 'освітні заклади, викладачі',
            'researcher': 'дослідники та аналітики',
            'federation_team': 'команда федерації'
        }
    }
}

# Новая модель участников
class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.String(20), unique=True, nullable=False)  # UAV-0001 формат
    callsign = db.Column(db.String(100), nullable=False, unique=True)
    photo_url = db.Column(db.String(200), default='default-pilot.svg')
    category = db.Column(db.String(50), nullable=False)  # 'military', 'civil', etc.
    subcategory = db.Column(db.String(100), nullable=False)  # конкретная подкатегория
    join_date = db.Column(db.DateTime, default=datetime.now)
    points = db.Column(db.Integer, default=0)
    qr_code = db.Column(db.String(100), unique=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # Статус активации ID карты
    
    def __repr__(self):
        return f'<Participant {self.callsign}>'
    
    def get_category_info(self):
        """Возвращает информацию о категории"""
        return CATEGORIES.get(self.category, {})
    
    def get_subcategory_name(self):
        """Возвращает название подкатегории"""
        category_info = self.get_category_info()
        subcategories = category_info.get('subcategories', {})
        return subcategories.get(self.subcategory, self.subcategory)
    
    def is_pilot(self):
        """Проверяет, является ли участник пилотом (для системы очков и публичного рейтинга)"""
        return (self.category == 'military' and 
                self.subcategory in ['pilot_strike', 'pilot_reconnaissance']) or \
               (self.category == 'civil' and 
                self.subcategory == 'pilot')
    
    def get_pilot_category(self):
        """Возвращает категорию пилота для совместимости"""
        if self.subcategory == 'pilot_strike':
            return 'strike'
        elif self.subcategory == 'pilot_reconnaissance':
            return 'reconnaissance'
        return None

# Старая модель для обратной совместимости (будет удалена после миграции)
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
    # Для новых участников
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=True)
    # Для старых пилотов (обратная совместимость)
    pilot_id = db.Column(db.Integer, db.ForeignKey('pilot.id'), nullable=True)
    description = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    date_awarded = db.Column(db.DateTime, default=datetime.now)
    
    participant = db.relationship('Participant', backref=db.backref('achievements', lazy=True))
    pilot = db.relationship('Pilot', backref=db.backref('achievements', lazy=True))
    
    def get_owner(self):
        """Возвращает владельца достижения (участника или пилота)"""
        return self.participant or self.pilot

# Новая модель для логирования активности админки
class AdminActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(50), nullable=False)  # 'add_participant', 'delete_participant', 'edit_participant', 'add_achievement'
    # Для новых участников
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=True)
    participant_name = db.Column(db.String(100), nullable=True)
    # Для старых пилотов (обратная совместимость)
    pilot_id = db.Column(db.Integer, db.ForeignKey('pilot.id'), nullable=True)
    pilot_name = db.Column(db.String(100), nullable=True)  # Сохраняем имя на случай удаления пилота
    description = db.Column(db.String(300), nullable=False)
    points_awarded = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
    participant = db.relationship('Participant', backref=db.backref('activity_logs', lazy=True))
    pilot = db.relationship('Pilot', backref=db.backref('activity_logs', lazy=True))
    
    def get_owner(self):
        """Возвращает владельца лога (участника или пилота)"""
        return self.participant or self.pilot
    
    def get_owner_name(self):
        """Возвращает имя владельца лога"""
        return self.participant_name or self.pilot_name

# Функция для логирования активности админки
def log_admin_activity(action_type, participant=None, pilot=None, description=None, points_awarded=None):
    # Приоритет отдаем participant
    if participant:
        participant_name = participant.callsign
        participant_id = participant.id
        pilot_name = None
        pilot_id = None
    elif pilot:
        participant_name = None
        participant_id = None
        pilot_name = pilot.callsign
        pilot_id = pilot.id
    else:
        participant_name = None
        participant_id = None
        pilot_name = None
        pilot_id = None
    
    log = AdminActivityLog(
        action_type=action_type,
        participant_id=participant_id,
        participant_name=participant_name,
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

@app.route('/support')
def support():
    return render_template('support.html')

@app.route('/rating')
def rating():
    # Получаем только пилотов (для публичного рейтинга)
    # Новые участники-пилоты (приоритет) - включаем военных и гражданских
    new_strike_pilots = Participant.query.filter_by(category='military', subcategory='pilot_strike').order_by(Participant.points.desc()).all()
    new_recon_pilots = Participant.query.filter_by(category='military', subcategory='pilot_reconnaissance').order_by(Participant.points.desc()).all()
    
    # Добавляем гражданских пилотов (они считаются как ударные для рейтинга)
    civil_pilots = Participant.query.filter_by(category='civil', subcategory='pilot').order_by(Participant.points.desc()).all()
    new_strike_pilots.extend(civil_pilots)
    
    # Получаем QR коды новых участников для исключения дубликатов
    migrated_qr_codes = set()
    for pilot in new_strike_pilots + new_recon_pilots:
        if pilot.qr_code:
            migrated_qr_codes.add(pilot.qr_code)
    
    # Старые пилоты (только те, которые не были мигрированы)
    old_strike_pilots = [p for p in Pilot.query.filter_by(category='strike').order_by(Pilot.points.desc()).all() 
                        if p.qr_code not in migrated_qr_codes]
    old_recon_pilots = [p for p in Pilot.query.filter_by(category='reconnaissance').order_by(Pilot.points.desc()).all() 
                       if p.qr_code not in migrated_qr_codes]
    
    # Объединяем списки и сортируем каждый по очкам
    strike_pilots = list(new_strike_pilots) + list(old_strike_pilots)
    strike_pilots.sort(key=lambda x: x.points, reverse=True)
    
    recon_pilots = list(new_recon_pilots) + list(old_recon_pilots)
    recon_pilots.sort(key=lambda x: x.points, reverse=True)
    
    all_pilots = strike_pilots + recon_pilots
    
    # Сортируем общий список по очкам
    all_pilots.sort(key=lambda x: x.points, reverse=True)
    
    return render_template('rating.html', 
                         all_pilots=all_pilots,
                         strike_pilots=strike_pilots,
                         recon_pilots=recon_pilots)

@app.route('/pilot/<string:qr_code>')
def pilot_profile(qr_code):
    # Пробуем найти среди новых участников
    participant = Participant.query.filter_by(qr_code=qr_code).first()
    if participant:
        achievements = Achievement.query.filter_by(participant_id=participant.id).order_by(Achievement.date_awarded.desc()).all()
        
        # Для участников - получаем только пилотов для рейтинга
        all_strike_pilots = Participant.query.filter_by(category='military', subcategory='pilot_strike').order_by(Participant.points.desc()).all()
        all_recon_pilots = Participant.query.filter_by(category='military', subcategory='pilot_reconnaissance').order_by(Participant.points.desc()).all()
        
        # Добавляем старых пилотов для совместимости
        old_strike_pilots = Pilot.query.filter_by(category='strike').order_by(Pilot.points.desc()).all()
        old_recon_pilots = Pilot.query.filter_by(category='reconnaissance').order_by(Pilot.points.desc()).all()
        
        all_strike_pilots.extend(old_strike_pilots)
        all_recon_pilots.extend(old_recon_pilots)
        
        # Подсчитываем дни в федерации
        days_in_federation = (datetime.now() - participant.join_date).days
        
        return render_template('pilot_profile.html', 
                             pilot=participant,  # Передаем как pilot для совместимости шаблона
                             achievements=achievements,
                             all_strike_pilots=all_strike_pilots,
                             all_recon_pilots=all_recon_pilots,
                             days_in_federation=days_in_federation)
    
    # Если не найден среди участников, ищем среди старых пилотов
    pilot = Pilot.query.filter_by(qr_code=qr_code).first_or_404()
    
    achievements = Achievement.query.filter_by(pilot_id=pilot.id).order_by(Achievement.date_awarded.desc()).all()
    
    # Получаем списки для определения места в категории
    all_strike_pilots = Pilot.query.filter_by(category='strike').order_by(Pilot.points.desc()).all()
    all_recon_pilots = Pilot.query.filter_by(category='reconnaissance').order_by(Pilot.points.desc()).all()
    
    # Добавляем новых участников-пилотов
    new_strike_pilots = Participant.query.filter_by(category='military', subcategory='pilot_strike').order_by(Participant.points.desc()).all()
    new_recon_pilots = Participant.query.filter_by(category='military', subcategory='pilot_reconnaissance').order_by(Participant.points.desc()).all()
    
    all_strike_pilots.extend(new_strike_pilots)
    all_recon_pilots.extend(new_recon_pilots)
    
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
    
    # Получаем статистику участников
    total_participants = Participant.query.count()
    total_pilots_old = Pilot.query.count()  # Старые пилоты
    total_all = total_participants + total_pilots_old
    
    # Статистика активации карт (только для новых участников)
    active_cards = Participant.query.filter_by(is_active=True).count()
    inactive_cards = Participant.query.filter_by(is_active=False).count()
    
    # Статистика по категориям новых участников
    military_count = Participant.query.filter_by(category='military').count()
    civil_count = Participant.query.filter_by(category='civil').count()
    deftech_count = Participant.query.filter_by(category='deftech').count()
    donor_partner_count = Participant.query.filter_by(category='donor_partner').count()
    media_education_count = Participant.query.filter_by(category='media_education').count()
    
    # Статистика пилотов (для совместимости)
    strike_pilots_old = Pilot.query.filter_by(category='strike').count()
    recon_pilots_old = Pilot.query.filter_by(category='reconnaissance').count()
    strike_pilots_new = Participant.query.filter_by(category='military', subcategory='pilot_strike').count()
    recon_pilots_new = Participant.query.filter_by(category='military', subcategory='pilot_reconnaissance').count()
    
    total_strike_pilots = strike_pilots_old + strike_pilots_new
    total_recon_pilots = recon_pilots_old + recon_pilots_new
    
    # Получаем всех участников для отображения
    all_participants = Participant.query.order_by(Participant.points.desc()).all()
    all_pilots_old = Pilot.query.order_by(Pilot.points.desc()).all()
    
    # Объединяем для отображения (приоритет новым участникам)
    all_members = list(all_participants) + list(all_pilots_old)
    
    # Получаем всех участников для поиска и преобразуем в словари
    all_members_data = []
    
    # Новые участники
    for participant in all_participants:
        member_data = {
            'id': participant.id,
            'participant_id': participant.participant_id,
            'callsign': participant.callsign,
            'category': participant.category,
            'subcategory': participant.subcategory,
            'points': participant.points,
            'photo_url': participant.photo_url,
            'join_date': participant.join_date.strftime('%d.%m.%Y'),
            'achievements': [{'description': ach.description, 'points': ach.points} for ach in participant.achievements],
            'type': 'participant'
        }
        all_members_data.append(member_data)
    
    # Старые пилоты
    for pilot in all_pilots_old:
        member_data = {
            'id': pilot.id,
            'pilot_id': pilot.pilot_id,
            'callsign': pilot.callsign,
            'category': pilot.category,
            'subcategory': None,
            'points': pilot.points,
            'photo_url': pilot.photo_url,
            'join_date': pilot.join_date.strftime('%d.%m.%Y'),
            'achievements': [{'description': ach.description, 'points': ach.points} for ach in pilot.achievements],
            'type': 'pilot'
        }
        all_members_data.append(member_data)
    
    # Получаем последние 20 записей активности
    activity_logs = AdminActivityLog.query.order_by(AdminActivityLog.timestamp.desc()).limit(20).all()
    
    return render_template('admin_dashboard.html', 
                         participants=all_participants,
                         pilots=all_pilots_old,  # Для обратной совместимости
                         all_members=all_members_data,
                         total_all=total_all,
                         total_participants=total_participants,
                         total_pilots_old=total_pilots_old,
                         active_cards=active_cards,
                         inactive_cards=inactive_cards,
                         military_count=military_count,
                         civil_count=civil_count,
                         deftech_count=deftech_count,
                         donor_partner_count=donor_partner_count,
                         media_education_count=media_education_count,
                         total_strike_pilots=total_strike_pilots,
                         total_recon_pilots=total_recon_pilots,
                         categories=CATEGORIES,
                         activity_logs=activity_logs)

@app.route('/admin/participant/add', methods=['GET', 'POST'])
@admin_required
def admin_add_participant():
    
    if request.method == 'POST':
        callsign = request.form['callsign']
        category = request.form['category']
        subcategory = request.form['subcategory']
        photo_url = request.form.get('photo_url', 'default-pilot.svg')
        custom_id = request.form.get('custom_id', '').strip()
        
        # Проверяем кастомный ID или генерируем автоматически
        if custom_id:
            # Валидируем формат
            import re
            if not re.match(r'^UAV-\d{4}$', custom_id):
                flash('Неправильний формат ID! Використовуйте формат UAV-XXXX (наприклад, UAV-0012)', 'error')
                return render_template('admin_add_participant.html', categories=CATEGORIES)
            
            # Проверяем уникальность
            existing_participant = Participant.query.filter_by(participant_id=custom_id).first()
            existing_pilot = Pilot.query.filter_by(pilot_id=custom_id).first()
            
            if existing_participant or existing_pilot:
                flash(f'ID {custom_id} вже зайнятий! Оберіть інший номер або залишіть поле порожнім для автогенерації.', 'error')
                return render_template('admin_add_participant.html', categories=CATEGORIES)
            
            participant_id = custom_id
        else:
            # Автогенерация ID
            participant_id = generate_next_participant_id()
        
        # Генерируем уникальный QR код
        qr_code = str(uuid.uuid4())
        
        participant = Participant(
            participant_id=participant_id,
            callsign=callsign,
            category=category,
            subcategory=subcategory,
            photo_url=photo_url,
            qr_code=qr_code
        )
        
        try:
            db.session.add(participant)
            db.session.commit()
            
            # Сохраняем QR код в файл
            save_participant_qr_code(participant)
            
            # Логируем активность
            category_info = CATEGORIES.get(category, {})
            subcategory_name = category_info.get('subcategories', {}).get(subcategory, subcategory)
            
            id_method = "вручну" if custom_id else "автоматично"
            log_admin_activity(
                action_type='add_participant',
                participant=participant,
                description=f'Додано нового учасника {callsign} ({participant_id}, ID призначено {id_method}) в категорії {category_info.get("name", category)} - {subcategory_name}'
            )
            
            flash(f'Учасник {callsign} (ID: {participant_id}) успішно додано')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при додаванні учасника: {str(e)}', 'error')
            return render_template('admin_add_participant.html', categories=CATEGORIES)
    
    return render_template('admin_add_participant.html', categories=CATEGORIES)

@app.route('/admin/check_participant_id')
@admin_required
def check_participant_id():
    """AJAX эндпоинт для проверки доступности ID участника"""
    participant_id = request.args.get('id', '').strip()
    
    if not participant_id:
        return jsonify({'available': True, 'message': ''})
    
    # Валидируем формат
    import re
    if not re.match(r'^UAV-\d{4}$', participant_id):
        return jsonify({'available': False, 'message': 'Неправильний формат! Використовуйте формат UAV-XXXX'})
    
    # Проверяем уникальность
    existing_participant = Participant.query.filter_by(participant_id=participant_id).first()
    existing_pilot = Pilot.query.filter_by(pilot_id=participant_id).first()
    
    if existing_participant or existing_pilot:
        owner_name = existing_participant.callsign if existing_participant else existing_pilot.callsign
        return jsonify({'available': False, 'message': f'ID {participant_id} вже зайнятий учасником "{owner_name}"'})
    
    return jsonify({'available': True, 'message': f'ID {participant_id} доступний'})

@app.route('/admin/participant/<int:participant_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_participant(participant_id):
    
    participant = Participant.query.get_or_404(participant_id)
    
    if request.method == 'POST':
        old_callsign = participant.callsign
        old_category = participant.category
        old_subcategory = participant.subcategory
        old_is_active = participant.is_active
        
        participant.callsign = request.form['callsign']
        participant.category = request.form['category']
        participant.subcategory = request.form['subcategory']
        participant.photo_url = request.form.get('photo_url', participant.photo_url)
        participant.is_active = 'is_active' in request.form  # Checkbox value
        
        db.session.commit()
        
        # Логируем активность
        changes = []
        if old_callsign != participant.callsign:
            changes.append(f'позивний: {old_callsign} → {participant.callsign}')
        if old_category != participant.category:
            old_cat_info = CATEGORIES.get(old_category, {})
            new_cat_info = CATEGORIES.get(participant.category, {})
            changes.append(f'категорія: {old_cat_info.get("name", old_category)} → {new_cat_info.get("name", participant.category)}')
        if old_subcategory != participant.subcategory:
            old_subcat = CATEGORIES.get(old_category, {}).get('subcategories', {}).get(old_subcategory, old_subcategory)
            new_subcat = CATEGORIES.get(participant.category, {}).get('subcategories', {}).get(participant.subcategory, participant.subcategory)
            changes.append(f'підкатегорія: {old_subcat} → {new_subcat}')
        if old_is_active != participant.is_active:
            status_text = "активована" if participant.is_active else "деактивована"
            changes.append(f'ID карта: {status_text}')
        
        if changes:
            log_admin_activity(
                action_type='edit_participant',
                participant=participant,
                description=f'Редагування учасника {participant.callsign}: {", ".join(changes)}'
            )
        
        flash(f'Учасник {participant.callsign} успішно оновлено')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_edit_participant.html', participant=participant, categories=CATEGORIES)

@app.route('/admin/participant/<int:participant_id>/delete', methods=['POST'])
@admin_required
def admin_delete_participant(participant_id):
    
    participant = Participant.query.get_or_404(participant_id)
    participant_callsign = participant.callsign
    participant_participant_id = participant.participant_id
    
    # Логируем активность перед удалением
    log_admin_activity(
        action_type='delete_participant',
        participant=participant,
        description=f'Видалено учасника {participant_callsign} ({participant_participant_id})'
    )
    
    # Удаляем связанные достижения
    Achievement.query.filter_by(participant_id=participant_id).delete()
    
    db.session.delete(participant)
    db.session.commit()
    
    flash(f'Учасник {participant_callsign} успішно видалено')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/participant/<int:participant_id>/add_achievement', methods=['POST'])
@admin_required
def admin_add_participant_achievement(participant_id):
    
    participant = Participant.query.get_or_404(participant_id)
    description = request.form['description']
    points = int(request.form.get('points', 0))  # Для не-пилотов может быть 0
    
    achievement = Achievement(
        participant_id=participant_id,
        description=description,
        points=points
    )
    
    # Обновляем общие очки участника только для пилотов
    if participant.is_pilot() and points > 0:
        participant.points += points
    
    db.session.add(achievement)
    db.session.commit()
    
    # Логируем активность
    if points > 0:
        log_admin_activity(
            action_type='add_achievement',
            participant=participant,
            description=f'Нараховано досягнення "{description}" для учасника {participant.callsign}',
            points_awarded=points
        )
    else:
        log_admin_activity(
            action_type='add_achievement',
            participant=participant,
            description=f'Додано досягнення "{description}" для учасника {participant.callsign}'
        )
    
    flash(f'Достижение добавлено для {participant.callsign}')
    return redirect(url_for('admin_dashboard'))



@app.route('/admin/logout')
@admin_required
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))



@app.route('/qr/<string:qr_code>')
def generate_qr(qr_code):
    from flask import send_file
    
    # Пробуем найти среди новых участников
    participant = Participant.query.filter_by(qr_code=qr_code).first()
    if participant:
        # Путь к файлу QR кода - используем существующий qr_code
        qr_filename = f"{participant.participant_id}.png"
        qr_filepath = os.path.join('static', 'qr_codes', qr_filename)
        
        # Проверяем, существует ли файл, если нет - создаем с существующим qr_code
        if not os.path.exists(qr_filepath):
            # Создаем директорию если её нет
            os.makedirs('static/qr_codes', exist_ok=True)
            
            # Создаем QR код с существующим qr_code из БД
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(f'https://ufmup.com/pilot/{participant.qr_code}')
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Сохраняем в файл
            img.save(qr_filepath)
        
        # Возвращаем файл изображения
        return send_file(qr_filepath, mimetype='image/png')
    
    # Если не найден среди участников, ищем среди старых пилотов
    pilot = Pilot.query.filter_by(qr_code=qr_code).first()
    if pilot:
        # Путь к файлу QR кода - используем существующий qr_code
        qr_filename = f"{pilot.pilot_id}.png"
        qr_filepath = os.path.join('static', 'qr_codes', qr_filename)
        
        # Проверяем, существует ли файл, если нет - создаем с существующим qr_code
        if not os.path.exists(qr_filepath):
            # Создаем директорию если её нет
            os.makedirs('static/qr_codes', exist_ok=True)
            
            # Создаем QR код с существующим qr_code из БД
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(f'https://ufmup.com/pilot/{pilot.qr_code}')
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Сохраняем в файл
            img.save(qr_filepath)
        
        # Возвращаем файл изображения
        return send_file(qr_filepath, mimetype='image/png')
    
    # Если не найден ни один участник, возвращаем ошибку 404
    from flask import abort
    abort(404)

# Функция для сохранения QR кода участника
def save_participant_qr_code(participant):
    qr_filename = f"{participant.participant_id}.png"
    qr_filepath = os.path.join('static', 'qr_codes', qr_filename)
    
    # Создаем QR код
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(f'https://ufmup.com/pilot/{participant.qr_code}')  # Ссылка на правильный сайт
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_filepath)
    
    return qr_filename

# Для обратной совместимости
def save_pilot_qr_code(pilot):
    qr_filename = f"{pilot.pilot_id}.png"
    qr_filepath = os.path.join('static', 'qr_codes', qr_filename)
    
    # Создаем QR код
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(f'https://ufmup.com/pilot/{pilot.qr_code}')
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_filepath)
    
    return qr_filename

def ensure_participant_has_qr_code(participant):
    """Гарантирует, что у участника есть QR код. Для существующих участников сохраняет старый QR код."""
    if not participant.qr_code:
        # Генерируем новый UUID только если QR код отсутствует полностью
        participant.qr_code = str(uuid.uuid4())
        db.session.commit()
        print(f"Сгенерирован новый QR код для участника {participant.callsign}: {participant.qr_code}")
    return participant.qr_code

def ensure_pilot_has_qr_code(pilot):
    """Гарантирует, что у пилота есть QR код. Для существующих пилотов сохраняет старый QR код."""
    if not pilot.qr_code:
        # Генерируем новый UUID только если QR код отсутствует полностью
        pilot.qr_code = str(uuid.uuid4())
        db.session.commit()
        print(f"Сгенерирован новый QR код для пилота {pilot.callsign}: {pilot.qr_code}")
    return pilot.qr_code

def migrate_database():
    """Обновляет схему базы данных для новых таблиц"""
    print("Обновляем схему базы данных...")
    
    # Создаем все таблицы (включая новые колонки)
    db.create_all()
    
    # Проверяем и добавляем колонку participant_id в таблицу achievement
    try:
        db.session.execute(db.text("SELECT participant_id FROM achievement LIMIT 1"))
        print("Колонка achievement.participant_id уже существует")
    except Exception:
        print("Добавляем колонку participant_id в таблицу achievement...")
        try:
            db.session.execute(db.text("ALTER TABLE achievement ADD COLUMN participant_id INTEGER"))
            db.session.commit()
            print("Колонка achievement.participant_id успешно добавлена")
        except Exception as e:
            print(f"Ошибка при добавлении колонки achievement.participant_id: {e}")
            db.session.rollback()
    
    # Проверяем и добавляем колонки в таблицу admin_activity_log
    try:
        db.session.execute(db.text("SELECT participant_id FROM admin_activity_log LIMIT 1"))
        print("Колонка admin_activity_log.participant_id уже существует")
    except Exception:
        print("Добавляем колонки participant_id и participant_name в таблицу admin_activity_log...")
        try:
            db.session.execute(db.text("ALTER TABLE admin_activity_log ADD COLUMN participant_id INTEGER"))
            db.session.execute(db.text("ALTER TABLE admin_activity_log ADD COLUMN participant_name VARCHAR(100)"))
            db.session.commit()
            print("Колонки admin_activity_log успешно добавлены")
        except Exception as e:
            print(f"Ошибка при добавлении колонок admin_activity_log: {e}")
            db.session.rollback()
    
    # Проверяем и добавляем колонку is_active в таблицу participant
    try:
        db.session.execute(db.text("SELECT is_active FROM participant LIMIT 1"))
        print("Колонка participant.is_active уже существует")
    except Exception:
        print("Добавляем колонку is_active в таблицу participant...")
        try:
            db.session.execute(db.text("ALTER TABLE participant ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            db.session.commit()
            print("Колонка participant.is_active успешно добавлена")
        except Exception as e:
            print(f"Ошибка при добавлении колонки participant.is_active: {e}")
            db.session.rollback()

def migrate_pilots_to_participants():
    """Мигрирует существующих пилотов в новую систему участников"""
    print("Начинаем миграцию пилотов в участников...")
    
    # Сначала обновляем схему базы данных
    migrate_database()
    
    # Проверяем, существует ли таблица pilot
    try:
        pilots_data = db.session.execute(db.text("""
            SELECT id, pilot_id, callsign, photo_url, category, join_date, points, qr_code 
            FROM pilot
        """)).fetchall()
    except Exception:
        print("Таблица pilot не существует или пуста, пропускаем миграцию")
        return
    
    migrated_count = 0
    
    for pilot_row in pilots_data:
        # Проверяем, не мигрирован ли уже этот пилот
        existing_participant = Participant.query.filter_by(qr_code=pilot_row.qr_code).first()
        if existing_participant:
            print(f"Пилот {pilot_row.callsign} уже мигрирован, пропускаем")
            continue
        
        # Определяем подкатегорию на основе старой категории
        if pilot_row.category == 'strike':
            subcategory = 'pilot_strike'
        elif pilot_row.category == 'reconnaissance':
            subcategory = 'pilot_reconnaissance'
        else:
            print(f"Неизвестная категория пилота {pilot_row.callsign}: {pilot_row.category}")
            continue
        
        # Преобразуем дату из строки в datetime объект если нужно
        join_date = pilot_row.join_date
        if isinstance(join_date, str):
            from datetime import datetime
            try:
                join_date = datetime.fromisoformat(join_date.replace('Z', '+00:00'))
            except:
                join_date = datetime.now()
        
        # Создаем нового участника
        participant = Participant(
            participant_id=pilot_row.pilot_id,
            callsign=pilot_row.callsign,
            photo_url=pilot_row.photo_url,
            category='military',  # Все пилоты попадают в военную категорию
            subcategory=subcategory,
            join_date=join_date,
            points=pilot_row.points,
            qr_code=pilot_row.qr_code
        )
        
        db.session.add(participant)
        db.session.flush()  # Получаем ID нового участника
        
        # Мигрируем достижения через прямой SQL
        achievements_data = db.session.execute(db.text("""
            SELECT id, description, points, date_awarded 
            FROM achievement 
            WHERE pilot_id = :pilot_id
        """), {"pilot_id": pilot_row.id}).fetchall()
        
        for achievement_row in achievements_data:
            # Преобразуем дату достижения если нужно
            date_awarded = achievement_row.date_awarded
            if isinstance(date_awarded, str):
                try:
                    date_awarded = datetime.fromisoformat(date_awarded.replace('Z', '+00:00'))
                except:
                    date_awarded = datetime.now()
            
            new_achievement = Achievement(
                participant_id=participant.id,
                description=achievement_row.description,
                points=achievement_row.points,
                date_awarded=date_awarded
            )
            db.session.add(new_achievement)
        
        migrated_count += 1
        print(f"Мигрирован пилот: {pilot_row.callsign} -> {participant.category}/{participant.subcategory}")
    
    if migrated_count > 0:
        db.session.commit()
        print(f"Миграция завершена! Мигрировано {migrated_count} пилотов")
    else:
        print("Нет пилотов для миграции")

if __name__ == '__main__':
    # Создаем необходимые директории
    os.makedirs('/tmp', exist_ok=True)
    os.makedirs('static/qr_codes', exist_ok=True)
    
    with app.app_context():
        db.create_all()
        
        # Выполняем миграцию существующих пилотов
        migrate_pilots_to_participants()
        
        # Создаем тестовых участников, если их нет
        if Pilot.query.count() == 0 and Participant.query.count() == 0:
            test_participants = [
                {
                    'participant_id': 'UAV-0001',
                    'callsign': 'Орел',
                    'category': 'military',
                    'subcategory': 'pilot_strike',
                    'photo_url': 'default-pilot.svg',
                    'points': 1250,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'participant_id': 'UAV-0002',
                    'callsign': 'Сокол',
                    'category': 'military',
                    'subcategory': 'pilot_reconnaissance',
                    'photo_url': 'default-pilot.svg',
                    'points': 980,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'participant_id': 'UAV-0003',
                    'callsign': 'Беркут',
                    'category': 'military',
                    'subcategory': 'pilot_strike',
                    'photo_url': 'default-pilot.svg',
                    'points': 1400,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'participant_id': 'UAV-0004',
                    'callsign': 'Ястреб',
                    'category': 'military',
                    'subcategory': 'pilot_reconnaissance',
                    'photo_url': 'default-pilot.svg',
                    'points': 1120,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'participant_id': 'UAV-0005',
                    'callsign': 'Інженер-01',
                    'category': 'deftech',
                    'subcategory': 'developer',
                    'photo_url': 'default-pilot.svg',
                    'points': 850,
                    'qr_code': str(uuid.uuid4())
                },
                {
                    'participant_id': 'UAV-0006',
                    'callsign': 'Цивіл-01',
                    'category': 'civil',
                    'subcategory': 'instructor',
                    'photo_url': 'default-pilot.svg',
                    'points': 650,
                    'qr_code': str(uuid.uuid4())
                }
            ]
            
            for participant_data in test_participants:
                participant = Participant(**participant_data)
                db.session.add(participant)
            
            db.session.commit()
            
            # Создаем QR коды для всех тестовых участников
            for participant in Participant.query.all():
                save_participant_qr_code(participant)
            
            print("Тестовые участники созданы с QR кодами")
    
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)
