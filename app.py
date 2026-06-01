from flask import Flask, redirect, url_for, session
from db import init_pool

# Importar los controladores (Blueprints) que hemos creado
from controllers.auth_controller import auth_bp
from controllers.games_controller import games_bp
from controllers.admin_controller import admin_bp
from controllers.reviews_controller import reviews_bp
from controllers.cart_controller import cart_bp

app = Flask(__name__)

# Clave secreta obligatoria para poder usar sesiones (session) y mensajes (flash)
app.secret_key = "clave_secreta_super_segura_proyecto_bda_unam"

# Límite de subida: 50 MB (necesario para los BLOBs de video/trailer)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# ==========================================
# INICIALIZACIÓN DE BASE DE DATOS
# ==========================================
# Llamamos a init_pool() de db.py para que, en cuanto levante el servidor,
init_pool()

# ==========================================
# REGISTRO DE MÓDULOS (BLUEPRINTS)
# ==========================================
# Esto le dice a Flask que las rutas definidas en otros archivos existen
app.register_blueprint(auth_bp)
app.register_blueprint(games_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(reviews_bp)
app.register_blueprint(cart_bp)
# ==========================================
# RUTAS PRINCIPALES
# ==========================================
@app.route('/')
def index():
    """
    Ruta raíz de la plataforma.
    Actúa como un enrutador inteligente dependiendo de si hay una sesión activa y el ROL.
    """
    if 'usuario_id' in session:
        rol = session.get('rol')
        
        # Redirecciones basadas en ROL
        if rol == 'ADMIN':
            # Manda al admin a ver los juegos que esperan aprobación
            return redirect(url_for('admin.juegos_pendientes')) 
            
        elif rol == 'EMPRESA':
            # Manda a la empresa a su panel de gestión
            # Nota: Asumimos que esta ruta está en games_controller
            return redirect(url_for('games.subir_juego'))
            
        else:
            # Si es USUARIO normal, lo manda directo a comprar
            return redirect(url_for('games.catalogo'))
            
    # Si nadie ha iniciado sesión, lo mandamos a la pantalla de Login
    return redirect(url_for('auth.login'))

# ==========================================
# EJECUCION DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    # host='0.0.0.0' permite que la app Flask reciba peticiones 
    # incluso si está corriendo dentro de un contenedor Docker.
    app.run(debug=True, host='0.0.0.0', port=5000)
