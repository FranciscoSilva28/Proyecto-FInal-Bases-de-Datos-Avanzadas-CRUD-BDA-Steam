from flask import Blueprint, request, session, redirect, url_for, flash
from db import get_connection
from decorators import role_required
import oracledb

reviews_bp = Blueprint('reviews', __name__, url_prefix='/reviews')

@reviews_bp.route('/calificar/<int:id_juego>', methods=['POST'])
@role_required('USUARIO')
def calificar_juego(id_juego):
    """
    Inserta una calificación. 
    Oracle la enviará a la partición correcta (p1, p2, p3, p4 o p5) según la puntuación.
    """
    puntuacion = int(request.form.get('puntuacion'))
    comentario = request.form.get('comentario')
    id_usuario = session.get('usuario_id')
    
    if puntuacion < 1 or puntuacion > 5:
        flash("La puntuación debe estar entre 1 y 5.", "error")
        return redirect(url_for('games.catalogo'))

    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Insertamos en la tabla particionada por lista
        sql = """INSERT INTO calificaciones_part (id_usuario, id_juego, puntuacion, comentario) 
                 VALUES (:user_id, :game_id, :score, :comment_text)"""
        
        cursor.execute(sql, {
            "user_id": id_usuario,
            "game_id": id_juego,
            "score": puntuacion,
            "comment_text": comentario
        })
        conn.commit()
        flash("¡Gracias por tu reseña! Ha sido guardada correctamente.", "success")
        
    except oracledb.IntegrityError:
        conn.rollback()
        flash("Ya has calificado este juego anteriormente.", "error")
    except oracledb.Error as e:
        conn.rollback()
        error_msg = str(e)
        if 'ORA-20002' in error_msg:
            flash("No puedes calificar un juego que no has comprado (Regla BD).", "error")
        else:
            flash(f"Error en la base de datos: {e}", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('games.catalogo'))
