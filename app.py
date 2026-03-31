from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime, timedelta
import os
import sys

# ── Rutas correctas tanto en script como en .exe compilado ─────────────────
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)          # carpeta del .exe
    _BUNDLE = sys._MEIPASS                            # carpeta temporal de PyInstaller
    app = Flask(__name__,
                template_folder=os.path.join(_BUNDLE, 'templates'),
                static_folder=os.path.join(_BUNDLE, 'static'),
                instance_path=os.path.join(_BASE, 'instance'))
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, instance_path=os.path.join(_BASE, 'instance'))

os.makedirs(app.instance_path, exist_ok=True)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'obras-asistencias-2026-kos')

_DATABASE_URL = os.environ.get('DATABASE_URL')
if _DATABASE_URL:
    if _DATABASE_URL.startswith('postgres://'):
        _DATABASE_URL = _DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = _DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        'sqlite:///' + os.path.join(app.instance_path, 'asistencias.db')
    )

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ─── MODELS ────────────────────────────────────────────────────────────────────

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.String(200))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    workers = db.relationship('Worker', backref='project', lazy=True)


WORK_TYPES = ['asistencia', 'destajo', 'fijo']
TRADES = ['Obra Civil', 'Fierro', 'Pintura', 'Electricidad', 'Maquinista',
          'Suministro', 'Almacen', 'Control Obra', 'Dirección', 'Contratista', 'Otro']
POSITIONS = {
    'Obra Civil': ['Cabo O.C.', '1/2 Cabo O.C.', 'Oficial O.C.', '1/2 Oficial O.C.', 'Ayudante O.C.'],
    'Fierro': ['Cabo F', '1/2 Cabo F', 'Oficial F', '1/2 Oficial F', 'Ayudante F'],
    'Pintura': ['Cabo P', '1/2 Cabo P', 'Oficial P', '1/2 Oficial P', 'Ayudante P'],
    'Electricidad': ['Cabo E', 'Oficial E', 'Ayudante E'],
    'Maquinista': ['Cabo M', 'Operador'],
    'Suministro': ['Ayudante S'],
    'Almacen': ['Almacen'],
    'Control Obra': ['Residente', 'Supervisor'],
    'Dirección': ['Director', 'Residente'],
    'Contratista': ['Contratista'],
    'Otro': ['Otro'],
}
LEVELS = ['T1-26', 'T2-26', 'T3-26', 'T1-25', 'T1-24', 'T2-24', 'T3-24', 'T1-23', 'T2-23', 'T3-23']


class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    trade = db.Column(db.String(50))         # Actividad
    position = db.Column(db.String(50))      # Puesto
    level = db.Column(db.String(20))         # Nivel tabulador
    work_type = db.Column(db.String(20), default='asistencia')  # asistencia/destajo/fijo
    fixed_weekly = db.Column(db.Float, default=0)   # sueldo fijo semanal si work_type=fijo
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    team = db.Column(db.String(50))          # Equipo/cuadrilla
    bank_name = db.Column(db.String(50))
    bank_account = db.Column(db.String(30))
    clabe = db.Column(db.String(20))
    imss_enrolled = db.Column(db.Boolean, default=False)   # en nómina IMSS/Santander
    imss_weekly_amount = db.Column(db.Float, default=2330.59)
    pay_frequency = db.Column(db.String(20), default='semanal')  # semanal/quincenal/mensual
    active = db.Column(db.Boolean, default=True)
    hire_date = db.Column(db.Date)
    termination_date = db.Column(db.Date)
    notes = db.Column(db.String(300))
    attendances = db.relationship('Attendance', backref='worker', lazy=True)
    payrolls = db.relationship('Payroll', backref='worker', lazy=True)


class PayScale(db.Model):
    """Tabulador de sueldos semanales"""
    id = db.Column(db.Integer, primary_key=True)
    trade = db.Column(db.String(50), nullable=False)
    position = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), nullable=False)
    weekly_rate = db.Column(db.Float, default=0)


