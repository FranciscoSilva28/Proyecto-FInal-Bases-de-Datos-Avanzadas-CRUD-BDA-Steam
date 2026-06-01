-- ============================================================
-- OBJETOS PL/SQL DEL PROYECTO STEAM BDA
-- Triggers, Stored Procedures, Funciones y Vistas
-- ============================================================

-- ============================================================
-- 1. TRIGGERS DE AUDITORIA
-- ============================================================

-- 1a. Trigger: Registrar en AUDITORIA cuando se crea un nuevo usuario
CREATE OR REPLACE TRIGGER trg_auditoria_registro
AFTER INSERT ON usuario
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, accion, descripcion)
    VALUES (:NEW.id_usuario, 'REGISTRO',
            'Nuevo usuario registrado: ' || :NEW.username || ' con rol ' || :NEW.rol);
END;
/

-- 1b. Trigger: Crear perfil automáticamente al registrar un usuario
CREATE OR REPLACE TRIGGER trg_perfil_auto
AFTER INSERT ON usuario
FOR EACH ROW
BEGIN
    INSERT INTO perfil_usuario (id_usuario, nombre_completo, descripcion)
    VALUES (:NEW.id_usuario, :NEW.username, 'Perfil creado automáticamente.');
END;
/

-- 1c. Trigger: Registrar en AUDITORIA cuando se aprueba o deniega un juego
CREATE OR REPLACE TRIGGER trg_auditoria_juego_estado
AFTER UPDATE OF estado ON videojuego
FOR EACH ROW
WHEN (OLD.estado = 'PE' AND NEW.estado IN ('AP', 'RE'))
BEGIN
    INSERT INTO auditoria (id_usuario, accion, descripcion)
    VALUES (:NEW.aprobado_por,
            CASE :NEW.estado WHEN 'AP' THEN 'APROBAR_JUEGO' ELSE 'DENEGAR_JUEGO' END,
            'Juego "' || :NEW.titulo || '" (ID: ' || :NEW.id_juego || ') fue ' ||
            CASE :NEW.estado WHEN 'AP' THEN 'APROBADO' ELSE 'DENEGADO' END ||
            ' por admin ID: ' || :NEW.aprobado_por);
END;
/

-- 1d. Trigger: Registrar en AUDITORIA cuando se realiza un pedido
CREATE OR REPLACE TRIGGER trg_auditoria_pedido
AFTER INSERT ON pedido
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, accion, descripcion)
    VALUES (:NEW.id_usuario, 'COMPRA',
            'Pedido #' || :NEW.id_pedido || ' realizado por $' || TO_CHAR(:NEW.total, '999,990.00'));
END;
/

-- 1e. Trigger: Registrar en AUDITORIA al agregar un juego a la biblioteca
CREATE OR REPLACE TRIGGER trg_auditoria_biblioteca
AFTER INSERT ON biblioteca
FOR EACH ROW
DECLARE
    v_titulo VARCHAR2(200);
BEGIN
    SELECT titulo INTO v_titulo FROM videojuego WHERE id_juego = :NEW.id_juego;
    INSERT INTO auditoria (id_usuario, accion, descripcion)
    VALUES (:NEW.id_usuario, 'ADQUISICION',
            'Juego "' || v_titulo || '" agregado a la biblioteca del usuario.');
END;
/

-- 1f. Trigger: Registrar cuando una empresa sube un juego nuevo
CREATE OR REPLACE TRIGGER trg_auditoria_subida_juego
AFTER INSERT ON videojuego
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, accion, descripcion)
    VALUES (:NEW.id_empresa, 'SUBIR_JUEGO',
            'Juego "' || :NEW.titulo || '" subido a la plataforma. Precio: $' || 
            TO_CHAR(:NEW.precio, '999,990.00') || '. Estado: Pendiente de aprobacion.');
END;
/

-- ============================================================
-- 2. STORED PROCEDURES (Lógica de negocio en Oracle)
-- ============================================================

