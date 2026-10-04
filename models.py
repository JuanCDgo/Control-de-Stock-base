"""
Capa de lógica de negocio y acceso a datos (Modelos / Servicios).
Implementa validaciones, reglas de negocio de precios, stock mínimo, imágenes,
transacciones atómicas de ventas, cuentas corrientes (clientes) y movimientos.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import sqlite3
from database import get_connection


# ==========================================
# EXCEPCIONES DE DOMINIO
# ==========================================
class BusinessLogicError(Exception):
    """Excepción base para errores de lógica de negocio."""
    pass


class InsufficientStockError(BusinessLogicError):
    """Lanzada cuando un producto no tiene suficiente stock para la venta."""
    pass


# ==========================================
# REGLAS DE PRECIOS
# ==========================================
def calcular_precio_venta(precio_costo: float, margen_ganancia: float) -> float:
    """
    Calcula el precio de venta sugerido en base al costo y margen porcentual.
    Fórmula: Costo * (1 + Margen / 100)
    """
    if precio_costo < 0 or margen_ganancia < 0:
        raise BusinessLogicError("El costo y el margen deben ser números no negativos.")
    return round(precio_costo * (1 + (margen_ganancia / 100.0)), 2)


# ==========================================
# GESTIÓN DE CATEGORÍAS
# ==========================================
def crear_categoria(nombre: str) -> int:
    """Crea una nueva categoría."""
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise BusinessLogicError("El nombre de la categoría no puede estar vacío.")

    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO categorias (nombre) VALUES (?);", (nombre_limpio,))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise BusinessLogicError(f"La categoría '{nombre_limpio}' ya existe.")


def obtener_categorias() -> List[Dict[str, Any]]:
    """Retorna todas las categorías ordenadas por nombre."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM categorias ORDER BY nombre ASC;")
        return [dict(row) for row in cursor.fetchall()]


