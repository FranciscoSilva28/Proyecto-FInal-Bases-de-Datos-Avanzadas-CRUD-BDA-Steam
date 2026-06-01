from flask import Blueprint, request, session, redirect, url_for, flash, render_template
from db import get_connection
from decorators import role_required
import oracledb

cart_bp = Blueprint('cart', __name__, url_prefix='/carrito')

@cart_bp.route('/')
@role_required('USUARIO')
def ver_carrito():
    """Muestra los juegos que el usuario ha agregado al carrito."""
    conn = get_connection()
    cursor = conn.cursor()
    
    usuario_id = session['usuario_id']
    
    # Unimos el carrito con la tabla de videojuegos para obtener detalles
    sql = """SELECT c.id_carrito, v.id_juego, v.titulo, v.precio 
             FROM carrito c
             JOIN videojuego v ON c.id_juego = v.id_juego
             WHERE c.id_usuario = :1"""
             
    cursor.execute(sql, [usuario_id])
    items = cursor.fetchall()
    
    # Usamos la FUNCIÓN fn_total_carrito de Oracle en lugar de sumar en Python
    cursor.execute("SELECT fn_total_carrito(:1) FROM DUAL", [usuario_id])
    total = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return render_template('carrito.html', items=items, total=total)

@cart_bp.route('/agregar/<int:id_juego>', methods=['POST'])
@role_required('USUARIO')
def agregar(id_juego):
    """Agrega un juego al carrito temporal."""
    conn = get_connection()
    cursor = conn.cursor()
    usuario_id = session['usuario_id']
    
    try:
        # 1. Verificar si ya lo tiene en la biblioteca
        cursor.execute("SELECT 1 FROM biblioteca WHERE id_usuario = :1 AND id_juego = :2", [usuario_id, id_juego])
        if cursor.fetchone():
            flash("Ya posees este juego en tu biblioteca.", "info")
            return redirect(url_for('games.catalogo'))
            
        # 2. Verificar si ya está en el carrito
        cursor.execute("SELECT 1 FROM carrito WHERE id_usuario = :1 AND id_juego = :2", [usuario_id, id_juego])
        if cursor.fetchone():
            flash("El juego ya está en tu carrito.", "info")
            return redirect(url_for('cart.ver_carrito'))
            
        # 3. Insertar en el carrito
        cursor.execute("INSERT INTO carrito (id_usuario, id_juego) VALUES (:1, :2)", [usuario_id, id_juego])
        conn.commit()
        flash("Juego agregado al carrito.", "success")
        
    except oracledb.Error as e:
        conn.rollback()
        flash(f"Error al agregar al carrito: {e}", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('games.catalogo'))

@cart_bp.route('/quitar/<int:id_juego>', methods=['POST'])
@role_required('USUARIO')
def quitar(id_juego):
    """Quita un juego del carrito temporal."""
    conn = get_connection()
    cursor = conn.cursor()
    usuario_id = session['usuario_id']
    
    try:
        cursor.execute("DELETE FROM carrito WHERE id_usuario = :1 AND id_juego = :2", [usuario_id, id_juego])
        conn.commit()
        flash("Juego eliminado del carrito.", "success")
    except oracledb.Error as e:
        conn.rollback()
        flash(f"Error al quitar del carrito: {e}", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('cart.ver_carrito'))

@cart_bp.route('/pagar', methods=['POST'])
@role_required('USUARIO')
def pagar():
    """
    Procesa la compra llamando al STORED PROCEDURE sp_procesar_compra.
    Toda la lógica transaccional vive en Oracle (cursor, pedido, detalles, biblioteca, vaciar carrito).
    """
    conn = get_connection()
    cursor = conn.cursor()
    usuario_id = session['usuario_id']
    
    try:
        # Variables de salida de Oracle
        p_id_pedido  = cursor.var(oracledb.NUMBER)
        p_total      = cursor.var(oracledb.NUMBER)
        p_num_juegos = cursor.var(oracledb.NUMBER)
        
        # Llamada al STORED PROCEDURE
        cursor.callproc('sp_procesar_compra', [usuario_id, p_id_pedido, p_total, p_num_juegos])
        
        total = p_total.getvalue()
        num   = int(p_num_juegos.getvalue())
        
        flash(f"¡Compra exitosa! Pedido #{int(p_id_pedido.getvalue())} — {num} juego(s) por ${total:.2f}. Ya están en tu biblioteca.", "success")
        
    except oracledb.Error as e:
        conn.rollback()
        error_msg = str(e)
        if 'ORA-20001' in error_msg:
            flash("Tu carrito está vacío.", "error")
        else:
            flash(f"Error procesando el pago: {error_msg}", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('games.catalogo'))

@cart_bp.route('/biblioteca')
@role_required('USUARIO')
def biblioteca():
    """Muestra los juegos adquiridos por el usuario, usando la función fn_promedio_calificacion."""
    conn = get_connection()
    cursor = conn.cursor()
    usuario_id = session['usuario_id']
    
    # Usamos la FUNCIÓN fn_promedio_calificacion y fn_juegos_en_biblioteca de Oracle
    sql = """SELECT v.id_juego, v.titulo, b.fecha_adquisicion,
                    fn_promedio_calificacion(v.id_juego) AS promedio
             FROM biblioteca b
             JOIN videojuego v ON b.id_juego = v.id_juego
             WHERE b.id_usuario = :1
             ORDER BY b.fecha_adquisicion DESC"""
             
    cursor.execute(sql, [usuario_id])
    juegos = cursor.fetchall()
    
    # Total de juegos en biblioteca usando función de Oracle
    cursor.execute("SELECT fn_juegos_en_biblioteca(:1) FROM DUAL", [usuario_id])
    total_juegos = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return render_template('biblioteca.html', juegos=juegos, total_juegos=total_juegos)