-- 2a. Procedimiento: Procesar toda la compra como transacción atómica
CREATE OR REPLACE PROCEDURE sp_procesar_compra (
    p_usuario_id  IN NUMBER,
    p_id_pedido   OUT NUMBER,
    p_total       OUT NUMBER,
    p_num_juegos  OUT NUMBER
) AS
    v_id_pedido NUMBER;
    v_total     NUMBER := 0;
    v_count     NUMBER := 0;
    
    -- Cursor para recorrer los items del carrito
    CURSOR c_carrito IS
        SELECT c.id_juego, v.precio
        FROM carrito c
        JOIN videojuego v ON c.id_juego = v.id_juego
        WHERE c.id_usuario = p_usuario_id;
BEGIN
    -- Verificar que el carrito no esté vacío
    SELECT COUNT(*) INTO v_count FROM carrito WHERE id_usuario = p_usuario_id;
    
    IF v_count = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'El carrito esta vacio.');
    END IF;

    -- Calcular total
    SELECT NVL(SUM(v.precio), 0) INTO v_total
    FROM carrito c
    JOIN videojuego v ON c.id_juego = v.id_juego
    WHERE c.id_usuario = p_usuario_id;

    -- Crear cabecera del pedido
    INSERT INTO pedido (id_usuario, total, estado)
    VALUES (p_usuario_id, v_total, 'COMPLETADO')
    RETURNING id_pedido INTO v_id_pedido;

    -- Recorrer cada juego del carrito con el cursor
    FOR item IN c_carrito LOOP
        -- Insertar detalle del pedido
        INSERT INTO detalle_pedido (id_pedido, id_juego, precio_pagado)
        VALUES (v_id_pedido, item.id_juego, item.precio);
        
        -- Mover a biblioteca del usuario
        INSERT INTO biblioteca (id_usuario, id_juego)
        VALUES (p_usuario_id, item.id_juego);
    END LOOP;

    -- Vaciar el carrito
    DELETE FROM carrito WHERE id_usuario = p_usuario_id;

    -- Retornar valores
    p_id_pedido  := v_id_pedido;
    p_total      := v_total;
    p_num_juegos := v_count;

    COMMIT;
    
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

-- 2b. Procedimiento: Aprobar un juego
CREATE OR REPLACE PROCEDURE sp_aprobar_juego (
    p_juego_id  IN NUMBER,
    p_admin_id  IN NUMBER,
    p_resultado OUT VARCHAR2
) AS
    v_estado VARCHAR2(2);
BEGIN
    -- Verificar estado actual
    SELECT estado INTO v_estado FROM videojuego WHERE id_juego = p_juego_id;
    
    IF v_estado != 'PE' THEN
        p_resultado := 'ERROR: El juego no esta en estado pendiente.';
        RETURN;
    END IF;
    
    UPDATE videojuego 
    SET estado = 'AP', 
        fecha_aprobacion = SYSDATE, 
        aprobado_por = p_admin_id
    WHERE id_juego = p_juego_id;
    
    COMMIT;
    p_resultado := 'OK';
    
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        p_resultado := 'ERROR: Juego no encontrado.';
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

-- 2c. Procedimiento: Denegar un juego (Pendiente a Rechazado)
CREATE OR REPLACE PROCEDURE sp_denegar_juego (
    p_juego_id  IN NUMBER,
    p_admin_id  IN NUMBER,
    p_resultado OUT VARCHAR2
) AS
    v_estado VARCHAR2(2);
BEGIN
    SELECT estado INTO v_estado FROM videojuego WHERE id_juego = p_juego_id;
    
    IF v_estado != 'PE' THEN
        p_resultado := 'ERROR: El juego no esta en estado pendiente.';
        RETURN;
    END IF;
    
    UPDATE videojuego 
    SET estado = 'RE', 
        aprobado_por = p_admin_id
    WHERE id_juego = p_juego_id;
    
    COMMIT;
    p_resultado := 'OK';
    
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        p_resultado := 'ERROR: Juego no encontrado.';
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

