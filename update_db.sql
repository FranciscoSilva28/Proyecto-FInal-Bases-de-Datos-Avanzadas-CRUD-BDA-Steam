ALTER TABLE videojuego ADD (modo_almacenamiento VARCHAR2(4) DEFAULT 'BLOB' CHECK (modo_almacenamiento IN ('BLOB','RUTA')), portada_ruta VARCHAR2(500), trailer_ruta VARCHAR2(500));
EXIT;
