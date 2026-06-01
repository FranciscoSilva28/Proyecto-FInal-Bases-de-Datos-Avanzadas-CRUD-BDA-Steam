from flask import Blueprint, request, session, redirect, url_for, flash, render_template
from db import get_connection
import oracledb
from werkzeug.security import check_password_hash # Para verificar contraseñas seguras

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            # Consultamos al usuario por su email 
            sql = """SELECT id_usuario, username, password_hash, rol, activo 
                     FROM usuario WHERE email = :email"""
            cursor.execute(sql, [email])
            user = cursor.fetchone()
            
            if user:
                # Oracle devuelve tuplas. Mapeamos por índice.
                user_id, username, db_password_hash, rol, activo = user
                
                if activo == 0:
                    flash("Tu cuenta está desactivada.", "error")
                    return redirect(url_for('auth.login'))
                
                # En un entorno real, usaríamos check_password_hash(db_password_hash, password)
                # Por simplicidad en la prueba, asumiremos texto plano o un hash simple si aún no implementas el registro
                if db_password_hash == password: 
                    session['usuario_id'] = user_id
                    session['username'] = username
                    session['rol'] = rol
                    
                    flash(f"Bienvenido {username}", "success")
                    # Redirigir según el rol
                    if rol == 'ADMIN':
                        return redirect(url_for('admin.juegos_pendientes'))
                    elif rol == 'EMPRESA':
                        return redirect(url_for('games.subir_juego'))
                    else:
                        return redirect(url_for('games.catalogo'))
                else:
                    flash("Contraseña incorrecta.", "error")
            else:
                flash("El correo no está registrado.", "error")
                
        except oracledb.Error as e:
            flash(f"Error de base de datos: {e}", "error")
        finally:
            cursor.close()
            conn.close()
            
    return render_template('login.html')

@auth_bp.route('/registro', methods=['GET', 'POST'])
def registro():
    """
    Ruta de registro de nuevos usuarios.
    Permite crear cuentas de tipo USUARIO o EMPRESA.
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        rol = request.form.get('rol', 'USUARIO')

        # Validaciones básicas
        if not username or not email or not password:
            flash("Todos los campos son obligatorios.", "error")
            return redirect(url_for('auth.registro'))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
            return redirect(url_for('auth.registro'))

        if password != password_confirm:
            flash("Las contraseñas no coinciden.", "error")
            return redirect(url_for('auth.registro'))

        if rol not in ('USUARIO', 'EMPRESA'):
            rol = 'USUARIO'

        conn = get_connection()
        cursor = conn.cursor()

        try:
            # Verificar si el email ya existe
            cursor.execute("SELECT 1 FROM usuario WHERE email = :1", [email])
            if cursor.fetchone():
                flash("Ya existe una cuenta con ese correo electrónico.", "error")
                return redirect(url_for('auth.registro'))

            # Verificar si el username ya existe
            cursor.execute("SELECT 1 FROM usuario WHERE username = :1", [username])
            if cursor.fetchone():
                flash("Ese nombre de usuario ya está en uso.", "error")
                return redirect(url_for('auth.registro'))

            # Insertar nuevo usuario
            sql = """INSERT INTO usuario (username, email, password_hash, rol)
                     VALUES (:username, :email, :password, :rol)"""
            cursor.execute(sql, {
                "username": username,
                "email": email,
                "password": password,
                "rol": rol
            })
            conn.commit()

            flash("¡Cuenta creada exitosamente! Ahora puedes iniciar sesión.", "success")
            return redirect(url_for('auth.login'))

        except oracledb.Error as e:
            conn.rollback()
            flash(f"Error al crear la cuenta: {e}", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template('registro.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for('auth.login'))