-- 2d. Procedimiento: Revocar un juego ya aprobado (Aprobado a Rechazado/Oculto)
CREATE OR REPLACE PROCEDURE sp_revocar_juego (
    p_juego_id  IN NUMBER,
    p_admin_id  IN NUMBER,
    p_resultado OUT VARCHAR2
) AS
    v_estado VARCHAR2(2);
    v_afectados NUMBER;
BEGIN
    SELECT estado INTO v_estado FROM videojuego WHERE id_juego = p_juego_id;
    
    IF v_estado != 'AP' THEN
        p_resultado := 'ERROR: El juego no esta publicado.';
        RETURN;
    END IF;
    
    -- Respaldar las bibliotecas afectadas antes de borrarlas
    INSERT INTO biblioteca_revocada (id_biblioteca, id_usuario, id_juego, fecha_adquisicion)
    SELECT id_biblioteca, id_usuario, id_juego, fecha_adquisicion
    FROM biblioteca WHERE id_juego = p_juego_id;
    
    v_afectados := SQL%ROWCOUNT;
    
    -- Eliminar de las bibliotecas activas
    DELETE FROM biblioteca WHERE id_juego = p_juego_id;
    
    -- Eliminar de los carritos activos
    DELETE FROM carrito WHERE id_juego = p_juego_id;
    
    -- Cambiar estado del juego
    UPDATE videojuego 
    SET estado = 'RE', 
        aprobado_por = p_admin_id,
        fecha_aprobacion = SYSDATE
    WHERE id_juego = p_juego_id;
    
    COMMIT;
    p_resultado := 'OK';
    
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        p_resultado := 'ERROR: Juego no encontrado.';
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

-- 2e. Procedimiento: Restaurar un juego revocado y re-establecer bibliotecas
CREATE OR REPLACE PROCEDURE sp_restaurar_juego (
    p_juego_id  IN NUMBER,
    p_admin_id  IN NUMBER,
    p_resultado OUT VARCHAR2
) AS
    v_estado VARCHAR2(2);
    v_restaurados NUMBER;
BEGIN
    SELECT estado INTO v_estado FROM videojuego WHERE id_juego = p_juego_id;
    
    IF v_estado != 'RE' THEN
        p_resultado := 'ERROR: El juego no esta en estado revocado.';
        RETURN;
    END IF;
    
    -- Re-insertar bibliotecas desde el respaldo
    FOR reg IN (SELECT id_usuario, id_juego, fecha_adquisicion 
                FROM biblioteca_revocada WHERE id_juego = p_juego_id) LOOP
        BEGIN
            INSERT INTO biblioteca (id_usuario, id_juego, fecha_adquisicion)
            VALUES (reg.id_usuario, reg.id_juego, reg.fecha_adquisicion);
        EXCEPTION
            WHEN DUP_VAL_ON_INDEX THEN
                NULL; -- Skip if somehow already exists
        END;
    END LOOP;
    
    v_restaurados := SQL%ROWCOUNT;
    
    -- Limpiar respaldo para este juego
    DELETE FROM biblioteca_revocada WHERE id_juego = p_juego_id;
    
    -- Restaurar estado a Aprobado
    UPDATE videojuego 
    SET estado = 'AP',
        aprobado_por = p_admin_id,
        fecha_aprobacion = SYSDATE
    WHERE id_juego = p_juego_id;
    
    COMMIT;
    p_resultado := 'OK';
    
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        p_resultado := 'ERROR: Juego no encontrado.';
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

-- 2f. Procedimiento: Eliminar permanentemente un juego revocado
CREATE OR REPLACE PROCEDURE sp_eliminar_juego_permanente (
    p_juego_id  IN NUMBER,
    p_admin_id  IN NUMBER,
    p_resultado OUT VARCHAR2
) AS
    v_estado VARCHAR2(2);
    v_titulo VARCHAR2(200);
