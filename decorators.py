from flask import session, redirect, url_for, flash
from functools import wraps

def role_required(required_role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Verifica si el usuario inicio sesion
            if 'usuario_id' not in session:
                flash("Por favor, inicia sesion primero.", "error")
                return redirect(url_for('auth.login'))
            
            # 2. Verifica si el rol coincide (el ADMIN tiene acceso a todo)
            if session.get('rol') != required_role and session.get('rol') != 'ADMIN':
                flash("No tienes permisos para acceder a esta seccion.", "error")
                return redirect(url_for('index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