def eliminar_categoria(categoria_id: int) -> bool:
    """Elimina una categoría por ID. Los productos asociados quedarán sin categoría (SET NULL)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categorias WHERE id = ?;", (categoria_id,))
        conn.commit()
        return cursor.rowcount > 0


# ==========================================
# GESTIÓN DE PRODUCTOS, IMÁGENES Y STOCK
# ==========================================
def crear_producto(
    codigo: str,
    nombre: str,
    categoria_id: Optional[int],
    precio_costo: float,
    margen_ganancia: float,
    usa_precio_manual: bool = False,
    precio_venta_manual: Optional[float] = None,
    stock_actual: int = 0,
    stock_minimo: int = 5,
    imagen_path: Optional[str] = None
) -> int:
    """
    Registra un nuevo producto calculando o asignando el precio de venta correspondiente,
    así como su umbral de stock mínimo y ruta de imagen opcional.
    """
    codigo = codigo.strip().upper()
    nombre = nombre.strip()
    if not codigo:
        raise BusinessLogicError("El código de producto es obligatorio.")
    if not nombre:
        raise BusinessLogicError("El nombre de producto es obligatorio.")
    if precio_costo < 0:
        raise BusinessLogicError("El precio de costo no puede ser negativo.")
    if stock_minimo < 0:
        raise BusinessLogicError("El stock mínimo no puede ser negativo.")

    if usa_precio_manual:
        if precio_venta_manual is None or precio_venta_manual < 0:
            raise BusinessLogicError("Debe indicar un precio de venta manual válido mayor o igual a 0.")
        precio_venta_final = round(precio_venta_manual, 2)
    else:
        precio_venta_final = calcular_precio_venta(precio_costo, margen_ganancia)

    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO productos (
                    codigo, nombre, categoria_id, precio_costo, 
                    margen_ganancia, precio_venta, usa_precio_manual,
                    stock_actual, stock_minimo, imagen_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                codigo,
                nombre,
                categoria_id,
                round(precio_costo, 2),
                round(margen_ganancia, 2),
                precio_venta_final,
                1 if usa_precio_manual else 0,
                int(stock_actual),
                int(stock_minimo),
                imagen_path
            ))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: productos.codigo" in str(e):
                raise BusinessLogicError(f"Ya existe un producto con el código / código de barras '{codigo}'.")
            raise BusinessLogicError(f"Error de base de datos: {e}")


def actualizar_producto(
    producto_id: int,
    codigo: str,
    nombre: str,
    categoria_id: Optional[int],
    precio_costo: float,
    margen_ganancia: float,
    usa_precio_manual: bool,
    precio_venta_manual: Optional[float] = None,
    stock_actual: Optional[int] = None,
    stock_minimo: Optional[int] = None,
    imagen_path: Optional[str] = None,
    eliminar_imagen: bool = False
) -> bool:
    """Actualiza datos, precios, inventario y ruta de imagen de un producto existente."""
    codigo = codigo.strip().upper()
    nombre = nombre.strip()
    if not codigo or not nombre:
        raise BusinessLogicError("Código y nombre son obligatorios.")

    if usa_precio_manual:
        if precio_venta_manual is None or precio_venta_manual < 0:
            raise BusinessLogicError("Debe ingresar un precio manual válido.")
        precio_venta_final = round(precio_venta_manual, 2)
    else:
        precio_venta_final = calcular_precio_venta(precio_costo, margen_ganancia)

    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT stock_actual, stock_minimo, imagen_path FROM productos WHERE id = ?;", (producto_id,))
            prod_actual = cursor.fetchone()
            if not prod_actual:
                raise BusinessLogicError("El producto no existe.")

            nuevo_stock_actual = int(stock_actual) if stock_actual is not None else prod_actual["stock_actual"]
            nuevo_stock_minimo = int(stock_minimo) if stock_minimo is not None else prod_actual["stock_minimo"]

            if eliminar_imagen:
                nueva_imagen_path = None
            elif imagen_path is not None:
                nueva_imagen_path = imagen_path
            else:
                nueva_imagen_path = prod_actual["imagen_path"]

            cursor.execute("""
                UPDATE productos SET
                    codigo = ?, nombre = ?, categoria_id = ?, precio_costo = ?,
                    margen_ganancia = ?, precio_venta = ?, usa_precio_manual = ?,
                    stock_actual = ?, stock_minimo = ?, imagen_path = ?
                WHERE id = ?;
            """, (
                codigo, nombre, categoria_id, round(precio_costo, 2),
                round(margen_ganancia, 2), precio_venta_final,
                1 if usa_precio_manual else 0,
                nuevo_stock_actual, nuevo_stock_minimo, nueva_imagen_path,
                producto_id
            ))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            raise BusinessLogicError(f"El código '{codigo}' ya está asignado a otro producto.")


def ajustar_stock(producto_id: int, nuevo_stock: int) -> bool:
    """Ajusta directamente el stock actual de un producto."""
    if nuevo_stock < 0:
        raise BusinessLogicError("El stock no puede ser un número negativo.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE productos SET stock_actual = ? WHERE id = ?;", (nuevo_stock, producto_id))
        conn.commit()
        return cursor.rowcount > 0


def actualizar_stock_minimo(producto_id: int, nuevo_stock_minimo: int) -> bool:
    """Modifica el umbral de stock mínimo para alertas tempranas."""
    if nuevo_stock_minimo < 0:
        raise BusinessLogicError("El stock mínimo no puede ser negativo.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE productos SET stock_minimo = ? WHERE id = ?;", (nuevo_stock_minimo, producto_id))
        conn.commit()
        return cursor.rowcount > 0


def actualizar_imagen_producto(producto_id: int, nueva_ruta_imagen: str) -> bool:
    """Actualiza la ruta de la foto de un producto."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE productos SET imagen_path = ? WHERE id = ?;", (nueva_ruta_imagen, producto_id))
        conn.commit()
        return cursor.rowcount > 0