class AttendanceWeek(db.Model):
    """Encabezado de semana de asistencia"""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    week_start = db.Column(db.Date, nullable=False)   # Sábado
    week_end = db.Column(db.Date, nullable=False)     # Viernes
    week_num = db.Column(db.Integer)
    year = db.Column(db.Integer)
    locked = db.Column(db.Boolean, default=False)
    project = db.relationship('Project', backref='weeks')
    attendances = db.relationship('Attendance', backref='week', lazy=True)
    payrolls = db.relationship('Payroll', backref='week', lazy=True)
    __table_args__ = (db.UniqueConstraint('project_id', 'week_start'),)

    @property
    def label(self):
        return f"[{self.project.code}] Sem.{self.week_num} {self.week_start.strftime('%d %b')}–{self.week_end.strftime('%d %b %Y')}"


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey('attendance_week.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    sat = db.Column(db.Boolean, default=False)
    mon = db.Column(db.Boolean, default=False)
    tue = db.Column(db.Boolean, default=False)
    wed = db.Column(db.Boolean, default=False)
    thu = db.Column(db.Boolean, default=False)
    fri = db.Column(db.Boolean, default=False)
    days_total = db.Column(db.Float, default=0)
    notes = db.Column(db.String(200))
    __table_args__ = (db.UniqueConstraint('week_id', 'worker_id'),)


class Payroll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey('attendance_week.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    attendance_days = db.Column(db.Float, default=0)   # Col K
    bonus_days = db.Column(db.Float, default=0)        # Col L
    attendance_pay = db.Column(db.Float, default=0)    # Col M
    bonus_pay = db.Column(db.Float, default=0)         # Col N
    extra_pay = db.Column(db.Float, default=0)         # Col O (destajo / ajustes)
    extra_reason = db.Column(db.String(200))           # Col S
    total_pay = db.Column(db.Float, default=0)         # Col P
    bank_pay = db.Column(db.Float, default=0)          # Col Q
    cash_pay = db.Column(db.Float, default=0)          # Col R
    fixed_pay = db.Column(db.Float, default=0)         # sueldo fijo
    notes = db.Column(db.String(300))
    __table_args__ = (db.UniqueConstraint('week_id', 'worker_id'),)


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def get_week_start(d=None):
    """Returns the Saturday that starts the current (or given date's) work week."""
    if d is None:
        d = date.today()
    # Find most recent Saturday (weekday 5)
    days_since_sat = (d.weekday() - 5) % 7
    return d - timedelta(days=days_since_sat)


def get_weekly_rate(worker):
    """Look up the tabulador rate for a worker."""
    if worker.work_type != 'asistencia':
        return 0
    scale = PayScale.query.filter_by(
        trade=worker.trade,
        position=worker.position,
        level=worker.level
    ).first()
    return scale.weekly_rate if scale else 0


def calc_attendance_pay(worker, days):
    rate = get_weekly_rate(worker)
    if rate and days:
        return round(rate * days / 6, 2)
    return 0


def recalc_payroll(payroll):
    worker = payroll.worker
    if worker.work_type == 'asistencia':
        payroll.attendance_pay = calc_attendance_pay(worker, payroll.attendance_days)
        payroll.fixed_pay = 0
    elif worker.work_type == 'fijo':
        payroll.attendance_pay = 0
        payroll.fixed_pay = (worker.fixed_weekly or 0) if (payroll.attendance_days or 0) > 0 else 0
    else:  # destajo
        payroll.attendance_pay = 0
        payroll.fixed_pay = 0
    payroll.total_pay = payroll.attendance_pay + payroll.bonus_pay + payroll.extra_pay + payroll.fixed_pay
    if payroll.bank_pay + payroll.cash_pay != payroll.total_pay:
        payroll.cash_pay = max(0.0, payroll.total_pay - payroll.bank_pay)


# ─── ROUTES ────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    projects = Project.query.filter_by(active=True).all()
    today = date.today()
    week_start = get_week_start(today)
    recent_weeks = AttendanceWeek.query.order_by(AttendanceWeek.week_start.desc()).limit(10).all()
    stats = {}
    for p in projects:
        worker_count = Worker.query.filter_by(project_id=p.id, active=True).count()
        current_week = AttendanceWeek.query.filter_by(
            project_id=p.id, week_start=week_start).first()
        stats[p.id] = {
            'workers': worker_count,
            'has_attendance': current_week is not None,
            'week_id': current_week.id if current_week else None,
        }
    week_end = week_start + timedelta(days=6)
    return render_template('dashboard.html', projects=projects, stats=stats,
                           week_start=week_start, week_end=week_end, today=today)


# ── PROJECTS ──────────────────────────────────────────────────────────────────

@app.route('/proyectos', methods=['GET', 'POST'])
def projects():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            p = Project(
                name=request.form['name'],
                code=request.form['code'].upper(),
                description=request.form.get('description', '')
            )
            db.session.add(p)
            db.session.commit()
            flash(f'Proyecto {p.name} creado.', 'success')
        elif action == 'toggle':
            p = Project.query.get_or_404(request.form['id'])
            p.active = not p.active
            db.session.commit()
            flash(f'Proyecto {p.name} {"activado" if p.active else "desactivado"}.', 'info')
        return redirect(url_for('projects'))
    all_projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template('projects.html', projects=all_projects)


@app.route('/proyectos/<int:pid>/edit', methods=['GET', 'POST'])
def edit_project(pid):
    p = Project.query.get_or_404(pid)
    if request.method == 'POST':
        p.name = request.form['name']
        p.code = request.form['code'].upper()
        p.description = request.form.get('description', '')
        db.session.commit()
        flash('Proyecto actualizado.', 'success')
        return redirect(url_for('projects'))
    return render_template('project_form.html', project=p)


# ── WORKERS ───────────────────────────────────────────────────────────────────

@app.route('/trabajadores')
def workers():
    project_id = request.args.get('proyecto', type=int)
    show_inactive = request.args.get('inactivos', '0') == '1'
    query = Worker.query
    if project_id:
        query = query.filter_by(project_id=project_id)
    if not show_inactive:
        query = query.filter_by(active=True)
    all_workers = query.order_by(Worker.project_id, Worker.trade, Worker.name).all()
    projects = Project.query.filter_by(active=True).all()
    return render_template('workers.html', workers=all_workers, projects=projects,
                           selected_project=project_id, show_inactive=show_inactive)


@app.route('/trabajadores/nuevo', methods=['GET', 'POST'])
def new_worker():
    projects = Project.query.filter_by(active=True).all()
    if request.method == 'POST':
        hire_date = None
        if request.form.get('hire_date'):
            hire_date = datetime.strptime(request.form['hire_date'], '%Y-%m-%d').date()
        w = Worker(
            name=request.form['name'],
            trade=request.form.get('trade'),
            position=request.form.get('position'),
            level=request.form.get('level'),
            work_type=request.form.get('work_type', 'asistencia'),
            fixed_weekly=float(request.form.get('fixed_weekly') or 0),
            project_id=int(request.form['project_id']),
            team=request.form.get('team', ''),
            bank_name=request.form.get('bank_name', ''),
            bank_account=request.form.get('bank_account', ''),
            clabe=request.form.get('clabe', ''),
            imss_enrolled='imss_enrolled' in request.form,
            imss_weekly_amount=float(request.form.get('imss_weekly_amount') or 2330.59),
            hire_date=hire_date,
            notes=request.form.get('notes', ''),
        )
        db.session.add(w)
        db.session.commit()
        flash(f'Trabajador {w.name} dado de alta.', 'success')
        next_url = request.form.get('next', url_for('workers'))
        return redirect(next_url)
    preselect = request.args.get('proyecto', type=int)
    return render_template('worker_form.html', worker=None, projects=projects,
                           trades=TRADES, positions=POSITIONS, levels=LEVELS,
                           work_types=WORK_TYPES, preselect=preselect)


@app.route('/trabajadores/<int:wid>/editar', methods=['GET', 'POST'])
def edit_worker(wid):
    w = Worker.query.get_or_404(wid)
    projects = Project.query.filter_by(active=True).all()
    if request.method == 'POST':
        w.name = request.form['name']
        w.trade = request.form.get('trade')
        w.position = request.form.get('position')
        w.level = request.form.get('level')
        w.work_type = request.form.get('work_type', 'asistencia')
        w.fixed_weekly = float(request.form.get('fixed_weekly') or 0)
        w.project_id = int(request.form['project_id'])
        w.team = request.form.get('team', '')
        w.bank_name = request.form.get('bank_name', '')
        w.bank_account = request.form.get('bank_account', '')
        w.clabe = request.form.get('clabe', '')
        w.imss_enrolled = 'imss_enrolled' in request.form
        w.imss_weekly_amount = float(request.form.get('imss_weekly_amount') or 2330.59)
        if request.form.get('hire_date'):
            w.hire_date = datetime.strptime(request.form['hire_date'], '%Y-%m-%d').date()
        w.notes = request.form.get('notes', '')
        db.session.commit()
        flash('Trabajador actualizado.', 'success')
        return redirect(url_for('workers', proyecto=w.project_id))
    return render_template('worker_form.html', worker=w, projects=projects,
                           trades=TRADES, positions=POSITIONS, levels=LEVELS,
                           work_types=WORK_TYPES, preselect=w.project_id)


@app.route('/trabajadores/<int:wid>/baja', methods=['POST'])
def deactivate_worker(wid):
    w = Worker.query.get_or_404(wid)
    w.active = False
    w.termination_date = date.today()
    db.session.commit()
    flash(f'{w.name} dado de baja.', 'warning')
    return redirect(url_for('workers', proyecto=w.project_id))


@app.route('/trabajadores/<int:wid>/reactivar', methods=['POST'])
def reactivate_worker(wid):
    w = Worker.query.get_or_404(wid)
    w.active = True
    w.termination_date = None
    db.session.commit()
    flash(f'{w.name} reactivado.', 'success')
    return redirect(url_for('workers', proyecto=w.project_id, inactivos=1))


# ── ATTENDANCE ────────────────────────────────────────────────────────────────

@app.route('/asistencias')
def attendance_list():
    projects = Project.query.filter_by(active=True).all()
    project_id = request.args.get('proyecto', type=int)
    weeks = AttendanceWeek.query
    if project_id:
        weeks = weeks.filter_by(project_id=project_id)
    weeks = weeks.order_by(AttendanceWeek.week_start.desc()).limit(20).all()
    return render_template('attendance_list.html', projects=projects,
                           weeks=weeks, selected_project=project_id)


@app.route('/asistencias/<int:pid>/<week_date>', methods=['GET', 'POST'])
def attendance_form(pid, week_date):
    project = Project.query.get_or_404(pid)
    week_start = datetime.strptime(week_date, '%Y-%m-%d').date()
    week_end = week_start + timedelta(days=6)

    # Get or create the week
    aw = AttendanceWeek.query.filter_by(project_id=pid, week_start=week_start).first()
    if not aw:
        aw = AttendanceWeek(
            project_id=pid,
            week_start=week_start,
            week_end=week_end,
            week_num=week_start.isocalendar()[1],
            year=week_start.year,
        )
        db.session.add(aw)
        db.session.commit()

    # Trabajadores activos + dados de baja que trabajaron al menos 1 día esta semana
    baja_con_dias = (
        db.session.query(Worker)
        .join(Attendance, Attendance.worker_id == Worker.id)
        .filter(
            Worker.project_id == pid,
            Worker.active == False,
            Attendance.week_id == aw.id,
            Attendance.days_total > 0,
        ).all()
    )
    baja_ids = {w.id for w in baja_con_dias}
    active_workers = Worker.query.filter_by(project_id=pid, active=True).order_by(
        Worker.trade, Worker.team, Worker.name).all()
    # Merge: activos primero, luego bajas con días (sin duplicar)
    all_week_workers = active_workers + [w for w in baja_con_dias if w.id not in {x.id for x in active_workers}]

    if request.method == 'POST':
        if aw.locked:
            flash('Esta semana está cerrada.', 'danger')
            return redirect(request.url)

        for w in all_week_workers:
            key = str(w.id)
            att = Attendance.query.filter_by(week_id=aw.id, worker_id=w.id).first()
            if not att:
                att = Attendance(week_id=aw.id, worker_id=w.id)
                db.session.add(att)
            att.sat = f'sat_{key}' in request.form
            att.mon = f'mon_{key}' in request.form
            att.tue = f'tue_{key}' in request.form
            att.wed = f'wed_{key}' in request.form
            att.thu = f'thu_{key}' in request.form
            att.fri = f'fri_{key}' in request.form
            att.notes = request.form.get(f'notes_{key}', '')
            att.days_total = sum([att.sat, att.mon, att.tue, att.wed, att.thu, att.fri])

            # Sync payroll attendance days
            pay = Payroll.query.filter_by(week_id=aw.id, worker_id=w.id).first()
            if not pay:
                pay = Payroll(week_id=aw.id, worker_id=w.id)
                db.session.add(pay)
            pay.attendance_days = att.days_total
            recalc_payroll(pay)

        db.session.commit()
        flash('Asistencias guardadas.', 'success')

        if request.form.get('goto_payroll'):
            return redirect(url_for('payroll_detail', pid=pid, week_date=week_date))
        return redirect(request.url)

    # Load existing attendance map
    att_map = {a.worker_id: a for a in aw.attendances}

    workers = all_week_workers  # alias for template

    day_labels = [
        (week_start, 'SAB'),
        (week_start + timedelta(days=2), 'LUN'),
        (week_start + timedelta(days=3), 'MAR'),
        (week_start + timedelta(days=4), 'MIÉ'),
        (week_start + timedelta(days=5), 'JUE'),
        (week_start + timedelta(days=6), 'VIE'),
    ]
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    return render_template('attendance_form.html', project=project, week=aw,
                           workers=workers, att_map=att_map,
                           week_start=week_start, week_end=week_end,
                           day_labels=day_labels, prev_week=prev_week, next_week=next_week)


@app.route('/asistencias/nueva')
def new_attendance():
    """Redirect to attendance form for current week."""
    pid = request.args.get('proyecto', type=int)
    if not pid:
        flash('Selecciona un proyecto.', 'warning')
        return redirect(url_for('attendance_list'))
    week_start = get_week_start()
    return redirect(url_for('attendance_form', pid=pid, week_date=week_start.strftime('%Y-%m-%d')))


# ── PAYROLL ───────────────────────────────────────────────────────────────────

@app.route('/nomina')
def payroll_list():
    projects = Project.query.filter_by(active=True).all()
    project_id = request.args.get('proyecto', type=int)
    weeks = AttendanceWeek.query
    if project_id:
        weeks = weeks.filter_by(project_id=project_id)
    weeks = weeks.order_by(AttendanceWeek.week_start.desc()).limit(20).all()

    week_totals = {}
    for w in weeks:
        pays = Payroll.query.filter_by(week_id=w.id).all()
        week_totals[w.id] = {
            'total': sum(p.total_pay for p in pays),
            'bank': sum(p.bank_pay for p in pays),
            'cash': sum(p.cash_pay for p in pays),
            'count': len(pays),
        }

    return render_template('payroll_list.html', projects=projects,
                           weeks=weeks, week_totals=week_totals,
                           selected_project=project_id)


@app.route('/nomina/<int:pid>/<week_date>', methods=['GET', 'POST'])
def payroll_detail(pid, week_date):
    project = Project.query.get_or_404(pid)
    week_start = datetime.strptime(week_date, '%Y-%m-%d').date()

    aw = AttendanceWeek.query.filter_by(project_id=pid, week_start=week_start).first()
    if not aw:
        flash('No hay asistencias registradas para esa semana.', 'warning')
        return redirect(url_for('payroll_list', proyecto=pid))

    # Activos + bajas con al menos 1 día trabajado esta semana
    baja_con_dias = (
        db.session.query(Worker)
        .join(Attendance, Attendance.worker_id == Worker.id)
        .filter(
            Worker.project_id == pid,
            Worker.active == False,
            Attendance.week_id == aw.id,
            Attendance.days_total > 0,
        ).all()
    )
    active_workers = Worker.query.filter_by(project_id=pid, active=True).order_by(
        Worker.trade, Worker.team, Worker.name).all()
    all_week_workers = active_workers + [w for w in baja_con_dias if w.id not in {x.id for x in active_workers}]

    # Ensure a payroll row exists for every worker visible this week
    for w in all_week_workers:
        # Skip workers hired after this week ended
        if w.hire_date and w.hire_date > aw.week_end:
            continue
        pay = Payroll.query.filter_by(week_id=aw.id, worker_id=w.id).first()
        if not pay:
            att = Attendance.query.filter_by(week_id=aw.id, worker_id=w.id).first()
            pay = Payroll(
                week_id=aw.id,
                worker_id=w.id,
                attendance_days=att.days_total if att else 0,
            )
            db.session.add(pay)
            db.session.flush()
            recalc_payroll(pay)
    db.session.commit()

    if request.method == 'POST':
        if aw.locked:
            flash('Esta semana está cerrada.', 'danger')
            return redirect(request.url)

        for w in all_week_workers:
            pay = Payroll.query.filter_by(week_id=aw.id, worker_id=w.id).first()
            key = str(w.id)
            pay.bonus_pay = float(request.form.get(f'bonus_{key}') or 0)
            pay.extra_pay = float(request.form.get(f'extra_{key}') or 0)
            pay.extra_reason = request.form.get(f'reason_{key}', '')
            pay.bank_pay = float(request.form.get(f'bank_{key}') or 0)

            # For destajo: extra_pay is the destajo amount
            if w.work_type == 'destajo':
                pay.attendance_pay = 0

            recalc_payroll(pay)
            pay.cash_pay = max(0.0, pay.total_pay - pay.bank_pay)

        if request.form.get('lock'):
            aw.locked = True
            flash('Nómina cerrada.', 'info')

        db.session.commit()
        flash('Nómina guardada.', 'success')
        return redirect(request.url)

    workers = all_week_workers  # alias for template
    pay_map = {p.worker_id: p for p in aw.payrolls}
    att_map = {a.worker_id: a for a in aw.attendances}

    totals = {
        'attendance': sum(p.attendance_pay for p in aw.payrolls),
        'bonus': sum(p.bonus_pay for p in aw.payrolls),
        'extra': sum(p.extra_pay for p in aw.payrolls),
        'fixed': sum(p.fixed_pay for p in aw.payrolls),
        'total': sum(p.total_pay for p in aw.payrolls),
        'bank': sum(p.bank_pay for p in aw.payrolls),
        'cash': sum(p.cash_pay for p in aw.payrolls),
    }

    return render_template('payroll_detail.html', project=project, week=aw,
                           workers=workers, pay_map=pay_map, att_map=att_map,
                           totals=totals, week_start=week_start)


# ── NOMIMSS ───────────────────────────────────────────────────────────────────

@app.route('/nomimss')
def nomimss_list():
    projects = Project.query.filter_by(active=True).all()
    project_id = request.args.get('proyecto', type=int)
    weeks = AttendanceWeek.query
    if project_id:
        weeks = weeks.filter_by(project_id=project_id)
    weeks = weeks.order_by(AttendanceWeek.week_start.desc()).limit(20).all()

    week_totals = {}
    for w in weeks:
        imss_workers = Worker.query.filter_by(project_id=w.project_id, imss_enrolled=True).all()
        bank_total = 0
        enrolled_count = 0
        for iw in imss_workers:
            pay = Payroll.query.filter_by(week_id=w.id, worker_id=iw.id).first()
            if pay:
                bank_total += pay.bank_pay
                if pay.bank_pay > 0:
                    enrolled_count += 1
        week_totals[w.id] = {'bank': bank_total, 'count': enrolled_count}

    return render_template('nomimss_list.html', projects=projects, weeks=weeks,
                           week_totals=week_totals, selected_project=project_id)


@app.route('/nomimss/<int:pid>/<week_date>', methods=['GET', 'POST'])
def nomimss_detail(pid, week_date):
    project = Project.query.get_or_404(pid)
    week_start = datetime.strptime(week_date, '%Y-%m-%d').date()

    aw = AttendanceWeek.query.filter_by(project_id=pid, week_start=week_start).first()
    if not aw:
        flash('No existe semana registrada para esa fecha.', 'warning')
        return redirect(url_for('nomimss_list', proyecto=pid))

    imss_workers = Worker.query.filter_by(project_id=pid, imss_enrolled=True).order_by(
        Worker.trade, Worker.team, Worker.name).all()

    if request.method == 'POST':
        for w in imss_workers:
            key = str(w.id)
            pay = Payroll.query.filter_by(week_id=aw.id, worker_id=w.id).first()
            if not pay:
                pay = Payroll(week_id=aw.id, worker_id=w.id)
                db.session.add(pay)
            new_bank = float(request.form.get(f'bank_{key}') or 0)
            pay.bank_pay = new_bank
            pay.cash_pay = max(0.0, pay.total_pay - new_bank)
            # Update imss_weekly_amount on worker too
            w.imss_weekly_amount = new_bank if new_bank > 0 else w.imss_weekly_amount
        db.session.commit()
        flash('NomIMSS guardada.', 'success')
        return redirect(request.url)

    # Ensure payroll rows exist for imss workers
    changed = False
    for w in imss_workers:
        pay = Payroll.query.filter_by(week_id=aw.id, worker_id=w.id).first()
        if not pay:
            att = Attendance.query.filter_by(week_id=aw.id, worker_id=w.id).first()
            pay = Payroll(
                week_id=aw.id, worker_id=w.id,
                attendance_days=att.days_total if att else 0,
                bank_pay=w.imss_weekly_amount,
            )
            db.session.add(pay)
            recalc_payroll(pay)
            changed = True
        elif pay.bank_pay == 0:
            pay.bank_pay = w.imss_weekly_amount
            pay.cash_pay = max(0.0, pay.total_pay - pay.bank_pay)
            changed = True
    if changed:
        db.session.commit()

    pay_map = {p.worker_id: p for p in aw.payrolls}
    total_imss = sum(
        pay_map[w.id].bank_pay if w.id in pay_map else w.imss_weekly_amount
        for w in imss_workers
    )
    discrepancias = [
        w for w in imss_workers
        if w.id in pay_map and abs(pay_map[w.id].bank_pay - w.imss_weekly_amount) > 0.01
    ]

    return render_template('nomimss_detail.html', project=project, week=aw,
                           workers=imss_workers, pay_map=pay_map,
                           total_imss=total_imss, discrepancias=discrepancias,
                           week_start=week_start)


# ── TABULADOR ─────────────────────────────────────────────────────────────────

@app.route('/tabulador', methods=['GET', 'POST'])
def tabulador():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save':
            sid = request.form.get('id')
            if sid:
                ps = PayScale.query.get_or_404(int(sid))
            else:
                ps = PayScale()
                db.session.add(ps)
            ps.trade = request.form['trade']
            ps.position = request.form['position']
            ps.level = request.form['level']
            ps.weekly_rate = float(request.form.get('weekly_rate') or 0)
            db.session.commit()
            flash('Tabulador actualizado.', 'success')
        elif action == 'delete':
            ps = PayScale.query.get_or_404(int(request.form['id']))
            db.session.delete(ps)
            db.session.commit()
            flash('Entrada eliminada.', 'info')
        return redirect(url_for('tabulador'))

    scales = PayScale.query.order_by(PayScale.trade, PayScale.position, PayScale.level).all()
    return render_template('tabulador.html', scales=scales, trades=TRADES,
                           positions=POSITIONS, levels=LEVELS)


# ── API helpers ───────────────────────────────────────────────────────────────

@app.route('/api/positions/<trade>')
def api_positions(trade):
    return jsonify(POSITIONS.get(trade, ['Otro']))


@app.route('/api/rate/<int:wid>')
def api_rate(wid):
    w = Worker.query.get_or_404(wid)
    return jsonify({'rate': get_weekly_rate(w), 'work_type': w.work_type})


# ─── SEED DATA ─────────────────────────────────────────────────────────────────

def seed_tabulador():
    """Pre-load tabulador rates from the Excel."""
    rates = [
        # trade, position, level, weekly_rate
        # ── T1-26 / T2-26 / T3-26 (Punto Calma 2026) ──────────────────────────
        ('Obra Civil', 'Cabo O.C.',       'T1-26', 4300),
        ('Obra Civil', 'Cabo O.C.',       'T2-26', 4100),
        ('Obra Civil', 'Cabo O.C.',       'T3-26', 3700),
        ('Obra Civil', 'Oficial O.C.',    'T1-26', 3100),
        ('Obra Civil', 'Oficial O.C.',    'T2-26', 2700),
        ('Obra Civil', 'Oficial O.C.',    'T3-26', 2500),
        ('Obra Civil', 'Ayudante O.C.',   'T1-26', 2210),
        ('Fierro',     'Cabo F',          'T1-26', 3900),
        ('Fierro',     'Cabo F',          'T2-26', 3700),
        ('Fierro',     'Cabo F',          'T3-26', 3500),
        ('Fierro',     'Oficial F',       'T1-26', 3100),
        ('Fierro',     'Oficial F',       'T2-26', 2700),
        ('Fierro',     'Oficial F',       'T3-26', 2500),
        ('Fierro',     'Ayudante F',      'T1-26', 2210),
        ('Maquinista', 'Cabo M',          'T3-26', 3600),
        ('Pintura',    'Cabo P',          'T1-26', 3900),
        ('Pintura',    'Cabo P',          'T2-26', 3700),
        ('Pintura',    'Cabo P',          'T3-26', 3500),
        ('Pintura',    'Oficial P',       'T1-26', 3300),
        ('Pintura',    'Oficial P',       'T2-26', 2900),
        ('Pintura',    'Oficial P',       'T3-26', 2500),
        ('Pintura',    'Ayudante P',      'T1-26', 2210),
        ('Pintura',    'Ayudante P',      'T2-26', 2000),
        ('Suministro', 'Chofer',          'T1-26', 3000),
        ('Suministro', 'Chofer',          'T2-26', 2750),
        ('Suministro', 'Chofer',          'T3-26', 2500),
        ('Suministro', 'Ayudante S',      'T1-26', 1600),
        ('Suministro', 'Ayudante S',      'T2-26', 1400),
        ('Almacen',    'Almacen',         'T1-26', 3500),
        ('Almacen',    'Almacen',         'T2-26', 2500),
        ('Almacen',    'Almacen',         'T3-26', 2210),
        ('Dirección',  'Director',        'T1-26', 3500),
        ('Dirección',  'Residente',       'T1-26', 2500),
        ('Externo',    'Externo',         'T1-26', 0),
        # ── T1-24 / T2-24 / T3-24 (Santián 2024) ──────────────────────────────
        ('Obra Civil', 'Cabo O.C.',       'T1-24', 3900),
        ('Obra Civil', 'Cabo O.C.',       'T2-24', 3700),
        ('Obra Civil', 'Cabo O.C.',       'T3-24', 3300),
        ('Obra Civil', 'Oficial O.C.',    'T1-24', 3200),
        ('Obra Civil', 'Oficial O.C.',    'T2-24', 2900),
        ('Obra Civil', 'Oficial O.C.',    'T3-24', 2500),
        ('Obra Civil', 'Ayudante O.C.',   'T1-24', 2100),
        ('Obra Civil', 'Ayudante O.C.',   'T2-24', 2000),
        ('Obra Civil', 'Chofer',          'T1-24', 2750),
        ('Dirección',  'Director',        'T1-24', 5000),
        ('Dirección',  'Residente',       'T1-24', 2500),
        ('Electricidad', 'Cabo E',        'T1-24', 3700),
        ('Electricidad', 'Oficial E',     'T1-24', 2900),
        ('Electricidad', 'Oficial E',     'T2-24', 2500),
        ('Electricidad', 'Ayudante E',    'T1-24', 2000),
        ('Fierro',     'Oficial F',       'T1-24', 2900),
        ('Fierro',     'Oficial F',       'T2-24', 2500),
        ('Fierro',     'Ayudante F',      'T1-24', 2000),
        ('Pintura',    'Oficial P',       'T1-24', 2900),
        ('Pintura',    'Oficial P',       'T2-24', 2500),
        ('Pintura',    'Oficial P',       'T3-24', 2200),
        ('Pintura',    'Ayudante P',      'T1-24', 2000),
        ('Suministro', 'Ayudante S',      'T1-24', 1400),
        ('Maquinista', 'Cabo M',          'T3-24', 3300),
    ]
    for trade, position, level, rate in rates:
        exists = PayScale.query.filter_by(trade=trade, position=position, level=level).first()
        if not exists:
            db.session.add(PayScale(trade=trade, position=position, level=level, weekly_rate=rate))
    db.session.commit()


# ─── INIT ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    # Migrate: add new columns to existing DB without losing data
    from sqlalchemy import text, inspect as sa_inspect
    _cols = [c['name'] for c in sa_inspect(db.engine).get_columns('worker')]
    with db.engine.begin() as _conn:
        if 'imss_enrolled' not in _cols:
            _conn.execute(text("ALTER TABLE worker ADD COLUMN imss_enrolled INTEGER DEFAULT 0"))
        if 'imss_weekly_amount' not in _cols:
            _conn.execute(text("ALTER TABLE worker ADD COLUMN imss_weekly_amount REAL DEFAULT 2330.59"))
        if 'pay_frequency' not in _cols:
            _conn.execute(text("ALTER TABLE worker ADD COLUMN pay_frequency VARCHAR(20) DEFAULT 'semanal'"))
    if PayScale.query.count() == 0:
        seed_tabulador()
    if Project.query.count() == 0:
        for p in [
            Project(name='KOS',            code='KOS',   description='Proyecto KOS'),
            Project(name='Administrativo', code='ADMIN', description='Proyecto Administrativo'),
            Project(name='Santián',        code='STN',   description='Proyecto Santián'),
            Project(name='Punto Calma',    code='PTC',   description='Proyecto Punto Calma'),
        ]:
            db.session.add(p)
        db.session.commit()

# ─── ADMIN PAY MODULE ──────────────────────────────────────────────────────

@app.route('/admin/pagos')
def admin_pagos():
    admin_project = Project.query.filter_by(code='ADMIN').first()
    workers = []
    if admin_project:
        workers = Worker.query.filter_by(
            project_id=admin_project.id, active=True
        ).order_by(Worker.name).all()
    return render_template('admin_pagos.html', workers=workers)

@app.route('/admin/pagos/save', methods=['POST'])
def admin_pagos_save():
    for key, value in request.form.items():
        if key.startswith('monto_'):
            worker_id = int(key.split('_')[1])
            w = Worker.query.get(worker_id)
            if w:
                w.fixed_weekly = float(value) if value else 0.0
                w.pay_frequency = request.form.get(f'freq_{worker_id}', 'semanal')
    db.session.commit()
    flash('Configuración de pagos actualizada.', 'success')
    return redirect(url_for('admin_pagos'))


@app.route('/admin/pagos/delete/<int:payroll_id>', methods=['POST'])
def admin_pagos_delete(payroll_id):
    week_id = request.form.get('week_id', type=int)
    project_id = request.form.get('project_id', type=int)
    payroll = Payroll.query.get_or_404(payroll_id)
    db.session.delete(payroll)
    db.session.commit()
    flash('Pago eliminado.', 'warning')
    return redirect(url_for('admin_pagos', week_id=week_id, project_id=project_id or ''))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(debug=False, host='0.0.0.0', port=port)
