"""Run: python import_projects.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import app, db, Project, Worker, PayScale, seed_tabulador

PROJECTS = [
    {'name': 'Santián',     'code': 'STN', 'description': 'Proyecto Santián'},
    {'name': 'Punto Calma', 'code': 'PTC', 'description': 'Proyecto Punto Calma'},
]

WORKERS = {
    'STN': [
        dict(name='Mariana Mendez',               activity='Dirección',  position='Residente',  level='T1-24', work_type='asistencia', imss_enrolled=False),
        dict(name='Juan Manuel Romero Susano',     activity='Obra Civil', position='Cabo O.C.',  level='T1-24', work_type='asistencia', imss_enrolled=True,  imss_weekly_amount=2330.59, bank_account='062180008444858008', bank_name='Afirme'),
        dict(name='Victor Villa Walls',            activity='Dirección',  position='Director',   level='T1-24', work_type='fijo',       fixed_weekly=5000,   imss_enrolled=False),
        dict(name='Marcos Vicente Romero Romero',  activity='Obra Civil', position='Chofer',     level='T1-24', work_type='asistencia', imss_enrolled=False, bank_account='127180013551160425', bank_name='Azteca'),
        dict(name='Carlos Alberto Luna Moreno',    activity='Obra Civil', position='Cabo O.C.',  level='T1-24', work_type='asistencia', imss_enrolled=True,  imss_weekly_amount=2330.59, bank_account='014180568962358044', bank_name='Santander'),
        dict(name='Sergio Oliva',                  activity='Obra Civil', position='Cabo O.C.',  level='T1-24', work_type='asistencia', imss_enrolled=False),
        dict(name='Mauricio Ruiz',                 activity='Obra Civil', position='Cabo O.C.',  level='T1-24', work_type='asistencia', imss_enrolled=False),
    ],
    'PTC': [
        dict(name='Mariana Mendez',                activity='Dirección',  position='Director',   level='T1-26', work_type='fijo',       fixed_weekly=3500,   imss_enrolled=False),
        dict(name='Sulpicio Miguel Aquino',        activity='Obra Civil', position='Cabo O.C.',  level='T2-26', work_type='asistencia', imss_enrolled=True,  imss_weekly_amount=2330.59),
        dict(name='Carlos Alberto Luna Moreno',    activity='Obra Civil', position='Cabo O.C.',  level='T2-26', work_type='asistencia', imss_enrolled=False),
        dict(name='Marcos Vicente Romero Romero',  activity='Suministro', position='Chofer',     level='T2-26', work_type='asistencia', imss_enrolled=False, bank_account='127180013551160425', bank_name='Azteca'),
        dict(name='Sergio Oliva',                  activity='Almacen',    position='Almacen',    level='T2-26', work_type='asistencia', imss_enrolled=False),
        dict(name='Francisco Javier González Romero', activity='Maquinista', position='Cabo M', level='T3-26', work_type='asistencia', imss_enrolled=True,  imss_weekly_amount=2330.59, bank_account='014180568962358044', bank_name='Santander'),
    ],
}

with app.app_context():
    seed_tabulador()
    for pd in PROJECTS:
        proj = Project.query.filter_by(code=pd['code']).first()
        if not proj:
            proj = Project(**pd)
            db.session.add(proj)
            db.session.flush()
            print(f"Created project: {pd['name']}")
        else:
            print(f"Project exists: {pd['name']}")
        for wd in WORKERS[pd['code']]:
            # Map 'activity' key to 'trade' (Worker model column)
            worker_data = dict(wd)
            worker_data['trade'] = worker_data.pop('activity')
            exists = Worker.query.filter_by(name=worker_data['name'], project_id=proj.id).first()
            if not exists:
                w = Worker(project_id=proj.id, active=True, **worker_data)
                db.session.add(w)
                print(f"  + Worker: {worker_data['name']}")
            else:
                print(f"  ~ Exists: {worker_data['name']}")
    db.session.commit()
    print("Done.")