def eliminar_producto(producto_id: int) -> bool:
    """Elimina un producto siempre que no tenga ventas históricas asociadas."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM detalle_ventas WHERE producto_id = ?;", (producto_id,))
        if cursor.fetchone()["count"] > 0:
            raise BusinessLogicError("No se puede eliminar un producto con historial de ventas registrado.")

        cursor.execute("DELETE FROM productos WHERE id = ?;", (producto_id,))
        conn.commit()
        return cursor.rowcount > 0


def obtener_productos(busqueda: Optional[str] = None, categoria_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Obtiene el listado de productos con datos de su categoría, stock mínimo y ruta de imagen."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                p.id, p.codigo, p.nombre, p.categoria_id,
                COALESCE(c.nombre, 'Sin categoría') as categoria_nombre,
                p.precio_costo, p.margen_ganancia, p.precio_venta,
                p.usa_precio_manual, p.stock_actual, p.stock_minimo,
                p.imagen_path
            FROM productos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE 1=1
        """
        params: List[Any] = []

        if busqueda:
            query += " AND (p.nombre LIKE ? OR p.codigo LIKE ?)"
            term = f"%{busqueda.strip()}%"
            params.extend([term, term])

        if categoria_id is not None:
            query += " AND p.categoria_id = ?"
            params.append(categoria_id)

        query += " ORDER BY p.nombre ASC;"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def obtener_producto_por_id(producto_id: int) -> Optional[Dict[str, Any]]:
    """Retorna un producto por su clave primaria."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM productos WHERE id = ?;", (producto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def obtener_producto_por_codigo(codigo: str) -> Optional[Dict[str, Any]]:
    """
    Busca un producto por coincidencia exacta con su código de barras o SKU (insensible a mayúsculas).
    Ideal para lecturas de lector óptico EAN / UPC.
    """
    if not codigo:
        return None
    codigo_limpio = codigo.strip().upper()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                p.id, p.codigo, p.nombre, p.categoria_id,
                COALESCE(c.nombre, 'Sin categoría') as categoria_nombre,
                p.precio_costo, p.margen_ganancia, p.precio_venta,
                p.usa_precio_manual, p.stock_actual, p.stock_minimo,
                p.imagen_path
            FROM productos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE UPPER(p.codigo) = ?;
        """, (codigo_limpio,))
        row = cursor.fetchone()
        return dict(row) if row else None


def obtener_productos_bajo_stock() -> List[Dict[str, Any]]:
    """
    Retorna los productos cuyo stock actual sea menor o igual a su stock mínimo configurado.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                p.id, p.codigo, p.nombre, p.categoria_id,
                COALESCE(c.nombre, 'Sin categoría') as categoria_nombre,
                p.stock_actual, p.stock_minimo, p.precio_costo, p.precio_venta,
                p.imagen_path,
                (p.stock_minimo - p.stock_actual) as deficit
            FROM productos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.stock_actual <= p.stock_minimo
            ORDER BY deficit DESC, p.stock_actual ASC;
        """)
        return [dict(row) for row in cursor.fetchall()]


# ==========================================
# GESTIÓN DE CLIENTES Y CUENTAS CORRIENTES ("LA LIBRETA")
# ==========================================
def crear_cliente(nombre: str, telefono: str = "", email: str = "", limite_credito: float = 0.0) -> int:
    """Registra un nuevo cliente con límite de crédito opcional."""
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise BusinessLogicError("El nombre del cliente es obligatorio.")
    if limite_credito < 0:
        raise BusinessLogicError("El límite de crédito no puede ser negativo.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clientes (nombre, telefono, email, saldo_deudor, limite_credito)
            VALUES (?, ?, ?, 0.0, ?);
        """, (nombre_limpio, telefono.strip(), email.strip().lower(), round(limite_credito, 2)))
        conn.commit()
        return cursor.lastrowid


def actualizar_cliente(cliente_id: int, nombre: str, telefono: str, email: str, limite_credito: float) -> bool:
    """Actualiza datos personales y límite de crédito de un cliente."""
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise BusinessLogicError("El nombre del cliente es obligatorio.")
    if limite_credito < 0:
        raise BusinessLogicError("El límite de crédito no puede ser negativo.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clientes 
            SET nombre = ?, telefono = ?, email = ?, limite_credito = ?
            WHERE id = ?;
        """, (nombre_limpio, telefono.strip(), email.strip().lower(), round(limite_credito, 2), cliente_id))
        conn.commit()
        return cursor.rowcount > 0


