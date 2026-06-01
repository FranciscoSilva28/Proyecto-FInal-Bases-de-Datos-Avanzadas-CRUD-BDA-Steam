import oracledb
import os

# Credenciales actualizadas que coinciden con tu configuracion de Docker
DB_USER = os.environ.get("DB_USER", "proyecto_bda")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "AdminP123")
DB_DSN = os.environ.get("DB_DSN", "localhost:1521/FREEPDB1") 

pool = None

def init_pool():
    global pool
    try:
        pool = oracledb.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            dsn=DB_DSN,
            min=2,
            max=5,
            increment=1
        )
        print("Conexion a Oracle exitosa.")
    except Exception as e:
        print(f"Error al conectar a Oracle: {e}")

def get_connection():
    if not pool:
        init_pool()
    return pool.acquire()