BEGIN
    SELECT estado, titulo INTO v_estado, v_titulo FROM videojuego WHERE id_juego = p_juego_id;
    
    IF v_estado != 'RE' THEN
        p_resultado := 'ERROR: Solo se pueden eliminar permanentemente juegos revocados.';
        RETURN;
    END IF;
    
    -- Borrar todas las dependencias en cascada
    DELETE FROM biblioteca_revocada WHERE id_juego = p_juego_id;
    DELETE FROM calificaciones_part WHERE id_juego = p_juego_id;
    DELETE FROM detalle_pedido WHERE id_juego = p_juego_id;
    DELETE FROM carrito WHERE id_juego = p_juego_id;
    DELETE FROM videojuego_genero WHERE id_juego = p_juego_id;
    
    -- Borrado fisico del videojuego
    DELETE FROM videojuego WHERE id_juego = p_juego_id;
    
    -- Registrar auditoria
    INSERT INTO auditoria (id_usuario, accion, descripcion)
    VALUES (p_admin_id, 'ELIMINAR_PERMANENTE', 
            'Juego "' || v_titulo || '" (ID: ' || p_juego_id || ') eliminado permanentemente del sistema.');
    
    COMMIT;
    p_resultado := 'OK';
    
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        p_resultado := 'ERROR: Juego no encontrado.';
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

-- ============================================================
-- 3. FUNCIONES
-- ============================================================

-- 3a. Función: Calcular total del carrito de un usuario
CREATE OR REPLACE FUNCTION fn_total_carrito (
    p_usuario_id IN NUMBER
) RETURN NUMBER AS
    v_total NUMBER;
BEGIN
    SELECT NVL(SUM(v.precio), 0) INTO v_total
    FROM carrito c
    JOIN videojuego v ON c.id_juego = v.id_juego
    WHERE c.id_usuario = p_usuario_id;
    
    RETURN v_total;
END;
/

-- 3b. Función: Obtener promedio de calificación de un juego
CREATE OR REPLACE FUNCTION fn_promedio_calificacion (
    p_juego_id IN NUMBER
) RETURN NUMBER AS
    v_promedio NUMBER;
BEGIN
    SELECT NVL(AVG(puntuacion), 0) INTO v_promedio
    FROM calificaciones_part
    WHERE id_juego = p_juego_id;
    
    RETURN ROUND(v_promedio, 1);
END;
/

-- 3c. Función: Contar cuántos juegos tiene un usuario en su biblioteca
CREATE OR REPLACE FUNCTION fn_juegos_en_biblioteca (
    p_usuario_id IN NUMBER
) RETURN NUMBER AS
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM biblioteca
    WHERE id_usuario = p_usuario_id;
    
    RETURN v_count;
END;
/

-- ============================================================
-- 4. VISTAS
-- ============================================================

-- 4a. Vista: Catálogo público con promedio de calificación y géneros
CREATE OR REPLACE VIEW v_catalogo_publico AS
SELECT 
    v.id_juego,
    v.titulo,
    v.precio,
    v.fecha_lanzamiento,
    u.username AS empresa,
    fn_promedio_calificacion(v.id_juego) AS calificacion_promedio,
    (SELECT COUNT(*) FROM calificaciones_part cp WHERE cp.id_juego = v.id_juego) AS num_resenas,
    CASE WHEN v.trailer IS NOT NULL OR v.trailer_ruta IS NOT NULL THEN 1 ELSE 0 END AS tiene_trailer,
    (SELECT LISTAGG(g.nombre, ', ') WITHIN GROUP (ORDER BY g.nombre)
     FROM videojuego_genero vg
     JOIN genero g ON vg.id_genero = g.id_genero
     WHERE vg.id_juego = v.id_juego) AS generos
FROM videojuego v
JOIN usuario u ON v.id_empresa = u.id_usuario
WHERE v.estado = 'AP';

-- 4b. Vista: Actividad de compras (para el admin)
CREATE OR REPLACE VIEW v_actividad_compras AS
SELECT 
    p.id_pedido,
    u.username,
    u.email,
    p.total,
    p.estado,
    p.fecha_pedido,
    (SELECT COUNT(*) FROM detalle_pedido dp WHERE dp.id_pedido = p.id_pedido) AS num_juegos