def eliminar_cliente(cliente_id: int) -> bool:
    """Elimina un cliente solo si no tiene saldo deudor pendiente."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT saldo_deudor FROM clientes WHERE id = ?;", (cliente_id,))
        cliente = cursor.fetchone()
        if not cliente:
            raise BusinessLogicError("El cliente no existe.")
        if cliente["saldo_deudor"] > 0:
            raise BusinessLogicError(f"No se puede eliminar un cliente con deuda pendiente (${cliente['saldo_deudor']:,.2f}).")

        cursor.execute("DELETE FROM clientes WHERE id = ?;", (cliente_id,))
        conn.commit()
        return cursor.rowcount > 0


def obtener_clientes(busqueda: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retorna clientes ordenados por mayor saldo deudor y luego por nombre."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT id, nombre, telefono, email, saldo_deudor, limite_credito FROM clientes WHERE 1=1"
        params: List[Any] = []
        if busqueda:
            query += " AND (nombre LIKE ? OR telefono LIKE ?)"
            term = f"%{busqueda.strip()}%"
            params.extend([term, term])
        query += " ORDER BY saldo_deudor DESC, nombre ASC;"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def obtener_cliente_por_id(cliente_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene un cliente por ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clientes WHERE id = ?;", (cliente_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def registrar_abono_cliente(
    cliente_id: int,
    monto: float,
    metodo_pago: str = "Efectivo",
    descripcion: Optional[str] = None
) -> int:
    """
    Registra un pago / abono a la cuenta corriente del cliente:
    - Valida que el monto sea positivo.
    - Reduce el saldo_deudor del cliente.
    - Registra el movimiento con tipo 'PAGO'.
    - Transacción atómica.
    """
    if monto <= 0:
        raise BusinessLogicError("El monto del abono debe ser mayor a 0.")

    monto_redondeado = round(monto, 2)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")

        cursor.execute("SELECT id, nombre, saldo_deudor FROM clientes WHERE id = ?;", (cliente_id,))
        cli = cursor.fetchone()
        if not cli:
            raise BusinessLogicError("Cliente no encontrado.")

        saldo_actual = cli["saldo_deudor"]
        nuevo_saldo = max(0.0, round(saldo_actual - monto_redondeado, 2))

        # Registrar movimiento de cuenta
        desc = descripcion.strip() if descripcion else f"Abono a cuenta corriente ({metodo_pago})"
        cursor.execute("""
            INSERT INTO movimientos_cuenta (cliente_id, tipo, monto, descripcion)
            VALUES (?, 'PAGO', ?, ?);
        """, (cliente_id, monto_redondeado, desc))
        mov_id = cursor.lastrowid

        # Actualizar saldo del cliente
        cursor.execute("UPDATE clientes SET saldo_deudor = ? WHERE id = ?;", (nuevo_saldo, cliente_id))

        conn.commit()
        return mov_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def obtener_movimientos_cliente(cliente_id: int) -> List[Dict[str, Any]]:
    """Retorna la lista de cargos y abonos ordenados cronológicamente."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, cliente_id, fecha_hora, tipo, monto, descripcion, ticket_id
            FROM movimientos_cuenta
            WHERE cliente_id = ?
            ORDER BY id DESC;
        """, (cliente_id,))
        return [dict(row) for row in cursor.fetchall()]


def obtener_resumen_deuda_total() -> Dict[str, Any]:
    """Calcula el total de deuda activa en la calle y la cantidad de clientes deudores."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(SUM(saldo_deudor), 0.0) as total_deuda,
                COUNT(id) as total_clientes,
                SUM(CASE WHEN saldo_deudor > 0 THEN 1 ELSE 0 END) as clientes_con_deuda
            FROM clientes;
        """)
        row = cursor.fetchone()
        return {
            "total_deuda": round(row["total_deuda"], 2),
            "total_clientes": row["total_clientes"],
            "clientes_con_deuda": row["clientes_con_deuda"] or 0
        }


# ==========================================
# REGISTRO DE VENTAS (TRANSACCIÓN ATÓMICA CON SOPORTE DE FIADO)
# ==========================================
def registrar_venta(
    items: List[Dict[str, Any]],
    forma_pago: str,
    cliente_id: Optional[int] = None
) -> int:
    """
    Registra una venta de manera atómica (ACID):
    - Valida disponibilidad de stock antes de cualquier cambio.
    - Si es 'Cuenta Corriente / Fiado', valida existencia del cliente y límite de crédito.
    - Inserta cabecera en `ventas` vinculando opcionalmente cliente_id.
    - Inserta renglones en `detalle_ventas` congelando precio y costo unitario.
    - Descuenta del inventario `stock_actual` para cada producto.
    - Si es Fiado, incrementa el `saldo_deudor` del cliente y genera un 'CARGO' en `movimientos_cuenta`.
    - Rollback completo si ocurre cualquier falla.
    """
    if not items:
        raise BusinessLogicError("El carrito de venta no contiene ningún producto.")

    forma_pago_limpia = forma_pago.strip()
    if not forma_pago_limpia:
        raise BusinessLogicError("Debe seleccionar una forma de pago válida.")

    es_fiado = forma_pago_limpia == "Cuenta Corriente / Fiado"
    if es_fiado and not cliente_id:
        raise BusinessLogicError("Para ventas en 'Cuenta Corriente / Fiado' debe seleccionar un cliente.")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")

        total_venta = 0.0
        detalles_a_insertar = []

        for item in items:
            p_id = item["producto_id"]
            cantidad = item["cantidad"]

            if cantidad <= 0:
                raise BusinessLogicError("La cantidad para cada producto debe ser mayor a 0.")

            cursor.execute("""
                SELECT id, codigo, nombre, precio_costo, precio_venta, stock_actual 
                FROM productos WHERE id = ?;
            """, (p_id,))
            prod = cursor.fetchone()

            if not prod:
                raise BusinessLogicError(f"El producto con ID {p_id} ya no existe en el sistema.")

            if prod["stock_actual"] < cantidad:
                raise InsufficientStockError(
                    f"Stock insuficiente para '{prod['nombre']}' (Código: {prod['codigo']}). "
                    f"Stock disponible: {prod['stock_actual']}, Solicitado: {cantidad}."
                )

            subtotal = round(prod["precio_venta"] * cantidad, 2)
            total_venta += subtotal

            detalles_a_insertar.append({
                "producto_id": prod["id"],
                "cantidad": cantidad,
                "precio_unitario": prod["precio_venta"],
                "costo_unitario": prod["precio_costo"],
                "stock_restante": prod["stock_actual"] - cantidad
            })

        total_venta = round(total_venta, 2)

        # Validación de Límite de Crédito del Cliente para Fiado
        if es_fiado:
            cursor.execute("SELECT id, nombre, saldo_deudor, limite_credito FROM clientes WHERE id = ?;", (cliente_id,))
            cli = cursor.fetchone()
            if not cli:
                raise BusinessLogicError("El cliente seleccionado no existe.")

            nuevo_saldo_previsto = round(cli["saldo_deudor"] + total_venta, 2)
            if cli["limite_credito"] > 0 and nuevo_saldo_previsto > cli["limite_credito"]:
                raise BusinessLogicError(
                    f"Límite de Crédito Excedido para '{cli['nombre']}': "
                    f"Saldo actual: ${cli['saldo_deudor']:,.2f} + Venta: ${total_venta:,.2f} = "
                    f"${nuevo_saldo_previsto:,.2f} (Límite máximo permitido: ${cli['limite_credito']:,.2f})."
                )

        # 1. Registrar venta en la cabecera
        cursor.execute("""
            INSERT INTO ventas (total_venta, forma_pago, cliente_id)
            VALUES (?, ?, ?);
        """, (total_venta, forma_pago_limpia, cliente_id))
        venta_id = cursor.lastrowid

        # 2. Registrar renglones de detalle y descontar stock
        for det in detalles_a_insertar:
            cursor.execute("""
                INSERT INTO detalle_ventas (
                    venta_id, producto_id, cantidad, precio_unitario, costo_unitario
                ) VALUES (?, ?, ?, ?, ?);
            """, (
                venta_id,
                det["producto_id"],
                det["cantidad"],
                det["precio_unitario"],
                det["costo_unitario"]
            ))

            cursor.execute("""
                UPDATE productos 
                SET stock_actual = ? 
                WHERE id = ?;
            """, (det["stock_restante"], det["producto_id"]))

        # 3. Si es Fiado, registrar Cargo en cuenta corriente y actualizar saldo deudor
        if es_fiado and cliente_id:
            cursor.execute("""
                UPDATE clientes 
                SET saldo_deudor = saldo_deudor + ? 
                WHERE id = ?;
            """, (total_venta, cliente_id))

            cursor.execute("""
                INSERT INTO movimientos_cuenta (cliente_id, tipo, monto, descripcion, ticket_id)
                VALUES (?, 'CARGO', ?, ?, ?);
            """, (
                cliente_id,
                total_venta,
                f"Compra Fiada - Ticket #{venta_id}",
                venta_id
            ))

        conn.commit()
        return venta_id

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ==========================================
# CONTROL DIARIO Y ARQUEO DE CAJA
# ==========================================
def obtener_arqueo_caja(fecha_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Calcula el resumen financiero para una fecha específica (formato 'YYYY-MM-DD').
    """
    if not fecha_str:
        fecha_str = datetime.now().strftime("%Y-%m-%d")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                forma_pago,
                COUNT(id) as operaciones,
                COALESCE(SUM(total_venta), 0.0) as total
            FROM ventas
            WHERE date(fecha_hora) = date(?)
            GROUP BY forma_pago
            ORDER BY total DESC;
        """, (fecha_str,))
        desglose = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT 
                COUNT(id) as total_operaciones,
                COALESCE(SUM(total_venta), 0.0) as total_ventas
            FROM ventas
            WHERE date(fecha_hora) = date(?);
        """, (fecha_str,))
        resumen_gral = cursor.fetchone()
        total_ventas = resumen_gral["total_ventas"]
        total_operaciones = resumen_gral["total_operaciones"]

        cursor.execute("""
            SELECT 
                COALESCE(SUM(d.cantidad * (d.precio_unitario - d.costo_unitario)), 0.0) as ganancia_estimada
            FROM detalle_ventas d
            INNER JOIN ventas v ON d.venta_id = v.id
            WHERE date(v.fecha_hora) = date(?);
        """, (fecha_str,))
        ganancia_estimada = round(cursor.fetchone()["ganancia_estimada"], 2)

        cursor.execute("""
            SELECT v.id, v.fecha_hora, v.total_venta, v.forma_pago, c.nombre as cliente_nombre
            FROM ventas v
            LEFT JOIN clientes c ON v.cliente_id = c.id
            WHERE date(v.fecha_hora) = date(?)
            ORDER BY v.id DESC;
        """, (fecha_str,))
        ventas_dia = [dict(row) for row in cursor.fetchall()]

        return {
            "fecha": fecha_str,
            "total_vendido": round(total_ventas, 2),
            "ganancia_estimada": ganancia_estimada,
            "total_operaciones": total_operaciones,
            "desglose_por_forma_pago": desglose,
            "ventas": ventas_dia
        }


