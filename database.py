"""
Configuración y conexión a la base de datos SQLite.
Maneja la inicialización del esquema, claves foráneas, índices y migraciones de esquema
incluyendo Productos, Categorías, Ventas, Cuentas Corrientes (Clientes) y Movimientos.
"""
import sqlite3
import os
from typing import Optional

# Ruta de la base de datos (por defecto en el mismo directorio del proyecto)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gestion_negocio.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Obtiene una conexión a la base de datos SQLite configurada adecuadamente:
    - row_factory = sqlite3.Row para acceder a columnas por nombre.
    - PRAGMA foreign_keys = ON para asegurar integridad referencial.
    - PRAGMA journal_mode = WAL para mejorar la concurrencia y velocidad.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Inicializa el esquema de base de datos creando las tablas e índices necesarios.
    Incluye lógica de migración para bases de datos existentes (IF NOT EXISTS y ALTER TABLE).
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # 1. Tabla Categorías
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE COLLATE NOCASE
            );
        """)

        # 2. Tabla Clientes / Cuentas Corrientes ("La Libreta")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL COLLATE NOCASE,
                telefono TEXT,
                email TEXT,
                saldo_deudor REAL NOT NULL DEFAULT 0.0 CHECK(saldo_deudor >= 0),
                limite_credito REAL NOT NULL DEFAULT 0.0 CHECK(limite_credito >= 0)
            );
        """)

        # 3. Tabla Productos (con stock_minimo e imagen_path, codigo funciona como Código de Barras / SKU)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                categoria_id INTEGER,
                precio_costo REAL NOT NULL DEFAULT 0.0 CHECK(precio_costo >= 0),
                margen_ganancia REAL NOT NULL DEFAULT 0.0,
                precio_venta REAL NOT NULL DEFAULT 0.0 CHECK(precio_venta >= 0),
                usa_precio_manual INTEGER NOT NULL DEFAULT 0 CHECK(usa_precio_manual IN (0, 1)),
                stock_actual INTEGER NOT NULL DEFAULT 0,
                stock_minimo INTEGER NOT NULL DEFAULT 5 CHECK(stock_minimo >= 0),
                imagen_path TEXT,
                FOREIGN KEY (categoria_id) REFERENCES categorias (id) ON DELETE SET NULL
            );
        """)

        # Migración limpia de columnas para productos
        cursor.execute("PRAGMA table_info(productos);")
        columnas_prods = {col["name"] for col in cursor.fetchall()}

        if "stock_minimo" not in columnas_prods:
            cursor.execute("ALTER TABLE productos ADD COLUMN stock_minimo INTEGER NOT NULL DEFAULT 5 CHECK(stock_minimo >= 0);")

        if "imagen_path" not in columnas_prods:
            cursor.execute("ALTER TABLE productos ADD COLUMN imagen_path TEXT;")

        # 4. Tabla Ventas (Cabecera, con soporte para cliente_id en ventas fiadas/cuenta corriente)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_hora TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                total_venta REAL NOT NULL CHECK(total_venta >= 0),
                forma_pago TEXT NOT NULL,
                cliente_id INTEGER,
                FOREIGN KEY (cliente_id) REFERENCES clientes (id) ON DELETE SET NULL
            );
        """)

        # Migración para ventas: verificar si existe cliente_id
        cursor.execute("PRAGMA table_info(ventas);")
        columnas_ventas = {col["name"] for col in cursor.fetchall()}
        if "cliente_id" not in columnas_ventas:
            cursor.execute("ALTER TABLE ventas ADD COLUMN cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL;")

        # 5. Tabla Detalle de Ventas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detalle_ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad INTEGER NOT NULL CHECK(cantidad > 0),
                precio_unitario REAL NOT NULL CHECK(precio_unitario >= 0),
                costo_unitario REAL NOT NULL CHECK(costo_unitario >= 0),
                FOREIGN KEY (venta_id) REFERENCES ventas (id) ON DELETE CASCADE,
                FOREIGN KEY (producto_id) REFERENCES productos (id)
            );
        """)

        # 6. Tabla Movimientos de Cuenta Corriente (Cargos por compras fiadas y Pagos/Abonos)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movimientos_cuenta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                fecha_hora TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                tipo TEXT NOT NULL CHECK(tipo IN ('CARGO', 'PAGO')),
                monto REAL NOT NULL CHECK(monto > 0),
                descripcion TEXT,
                ticket_id INTEGER,
                FOREIGN KEY (cliente_id) REFERENCES clientes (id) ON DELETE CASCADE,
                FOREIGN KEY (ticket_id) REFERENCES ventas (id) ON DELETE SET NULL
            );
        """)

        # Índices para optimizar búsquedas frecuentes, códigos de barra y reportes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_codigo ON productos(codigo);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha_hora);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_detalle_venta_id ON detalle_ventas(venta_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_detalle_producto_id ON detalle_ventas(producto_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_nombre ON clientes(nombre);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_cliente ON movimientos_cuenta(cliente_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos_cuenta(fecha_hora);")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada y migrada con soporte de Clientes y Códigos de Barras.")