FROM pedido p
JOIN usuario u ON p.id_usuario = u.id_usuario;

-- 4c. Vista: Resumen general de la plataforma
CREATE OR REPLACE VIEW v_resumen_plataforma AS
SELECT
    (SELECT COUNT(*) FROM usuario WHERE rol = 'USUARIO') AS total_usuarios,
    (SELECT COUNT(*) FROM usuario WHERE rol = 'EMPRESA') AS total_empresas,
    (SELECT COUNT(*) FROM pedido) AS total_pedidos,
    (SELECT NVL(SUM(total), 0) FROM pedido) AS ingresos_totales,
    (SELECT COUNT(*) FROM videojuego WHERE estado = 'AP') AS juegos_publicados,
    (SELECT COUNT(*) FROM videojuego WHERE estado = 'PE') AS juegos_pendientes,
    (SELECT COUNT(*) FROM videojuego WHERE estado = 'RE') AS juegos_rechazados
FROM DUAL;

-- 4d. Vista: Auditoría reciente
CREATE OR REPLACE VIEW v_auditoria_reciente AS
SELECT 
    a.id_auditoria,
    NVL(u.username, 'SISTEMA') AS usuario,
    a.accion,
    a.descripcion,
    TO_CHAR(a.fecha, 'DD/MM/YYYY HH24:MI:SS') AS fecha_formateada
FROM auditoria a
LEFT JOIN usuario u ON a.id_usuario = u.id_usuario
ORDER BY a.fecha DESC;

-- ============================================================
-- 5. TRIGGERS AVANZADOS (REGLAS DE NEGOCIO Y RESTRICCIONES)
-- ============================================================

-- 5a. Trigger de DELETE: Respaldo histórico automático antes de borrar
CREATE OR REPLACE TRIGGER trg_respaldo_delete_usuario
BEFORE DELETE ON usuario
FOR EACH ROW
BEGIN
    INSERT INTO usuario_eliminado (id_usuario, username, email, rol, fecha_registro)
    VALUES (:OLD.id_usuario, :OLD.username, :OLD.email, :OLD.rol, :OLD.fecha_registro);
    
    INSERT INTO auditoria (id_usuario, accion, descripcion)
    VALUES (NULL, 'ELIMINAR_USUARIO', 'Usuario ' || :OLD.username || ' (ID: ' || :OLD.id_usuario || ') eliminado del sistema.');
END;
/

-- 5b. Trigger de INSERT: Validar propiedad antes de calificar
CREATE OR REPLACE TRIGGER trg_validar_compra_resena
BEFORE INSERT ON calificaciones_part
FOR EACH ROW
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count 
    FROM biblioteca 
    WHERE id_usuario = :NEW.id_usuario AND id_juego = :NEW.id_juego;
    
    IF v_count = 0 THEN
        RAISE_APPLICATION_ERROR(-20002, 'REGLA DB: No puedes calificar un juego que no has comprado.');
    END IF;
END;
/

-- 5c. Trigger de UPDATE: Proteger integridad de juegos aprobados
CREATE OR REPLACE TRIGGER trg_proteger_juego_aprobado
BEFORE UPDATE ON videojuego
FOR EACH ROW
BEGIN
    IF :OLD.estado = 'AP' THEN
        -- No pueden cambiarle el título
        IF :OLD.titulo != :NEW.titulo THEN
            RAISE_APPLICATION_ERROR(-20003, 'REGLA DB: No se puede cambiar el titulo de un juego ya aprobado.');
        END IF;
        
        -- No pueden subir el precio más de un 20% de golpe
        IF :NEW.precio > (:OLD.precio * 1.20) THEN
            RAISE_APPLICATION_ERROR(-20004, 'REGLA DB: No se puede incrementar el precio mas del 20% en juegos aprobados.');
        END IF;
    END IF;
END;
/

-- ============================================================
-- FIN DE OBJETOS PL/SQL
-- ============================================================
