from flask import Blueprint, request, render_template, session, redirect, url_for, flash, Response, send_file
from db import get_connection
from decorators import role_required
import oracledb
import os
import uuid

games_bp = Blueprint('games', __name__)

UPLOAD_PORTADAS = os.path.join('static', 'uploads', 'portadas')
UPLOAD_TRAILERS = os.path.join('static', 'uploads', 'trailers')


@games_bp.route('/catalogo')
def catalogo():
    """Muestra solo los juegos aprobados a los usuarios normales."""
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM v_catalogo_publico ORDER BY fecha_lanzamiento DESC"
    cursor.execute(sql)
    juegos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('catalogo.html', juegos=juegos)


@games_bp.route('/empresa/mis-juegos')
@role_required('EMPRESA')
def mis_juegos():
    """Lista todos los juegos de la empresa logueada con su estado actual."""
    conn = get_connection()
    cursor = conn.cursor()
    sql = """SELECT id_juego, titulo, precio, estado, fecha_subida, modo_almacenamiento
             FROM videojuego 
             WHERE id_empresa = :1
             ORDER BY fecha_subida DESC"""
    cursor.execute(sql, [session['usuario_id']])
    juegos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('mis_juegos.html', juegos=juegos)


@games_bp.route('/empresa/subir-juego', methods=['GET', 'POST'])
@role_required('EMPRESA')
def subir_juego():
    """Permite a una empresa subir un juego en estado Pendiente ('PE')."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        descripcion = request.form.get('descripcion')
        precio = float(request.form.get('precio'))
        generos_seleccionados = request.form.getlist('generos')
        modo = request.form.get('modo_almacenamiento', 'BLOB')
        
        portada_file = request.files.get('portada')
        trailer_file = request.files.get('trailer')
        
        try:
            id_juego_var = cursor.var(oracledb.NUMBER)
            
            if modo == 'RUTA':
                # Modo RUTA: guardar archivos en disco, solo ruta en Oracle
                sql = """INSERT INTO videojuego (id_empresa, titulo, descripcion, precio, estado, modo_almacenamiento) 
                         VALUES (:empresa, :titulo, :descripcion, :precio, 'PE', 'RUTA')
                         RETURNING id_juego INTO :id_juego_out"""
                cursor.execute(sql, {
                    "empresa": session['usuario_id'],
                    "titulo": titulo,
                    "descripcion": descripcion,
                    "precio": precio,
                    "id_juego_out": id_juego_var
                })
                
                id_juego_generado = int(id_juego_var.getvalue()[0])
                
                if portada_file and portada_file.filename:
                    ext = os.path.splitext(portada_file.filename)[1] or '.jpg'
                    filename = f"{id_juego_generado}_{uuid.uuid4().hex[:8]}{ext}"
                    ruta = os.path.join(UPLOAD_PORTADAS, filename)
                    os.makedirs(UPLOAD_PORTADAS, exist_ok=True)
                    portada_file.save(ruta)
                    cursor.execute("UPDATE videojuego SET portada_ruta = :1 WHERE id_juego = :2", [ruta, id_juego_generado])
                
                if trailer_file and trailer_file.filename:
                    ext = os.path.splitext(trailer_file.filename)[1] or '.mp4'
                    filename = f"{id_juego_generado}_{uuid.uuid4().hex[:8]}{ext}"
                    ruta = os.path.join(UPLOAD_TRAILERS, filename)
                    os.makedirs(UPLOAD_TRAILERS, exist_ok=True)
                    trailer_file.save(ruta)
                    cursor.execute("UPDATE videojuego SET trailer_ruta = :1 WHERE id_juego = :2", [ruta, id_juego_generado])
            
            else:
                # Modo BLOB: guardar datos binarios directamente en Oracle
                portada_blob = portada_file.read() if portada_file and portada_file.filename else None
                trailer_blob = trailer_file.read() if trailer_file and trailer_file.filename else None
                
                sql = """INSERT INTO videojuego (id_empresa, titulo, descripcion, precio, estado, portada, trailer, modo_almacenamiento) 
                         VALUES (:empresa, :titulo, :descripcion, :precio, 'PE', :portada, :trailer, 'BLOB')
                         RETURNING id_juego INTO :id_juego_out"""
                cursor.execute(sql, {
                    "empresa": session['usuario_id'],
                    "titulo": titulo,
                    "descripcion": descripcion,
                    "precio": precio,
                    "portada": portada_blob,
                    "trailer": trailer_blob,
                    "id_juego_out": id_juego_var
                })
                
                id_juego_generado = int(id_juego_var.getvalue()[0])
            
            # Insertar los generos relacionados
            for gen_id in generos_seleccionados:
                cursor.execute("INSERT INTO videojuego_genero (id_juego, id_genero) VALUES (:1, :2)", 
                              [id_juego_generado, int(gen_id)])
            
            conn.commit()
            flash("Juego subido con éxito. Pendiente de aprobación por un Administrador.", "success")
            return redirect(url_for('games.subir_juego'))
            
        except oracledb.Error as e:
            conn.rollback()
            flash(f"Error al subir el juego: {e}", "error")
    
    cursor.execute("SELECT id_genero, nombre FROM genero ORDER BY nombre")
    generos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('subir_juego.html', generos=generos)


@games_bp.route('/empresa/editar-juego/<int:id_juego>', methods=['GET', 'POST'])
@role_required('EMPRESA')
def editar_juego(id_juego):
    """Permite a la empresa editar un juego existente (aprobado o pendiente)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Verificar propiedad y obtener datos basicos
    cursor.execute("""SELECT id_empresa, titulo, precio, estado, modo_almacenamiento 
                      FROM videojuego WHERE id_juego = :1""", [id_juego])
    juego = cursor.fetchone()
    
    if not juego or juego[0] != session['usuario_id']:
        flash("No tienes permisos para editar este juego.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('games.mis_juegos'))
    
    if request.method == 'POST':
        descripcion = request.form.get('descripcion')
        precio = float(request.form.get('precio'))
        modo = request.form.get('modo_almacenamiento', 'BLOB')
        generos_seleccionados = request.form.getlist('generos')
        
        portada_file = request.files.get('portada')
        trailer_file = request.files.get('trailer')
        
        try:
            # Construir UPDATE dinamico
            updates = ["descripcion = :descripcion", "precio = :precio", "modo_almacenamiento = :modo"]
            params = {"descripcion": descripcion, "precio": precio, "modo": modo, "id_juego": id_juego}
            
            if modo == 'RUTA':
                if portada_file and portada_file.filename:
                    ext = os.path.splitext(portada_file.filename)[1] or '.jpg'
                    filename = f"{id_juego}_{uuid.uuid4().hex[:8]}{ext}"
                    ruta = os.path.join(UPLOAD_PORTADAS, filename)
                    os.makedirs(UPLOAD_PORTADAS, exist_ok=True)
                    portada_file.save(ruta)
                    updates.append("portada_ruta = :portada_ruta")
                    updates.append("portada = NULL")
                    params["portada_ruta"] = ruta
                
                if trailer_file and trailer_file.filename:
                    ext = os.path.splitext(trailer_file.filename)[1] or '.mp4'
                    filename = f"{id_juego}_{uuid.uuid4().hex[:8]}{ext}"
                    ruta = os.path.join(UPLOAD_TRAILERS, filename)
                    os.makedirs(UPLOAD_TRAILERS, exist_ok=True)
                    trailer_file.save(ruta)
                    updates.append("trailer_ruta = :trailer_ruta")
                    updates.append("trailer = NULL")
                    params["trailer_ruta"] = ruta
            else:
                if portada_file and portada_file.filename:
                    updates.append("portada = :portada")
                    updates.append("portada_ruta = NULL")
                    params["portada"] = portada_file.read()
                
                if trailer_file and trailer_file.filename:
                    updates.append("trailer = :trailer")
                    updates.append("trailer_ruta = NULL")
                    params["trailer"] = trailer_file.read()
            
            sql = f"UPDATE videojuego SET {', '.join(updates)} WHERE id_juego = :id_juego"
            cursor.execute(sql, params)
            
            # Actualizar generos (borrar y re-insertar)
            cursor.execute("DELETE FROM videojuego_genero WHERE id_juego = :1", [id_juego])
            for gen_id in generos_seleccionados:
                cursor.execute("INSERT INTO videojuego_genero (id_juego, id_genero) VALUES (:1, :2)", 
                              [id_juego, int(gen_id)])
            
            conn.commit()
            flash("Juego actualizado exitosamente.", "success")
            cursor.close()
            conn.close()
            return redirect(url_for('games.mis_juegos'))
            
        except oracledb.Error as e:
            conn.rollback()
            error_msg = str(e)
            if 'ORA-20003' in error_msg:
                flash("No se puede cambiar el título de un juego aprobado (Regla BD).", "error")
            elif 'ORA-20004' in error_msg:
                flash("No se puede incrementar el precio más del 20% en juegos aprobados (Regla BD).", "error")
            else:
                flash(f"Error al actualizar: {e}", "error")
    
    # GET: cargar datos actuales + generos
    cursor.execute("SELECT descripcion FROM videojuego WHERE id_juego = :1", [id_juego])
    desc_row = cursor.fetchone()
    if desc_row and desc_row[0]:
        descripcion_text = desc_row[0].read() if hasattr(desc_row[0], 'read') else str(desc_row[0])
    else:
        descripcion_text = ''
    
    cursor.execute("SELECT id_genero, nombre FROM genero ORDER BY nombre")
    generos = cursor.fetchall()
    
    cursor.execute("SELECT id_genero FROM videojuego_genero WHERE id_juego = :1", [id_juego])
    generos_actuales = [row[0] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return render_template('editar_juego.html', 
                           juego=juego, id_juego=id_juego,
                           descripcion_text=descripcion_text,
                           generos=generos, 
                           generos_actuales=generos_actuales)


@games_bp.route('/imagen-juego/<int:id_juego>')
def imagen_juego(id_juego):
    """
    Ruta para servir el BLOB de imagen (portada) desde Oracle o desde disco.
    Detecta automaticamente el modo de almacenamiento.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""SELECT portada, modo_almacenamiento, portada_ruta 
                          FROM videojuego WHERE id_juego = :1""", [id_juego])
        row = cursor.fetchone()
        
        if row:
            modo = row[1] if row[1] else 'BLOB'
            
            if modo == 'RUTA' and row[2]:
                # Servir desde disco
                if os.path.exists(row[2]):
                    return send_file(row[2], mimetype='image/jpeg')
            elif row[0]:
                # Servir desde Oracle BLOB
                image_data = row[0].read()
                return Response(image_data, mimetype='image/jpeg')
        
        return Response("", status=404)
    except oracledb.Error as e:
        return Response("", status=500)
    finally:
        cursor.close()
        conn.close()


@games_bp.route('/trailer-juego/<int:id_juego>')
def trailer_juego(id_juego):
    """
    Ruta para servir el BLOB de video (trailer) desde Oracle o desde disco.
    Soporta Range Requests para streaming cuando es BLOB.
    Cuando es RUTA, Flask send_file maneja Range Requests automaticamente.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""SELECT trailer, modo_almacenamiento, trailer_ruta 
                          FROM videojuego WHERE id_juego = :1""", [id_juego])
        row = cursor.fetchone()
        
        if row:
            modo = row[1] if row[1] else 'BLOB'
            
            if modo == 'RUTA' and row[2]:
                # Servir desde disco (send_file soporta Range Requests automaticamente)
                if os.path.exists(row[2]):
                    return send_file(row[2], mimetype='video/mp4', conditional=True)
            elif row[0]:
                # Servir desde Oracle BLOB con soporte Range Request manual
                video_data = row[0].read()
                total_size = len(video_data)
                
                range_header = request.headers.get('Range')
                if range_header:
                    byte_range = range_header.replace('bytes=', '').split('-')
                    start = int(byte_range[0])
                    end = int(byte_range[1]) if byte_range[1] else total_size - 1
                    end = min(end, total_size - 1)
                    chunk = video_data[start:end + 1]
                    
                    response = Response(
                        chunk,
                        status=206,
                        mimetype='video/mp4',
                        headers={
                            'Content-Range': f'bytes {start}-{end}/{total_size}',
                            'Accept-Ranges': 'bytes',
                            'Content-Length': len(chunk),
                        }
                    )
                    return response
                else:
                    return Response(
                        video_data, 
                        mimetype='video/mp4',
                        headers={
                            'Accept-Ranges': 'bytes',
                            'Content-Length': total_size,
                        }
                    )
        
        return Response("", status=404)
    except oracledb.Error as e:
        return Response(f"Error: {e}", status=500)
    finally:
        cursor.close()
        conn.close()
