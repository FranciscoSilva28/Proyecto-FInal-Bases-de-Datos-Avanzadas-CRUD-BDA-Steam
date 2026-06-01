from flask import Blueprint, request, render_template, session, redirect, url_for, flash
from db import get_connection
from decorators import role_required
import oracledb
import os

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/juegos-pendientes')
@role_required('ADMIN')
def juegos_pendientes():
    """Muestra los juegos pendientes de aprobación y los ya revocados."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Juegos Pendientes ('PE')
    sql_pendientes = """
        SELECT v.id_juego, v.titulo, v.precio, v.fecha_lanzamiento, u.username 
        FROM videojuego v
        JOIN usuario u ON v.id_empresa = u.id_usuario
        WHERE v.estado = 'PE'
        ORDER BY v.fecha_lanzamiento DESC
    """
    cursor.execute(sql_pendientes)
    pendientes = cursor.fetchall()
    
    # Juegos Revocados ('RE')
    sql_revocados = """
        SELECT v.id_juego, v.titulo, v.precio, v.fecha_lanzamiento, u.username 
        FROM videojuego v
        JOIN usuario u ON v.id_empresa = u.id_usuario
        WHERE v.estado = 'RE'
        ORDER BY v.fecha_aprobacion DESC NULLS LAST
    """
    cursor.execute(sql_revocados)
    revocados = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('admin/pendientes.html', pendientes=pendientes, revocados=revocados)

@admin_bp.route('/aprobar-juego/<int:id_juego>', methods=['POST'])
@role_required('ADMIN')
def aprobar_juego(id_juego):
    """Llama al STORED PROCEDURE sp_aprobar_juego."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        p_resultado = cursor.var(oracledb.STRING, 200)
        cursor.callproc('sp_aprobar_juego', [id_juego, session['usuario_id'], p_resultado])
        
        resultado = p_resultado.getvalue()
        if resultado == 'OK':
            flash("Juego aprobado y publicado en el catálogo.", "success")
        else:
            flash(resultado, "error")
    except oracledb.Error as e:
        conn.rollback()
        flash(f"Error: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.juegos_pendientes'))

@admin_bp.route('/denegar-juego/<int:id_juego>', methods=['POST'])
@role_required('ADMIN')
def denegar_juego(id_juego):
    """Llama al STORED PROCEDURE sp_denegar_juego."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        p_resultado = cursor.var(oracledb.STRING, 200)
        cursor.callproc('sp_denegar_juego', [id_juego, session['usuario_id'], p_resultado])
        
        resultado = p_resultado.getvalue()
        if resultado == 'OK':
            flash("Juego denegado. La empresa será notificada.", "warning")
        else:
            flash(resultado, "error")
    except oracledb.Error as e:
        conn.rollback()
        flash(f"Error: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.juegos_pendientes'))

@admin_bp.route('/revocar-juego/<int:id_juego>', methods=['POST'])
@role_required('ADMIN')
def revocar_juego(id_juego):
    """Llama al STORED PROCEDURE sp_revocar_juego para quitar un juego del catálogo."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        p_resultado = cursor.var(oracledb.STRING, 200)
        cursor.callproc('sp_revocar_juego', [id_juego, session['usuario_id'], p_resultado])
        
        resultado = p_resultado.getvalue()
        if resultado == 'OK':
            flash("Juego revocado exitosamente. Ya no es visible en el catálogo.", "warning")
        else:
            flash(resultado, "error")
    except oracledb.Error as e:
        conn.rollback()
        flash(f"Error: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('games.catalogo'))

@admin_bp.route('/restaurar-juego/<int:id_juego>', methods=['POST'])
@role_required('ADMIN')
def restaurar_juego(id_juego):
    """Llama al STORED PROCEDURE sp_restaurar_juego para devolver un juego al catálogo."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        p_resultado = cursor.var(oracledb.STRING, 200)
        cursor.callproc('sp_restaurar_juego', [id_juego, session['usuario_id'], p_resultado])
        
        resultado = p_resultado.getvalue()
        if resultado == 'OK':
            flash("Juego restaurado exitosamente. Ahora vuelve a ser visible en el catálogo.", "success")
        else:
            flash(resultado, "error")
    except oracledb.Error as e:
        conn.rollback()
        flash(f"Error: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.juegos_pendientes'))

@admin_bp.route('/eliminar-juego/<int:id_juego>', methods=['POST'])
@role_required('ADMIN')
def eliminar_juego_permanente(id_juego):
    """Llama al STORED PROCEDURE sp_eliminar_juego_permanente para borrado fisico total."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Obtener rutas de archivos antes de borrar (para limpiar disco)
        cursor.execute("SELECT portada_ruta, trailer_ruta FROM videojuego WHERE id_juego = :1", [id_juego])
        rutas = cursor.fetchone()
        
        p_resultado = cursor.var(oracledb.STRING, 200)
        cursor.callproc('sp_eliminar_juego_permanente', [id_juego, session['usuario_id'], p_resultado])
        
        resultado = p_resultado.getvalue()
        if resultado == 'OK':
            # Limpiar archivos del disco si existen (modo RUTA)
            if rutas:
                for ruta in rutas:
                    if ruta and os.path.exists(ruta):
                        try:
                            os.remove(ruta)
                        except OSError:
                            pass
            flash("Juego eliminado permanentemente del sistema.", "success")
        else:
            flash(resultado, "error")
    except oracledb.Error as e:
        conn.rollback()
        flash(f"Error: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.juegos_pendientes'))

@admin_bp.route('/actividad-usuarios')
@role_required('ADMIN')
def actividad_usuarios():
    """
    Consulta la actividad de compras usando la VISTA v_actividad_compras
    y el resumen usando la VISTA v_resumen_plataforma.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Usar la VISTA v_actividad_compras
    cursor.execute("SELECT * FROM v_actividad_compras ORDER BY fecha_pedido DESC")
    pedidos = cursor.fetchall()
    
    # Detalle de cada pedido
    sql_detalles = """SELECT dp.id_pedido, v.titulo, dp.precio_pagado
                      FROM detalle_pedido dp
                      JOIN videojuego v ON dp.id_juego = v.id_juego
                      ORDER BY dp.id_pedido DESC"""
    cursor.execute(sql_detalles)
    detalles_raw = cursor.fetchall()
    
    detalles = {}
    for id_pedido, titulo, precio in detalles_raw:
        if id_pedido not in detalles:
            detalles[id_pedido] = []
        detalles[id_pedido].append({"titulo": titulo, "precio": precio})
    
    # Usar la VISTA v_resumen_plataforma
    cursor.execute("SELECT * FROM v_resumen_plataforma")
    resumen = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return render_template('admin/actividad.html', 
                           pedidos=pedidos, 
                           detalles=detalles, 
                           resumen=resumen)

@admin_bp.route('/auditoria')
@role_required('ADMIN')
def auditoria():
    """Consulta el log de auditoría usando la VISTA v_auditoria_reciente."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""SELECT id_auditoria, usuario, accion, descripcion, fecha_formateada 
                      FROM v_auditoria_reciente 
                      WHERE ROWNUM <= 100""")
    registros = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin/auditoria.html', registros=registros)

@admin_bp.route('/respaldo-videojuegos', methods=['POST'])
@role_required('ADMIN')
def respaldo_videojuegos():
    """
    Cumple con el requerimiento de: COPIA DE UNA TABLA CON DATOS.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        try:
            cursor.execute("DROP TABLE videojuego_backup_con_datos")
        except oracledb.DatabaseError:
            pass

        sql_backup = "CREATE TABLE videojuego_backup_con_datos AS SELECT * FROM videojuego"
        cursor.execute(sql_backup)
        
        flash("Respaldo de la tabla VIDEOJUEGO creado exitosamente (Estructura y Datos).", "success")
    except oracledb.Error as e:
        flash(f"Error al crear el respaldo: {e}", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin.juegos_pendientes'))