def obtener_detalle_de_venta(venta_id: int) -> List[Dict[str, Any]]:
    """Obtiene los renglones de una venta con los nombres de productos y subtotales."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                d.id, d.producto_id, p.codigo, p.nombre,
                d.cantidad, d.precio_unitario, d.costo_unitario,
                (d.cantidad * d.precio_unitario) as subtotal,
                (d.cantidad * (d.precio_unitario - d.costo_unitario)) as margen_obtenido
            FROM detalle_ventas d
            INNER JOIN productos p ON d.producto_id = p.id
            WHERE d.venta_id = ?
            ORDER BY d.id ASC;
        """, (venta_id,))
        return [dict(row) for row in cursor.fetchall()]


# ==========================================
# RESET DE FÁBRICA / LIMPIEZA DE DATOS
# ==========================================
def vaciar_base_de_datos(
    limpiar_ventas: bool = True,
    limpiar_clientes: bool = True,
    limpiar_productos: bool = False,
    uploads_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ejecuta el vaciado y reinicio selectivo de tablas en SQLite,
    restableciendo a 1 los contadores de IDs en sqlite_sequence.
    Si limpiar_productos es True, borra también los archivos de fotos de productos en uploads_dir.
    """
    resumen = {
        "ventas_borradas": False,
        "clientes_borrados": False,
        "productos_borrados": False,
        "fotos_eliminadas": 0
    }

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")

        # Desactivar temporalmente foreign keys para permitir vaciado en cualquier combinación elegida
        cursor.execute("PRAGMA foreign_keys = OFF;")

        tablas_a_reiniciar = []

        # 1. Limpieza de Ventas y Tickets
        if limpiar_ventas:
            cursor.execute("DELETE FROM detalle_ventas;")
            cursor.execute("DELETE FROM ventas;")
            # Si no se borran los clientes, limpiar cargos de compras fiadas y poner saldo deudor a 0
            if not limpiar_clientes:
                cursor.execute("DELETE FROM movimientos_cuenta WHERE ticket_id IS NOT NULL;")
                cursor.execute("UPDATE clientes SET saldo_deudor = 0.0;")
            tablas_a_reiniciar.extend(["ventas", "detalle_ventas"])
            resumen["ventas_borradas"] = True

        # 2. Limpieza de Clientes y Cuentas Corrientes
        if limpiar_clientes:
            cursor.execute("DELETE FROM movimientos_cuenta;")
            cursor.execute("DELETE FROM clientes;")
            cursor.execute("UPDATE ventas SET cliente_id = NULL;")
            tablas_a_reiniciar.extend(["clientes", "movimientos_cuenta"])
            resumen["clientes_borrados"] = True

        # 3. Limpieza de Catálogo de Productos y Categorías
        if limpiar_productos:
            cursor.execute("DELETE FROM detalle_ventas;")
            cursor.execute("DELETE FROM productos;")
            cursor.execute("DELETE FROM categorias;")
            tablas_a_reiniciar.extend(["productos", "categorias", "detalle_ventas"])
            resumen["productos_borrados"] = True

            # Borrar archivos de fotos de productos de la carpeta /static/uploads (preservando el qr_pago)
            if uploads_dir and os.path.exists(uploads_dir):
                conteo_fotos = 0
                for arch in os.listdir(uploads_dir):
                    if arch.startswith("prod_") or (arch.lower().endswith((".jpg", ".jpeg", ".png")) and not arch.startswith("qr_")):
                        try:
                            os.remove(os.path.join(uploads_dir, arch))
                            conteo_fotos += 1
                        except Exception:
                            pass
                resumen["fotos_eliminadas"] = conteo_fotos

        # Reiniciar contadores autoincrementales en sqlite_sequence
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';")
        if cursor.fetchone():
            for t_nombre in set(tablas_a_reiniciar):
                cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?;", (t_nombre,))

        # Reactivar foreign keys y confirmar transacción
        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
        return resumen

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
