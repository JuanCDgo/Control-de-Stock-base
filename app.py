"""
Interfaz de usuario con Streamlit para el Sistema de Gestión Interna.
Organizado en 6 módulos principales:
1. 🛒 Punto de Venta (POS) con Lector de Código de Barras, QR y Cuenta Corriente / Fiado
2. 👥 Cuentas Corrientes / Clientes ("La Libreta" de fiados, abonos y límites)
3. 📦 Productos e Inventario (Catálogo, Carga con Fotos, Edición Completa, Ajustes y Alertas)
4. 🏷️ Categorías
5. 📊 Arqueo de Caja y Cierre Diario en PDF / WhatsApp / Correo
6. ⚙️ Configuración del Negocio (Datos Bancarios, QR y SMTP)
"""
import os
import urllib.parse
import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Optional

from database import init_db
import models
import reportes
from config_manager import (
    cargar_configuracion,
    guardar_configuracion,
    validar_clave_admin,
    cambiar_clave_admin
)

# Configuración del directorio base y carpetas estáticas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Configuración general de la página Streamlit
st.set_page_config(
    page_title="Sistema de Gestión Comercial",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar y migrar la base de datos automáticamente
init_db()

# Cargar configuración global del negocio
config_negocio = cargar_configuracion()

# Inicialización de estado de sesión para el carrito de compras
if "carrito" not in st.session_state:
    st.session_state.carrito = []


# ==============================================================================
# FUNCIONES AUXILIARES PARA ARCHIVOS DE IMÁGENES
# ==============================================================================
def guardar_archivo_imagen(uploaded_file, prefijo: str = "img") -> Optional[str]:
    """Guarda una imagen subida en /static/uploads y retorna su ruta relativa."""
    if uploaded_file is None:
        return None

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        return None

    prefijo_limpio = "".join(c for c in prefijo if c.isalnum() or c in ("-", "_")).lower()
    timestamp = int(datetime.now().timestamp() * 1000)
    nombre_archivo = f"{prefijo_limpio}_{timestamp}{ext}"
    ruta_absoluta = os.path.join(UPLOADS_DIR, nombre_archivo)

    with open(ruta_absoluta, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return os.path.join("static", "uploads", nombre_archivo).replace("\\", "/")


def obtener_ruta_imagen_absoluta(ruta_relativa: Optional[str]) -> Optional[str]:
    """Valida la existencia de la imagen en disco y devuelve su ruta absoluta."""
    if not ruta_relativa:
        return None
    ruta_abs = os.path.join(BASE_DIR, ruta_relativa)
    return ruta_abs if os.path.exists(ruta_abs) else None


# ==============================================================================
# BARRA LATERAL (NAVEGACIÓN Y ALERTAS GLOBALES)
# ==============================================================================
st.sidebar.title(f"🏪 {config_negocio.get('nombre_negocio', 'Mi Comercio')}")
st.sidebar.caption("Gestión Integral, POS, Clientes, Inventario & Caja")

modulo = st.sidebar.radio(
    "Navegación",
    [
        "🛒 Punto de Venta (POS)",
        "👥 Cuentas Corrientes / Clientes",
        "📦 Productos e Inventario",
        "🏷️ Categorías",
        "📊 Arqueo de Caja / Control Diario",
        "⚙️ Configuración del Negocio"
    ]
)

st.sidebar.markdown("---")

# Alertas globales en la barra lateral
prods_criticos_global = models.obtener_productos_bajo_stock()
if prods_criticos_global:
    st.sidebar.error(f"🚨 **Stock Crítico:** {len(prods_criticos_global)} producto(s) en o bajo el mínimo.")
    with st.sidebar.expander("🔎 Ver artículos en alerta"):
        for p_crit in prods_criticos_global:
            st.markdown(
                f"- **{p_crit['nombre']}** (`{p_crit['codigo']}`): "
                f"<span style='color:red;'><b>{p_crit['stock_actual']}</b></span> / mín. {p_crit['stock_minimo']}",
                unsafe_allow_html=True
            )
else:
    st.sidebar.success("✅ Todos los productos tienen stock saludable.")

# KPI rápido de Deuda en la calle en la barra lateral
resumen_deuda_sidebar = models.obtener_resumen_deuda_total()
if resumen_deuda_sidebar["total_deuda"] > 0:
    st.sidebar.warning(f"💸 **Deuda en Clientes:** ${resumen_deuda_sidebar['total_deuda']:,.2f}")


# ==============================================================================
# MÓDULO 1: PUNTO DE VENTA (POS) CON LECTOR DE BARRAS & CUENTA CORRIENTE
# ==============================================================================
if modulo == "🛒 Punto de Venta (POS)":
    st.header("🛒 Terminal de Punto de Venta")

    # 1. INTEGRACIÓN CON LECTORA DE CÓDIGO DE BARRAS (EAN / SKU)
    with st.form("form_barcode_scanner", clear_on_submit=True):
        col_scan_txt, col_scan_btn = st.columns([3.5, 1], gap="small")
        with col_scan_txt:
            barcode_in = st.text_input(
                "🔍 Escanear Código de Barras (EAN / SKU):",
                placeholder="Pase el lector óptico aquí o ingrese el código y presione Enter...",
                key="barcode_scanner_field"
            )
        with col_scan_btn:
            st.write("")
            btn_scan = st.form_submit_button("⚡ Cargar por Código", use_container_width=True)

        if btn_scan and barcode_in:
            prod_esc = models.obtener_producto_por_codigo(barcode_in)
            if not prod_esc:
                st.error(f"❌ Código '{barcode_in}' no registrado en el catálogo.")
            else:
                cant_en_cart = sum(it["cantidad"] for it in st.session_state.carrito if it["producto_id"] == prod_esc["id"])
                if prod_esc["stock_actual"] - cant_en_cart <= 0:
                    st.error(f"❌ Stock insuficiente para '{prod_esc['nombre']}' (Stock actual: {prod_esc['stock_actual']}).")
                else:
                    encontrado = False
                    for it in st.session_state.carrito:
                        if it["producto_id"] == prod_esc["id"]:
                            it["cantidad"] += 1
                            it["subtotal"] = round(it["cantidad"] * it["precio_unitario"], 2)
                            encontrado = True
                            break
                    if not encontrado:
                        st.session_state.carrito.append({
                            "producto_id": prod_esc["id"],
                            "codigo": prod_esc["codigo"],
                            "nombre": prod_esc["nombre"],
                            "precio_unitario": prod_esc["precio_venta"],
                            "cantidad": 1,
                            "subtotal": round(prod_esc["precio_venta"], 2),
                            "imagen_path": prod_esc.get("imagen_path")
                        })
                    st.toast(f"🛒 Agregado: {prod_esc['nombre']} x1 ($ {prod_esc['precio_venta']:,.2f})", icon="📦")
                    st.rerun()

    st.markdown("---")

    col_izq, col_der = st.columns([1.2, 1.3], gap="large")

    with col_izq:
        st.subheader("Búsqueda Manual de Producto")
        productos_db = models.obtener_productos()

        if not productos_db:
            st.warning("⚠️ No hay productos registrados. Por favor, agregue productos en la sección de Inventario.")
        else:
            opciones_productos = {
                f"[{p['codigo']}] {p['nombre']} - ${p['precio_venta']:,.2f}": p
                for p in productos_db
            }

            prod_seleccionado_label = st.selectbox(
                "Seleccionar de la lista:",
                options=list(opciones_productos.keys())
            )
            prod_info = opciones_productos[prod_seleccionado_label]

            # Ficha visual del producto
            with st.container(border=True):
                col_foto, col_datos = st.columns([1, 2])
                with col_foto:
                    img_abs = obtener_ruta_imagen_absoluta(prod_info.get("imagen_path"))
                    if img_abs:
                        st.image(img_abs, caption=prod_info["nombre"], use_container_width=True)
                    else:
                        st.markdown(
                            """
                            <div style="border: 2px dashed #bbb; border-radius: 8px; padding: 25px 5px; text-align: center; color: #888;">
                                📷<br><small>Sin foto</small>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                with col_datos:
                    st.markdown(f"#### {prod_info['nombre']}")
                    st.markdown(f"**Código / Barra:** `{prod_info['codigo']}` | **Categoría:** {prod_info['categoria_nombre']}")
                    st.markdown(f"### Precio: **${prod_info['precio_venta']:,.2f}**")

                stock_actual = prod_info["stock_actual"]
                stock_minimo = prod_info["stock_minimo"]

                if stock_actual <= stock_minimo:
                    st.error(
                        f"🚨 **¡ALERTA DE STOCK CRÍTICO!**<br>"
                        f"Stock disponible: **{stock_actual}** unidades (Umbral mínimo: **{stock_minimo}**).",
                        icon="⚠️"
                    )
                else:
                    st.success(f"✅ Stock disponible: **{stock_actual}** unidades (Mínimo: {stock_minimo})")

            cant_en_carrito = sum(
                item["cantidad"] for item in st.session_state.carrito if item["producto_id"] == prod_info["id"]
            )
            disponible_para_agregar = stock_actual - cant_en_carrito

            col_cant, col_btn = st.columns([1, 1.2])
            with col_cant:
                cantidad = st.number_input(
                    "Cantidad a vender",
                    min_value=1,
                    max_value=max(1, disponible_para_agregar) if disponible_para_agregar > 0 else 1,
                    value=1,
                    step=1
                )

            with col_btn:
                st.write("")
                st.write("")
                deshabilitar_agregar = disponible_para_agregar <= 0
                if st.button("➕ Agregar al Carrito", disabled=deshabilitar_agregar, use_container_width=True):
                    if disponible_para_agregar <= 0:
                        st.error("No hay más unidades disponibles de este producto.")
                    else:
                        encontrado = False
                        for item in st.session_state.carrito:
                            if item["producto_id"] == prod_info["id"]:
                                item["cantidad"] += cantidad
                                item["subtotal"] = round(item["cantidad"] * item["precio_unitario"], 2)
                                encontrado = True
                                break
                        if not encontrado:
                            st.session_state.carrito.append({
                                "producto_id": prod_info["id"],
                                "codigo": prod_info["codigo"],
                                "nombre": prod_info["nombre"],
                                "precio_unitario": prod_info["precio_venta"],
                                "cantidad": cantidad,
                                "subtotal": round(prod_info["precio_venta"] * cantidad, 2),
                                "imagen_path": prod_info.get("imagen_path")
                            })
                        st.rerun()

    # Panel derecho: Carrito de compras, Medio de pago y Cobro
    with col_der:
        st.subheader("Carrito Actual")

        if not st.session_state.carrito:
            st.info("El carrito está vacío. Agregue artículos escaneando o desde el panel izquierdo.")
        else:
            for idx, item in enumerate(st.session_state.carrito):
                with st.container(border=True):
                    c_img, c_info, c_sub, c_del = st.columns([0.8, 2.5, 1.5, 0.7])
                    with c_img:
                        img_item = obtener_ruta_imagen_absoluta(item.get("imagen_path"))
                        if img_item:
                            st.image(img_item, width=50)
                        else:
                            st.write("📦")
                    with c_info:
                        st.markdown(f"**{item['nombre']}** (`{item['codigo']}`)")
                        st.caption(f"{item['cantidad']} unid. x ${item['precio_unitario']:,.2f}")
                    with c_sub:
                        st.markdown(f"**${item['subtotal']:,.2f}**")
                    with c_del:
                        if st.button("❌", key=f"del_cart_{idx}"):
                            st.session_state.carrito.pop(idx)
                            st.rerun()

            total_venta = round(sum(item["subtotal"] for item in st.session_state.carrito), 2)
            st.markdown(f"### Total a Cobrar: **${total_venta:,.2f}**")

            # Formas de Pago con opción de Cuenta Corriente / Fiado
            forma_pago = st.selectbox(
                "Forma de Pago:",
                [
                    "Efectivo",
                    "Mercado Pago / QR",
                    "Transferencia",
                    "Cuenta Corriente / Fiado",
                    "Tarjeta de Débito",
                    "Tarjeta de Crédito"
                ]
            )

            # Tarjeta de Datos Bancarios y QR
            if forma_pago in ["Mercado Pago / QR", "Transferencia"]:
                with st.container(border=True):
                    st.markdown("#### 📱 Datos para Cobro Electrónico")
                    col_qr_vista, col_banco_vista = st.columns([1, 1.5], gap="small")
                    with col_qr_vista:
                        qr_abs = obtener_ruta_imagen_absoluta(config_negocio.get("qr_imagen_path"))
                        if qr_abs:
                            st.image(qr_abs, caption="Escanear Código QR", use_container_width=True)
                        else:
                            st.info("Sin QR cargado en Configuración.")
                    with col_banco_vista:
                        st.markdown(f"**Titular:** {config_negocio.get('titular_cuenta', '-')}")
                        st.markdown(f"**Banco:** {config_negocio.get('banco', '-')}")
                        st.markdown(f"**Alias:** `{config_negocio.get('alias', '-')}`")
                        st.markdown(f"**CBU:** `{config_negocio.get('cbu', '-')}`")

            # CUENTA CORRIENTE / FIADO: Seleccionar cliente y validar límite de crédito
            cliente_seleccionado_id = None
            bloquear_venta_fiado = False

            if forma_pago == "Cuenta Corriente / Fiado":
                with st.container(border=True):
                    st.markdown("#### 👥 Asignar Venta a Cuenta Corriente")
                    clientes_lista = models.obtener_clientes()
                    if not clientes_lista:
                        st.error("⚠️ No hay clientes registrados en el sistema. Registra clientes en el módulo 'Cuentas Corrientes'.")
                        bloquear_venta_fiado = True
                    else:
                        dict_cli_opciones = {
                            f"{c['nombre']} (Deuda: ${c['saldo_deudor']:,.2f} | Límite: ${c['limite_credito']:,.2f})": c
                            for c in clientes_lista
                        }
                        cli_label = st.selectbox("Seleccione el Cliente:", list(dict_cli_opciones.keys()))
                        cliente_actual = dict_cli_opciones[cli_label]
                        cliente_seleccionado_id = cliente_actual["id"]

                        saldo_previsto = cliente_actual["saldo_deudor"] + total_venta
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            st.markdown(f"**Saldo Actual:** ${cliente_actual['saldo_deudor']:,.2f}")
                            st.markdown(f"**Límite Máximo:** ${cliente_actual['limite_credito']:,.2f}" if cliente_actual['limite_credito'] > 0 else "**Límite:** Sin límite")
                        with col_c2:
                            st.markdown(f"**Saldo Tras la Venta:** **${saldo_previsto:,.2f}**")

                        if cliente_actual["limite_credito"] > 0 and saldo_previsto > cliente_actual["limite_credito"]:
                            st.error(f"⛔ **LÍMITE EXCEDIDO:** La venta superará el límite de crédito configurado (${cliente_actual['limite_credito']:,.2f}).")
                            bloquear_venta_fiado = True
                        else:
                            st.success("✅ Cliente habilitado para fiado.")

            st.write("")
            col_btn_vender, col_btn_vaciar = st.columns([2, 1], gap="medium")
            with col_btn_vaciar:
                if st.button("🗑️ Vaciar Carrito", use_container_width=True):
                    st.session_state.carrito = []
                    st.rerun()
            with col_btn_vender:
                boton_deshabilitado = bloquear_venta_fiado
                if st.button("✅ Confirmar y Cobrar", type="primary", disabled=boton_deshabilitado, use_container_width=True):
                    try:
                        items_venta = [
                            {"producto_id": it["producto_id"], "cantidad": it["cantidad"]}
                            for it in st.session_state.carrito
                        ]
                        venta_id = models.registrar_venta(
                            items=items_venta,
                            forma_pago=forma_pago,
                            cliente_id=cliente_seleccionado_id
                        )
                        st.session_state.carrito = []
                        st.balloons()
                        st.success(f"🎉 ¡Venta #{venta_id} confirmada por ${total_venta:,.2f} ({forma_pago})!")
                    except models.InsufficientStockError as err:
                        st.error(f"Stock insuficiente: {err}")
                    except Exception as err:
                        st.error(f"Error al registrar la venta: {err}")


# ==============================================================================
# MÓDULO 2: CUENTAS CORRIENTES / CLIENTES ("LA LIBRETA")
# ==============================================================================
elif modulo == "👥 Cuentas Corrientes / Clientes":
    st.header("👥 Cuentas Corrientes / Clientes (\"La Libreta\")")
    st.caption("Control de fiados, límites de crédito, registro de abonos e historial de cuenta por cliente.")

    # Resumen Financiero de Cuentas Corrientes
    resumen_deuda = models.obtener_resumen_deuda_total()
    col_k1, col_k2, col_k3 = st.columns(3)
    col_k1.metric("💸 Deuda Total en la Calle", f"${resumen_deuda['total_deuda']:,.2f}")
    col_k2.metric("⚠️ Clientes con Deuda Activa", f"{resumen_deuda['clientes_con_deuda']} clientes")
    col_k3.metric("👤 Clientes Registrados", f"{resumen_deuda['total_clientes']}")

    st.markdown("---")

    tab_c_lista, tab_c_nuevo, tab_c_abono, tab_c_ficha, tab_c_edit = st.tabs([
        "📋 Libreta de Clientes",
        "➕ Nuevo Cliente",
        "💵 Registrar Abono / Pago",
        "📜 Ficha e Historial de Movimientos",
        "✏️ Modificar / Eliminar Cliente"
    ])

    # 1. Catálogo / Libreta de Clientes
    with tab_c_lista:
        busqueda_cli = st.text_input("🔍 Buscar cliente por nombre o teléfono:", "")
        clientes = models.obtener_clientes(busqueda=busqueda_cli or None)

        if not clientes:
            st.info("No se encontraron clientes registrados.")
        else:
            for c in clientes:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 1.5, 1.5])
                    with c1:
                        st.markdown(f"### {c['nombre']}")
                        st.caption(f"📞 Tel: {c['telefono'] or 'Sin teléfono'} | ✉️ {c['email'] or 'Sin correo'}")
                    with c2:
                        limite_txt = f"${c['limite_credito']:,.2f}" if c['limite_credito'] > 0 else "Sin límite"
                        st.markdown(f"**Límite de Crédito:** {limite_txt}")
                    with c3:
                        if c["saldo_deudor"] > 0:
                            st.error(f"🔴 **Debe: ${c['saldo_deudor']:,.2f}**")
                        else:
                            st.success("🟢 **Al día ($0.00)**")

    # 2. Alta de Cliente
    with tab_c_nuevo:
        st.subheader("Registrar Nuevo Cliente")
        with st.form("form_nuevo_cliente", clear_on_submit=True):
            col_nc1, col_nc2 = st.columns(2)
            with col_nc1:
                nom_cli = st.text_input("Nombre y Apellido *", placeholder="Ej: Carlos Gómez")
                tel_cli = st.text_input("Teléfono / WhatsApp", placeholder="Ej: 11-5555-1234")
            with col_nc2:
                mail_cli = st.text_input("Correo Electrónico (Opcional)", placeholder="carlos@email.com")
                limite_cli = st.number_input(
                    "Límite de Crédito ($)",
                    min_value=0.0,
                    value=0.0,
                    step=5000.0,
                    help="0 = Sin límite de crédito establecido."
                )

            btn_crear_cli = st.form_submit_button("💾 Guardar Cliente", type="primary")
            if btn_crear_cli:
                try:
                    nuevo_cid = models.crear_cliente(
                        nombre=nom_cli,
                        telefono=tel_cli,
                        email=mail_cli,
                        limite_credito=limite_cli
                    )
                    st.success(f"✅ ¡Cliente '{nom_cli}' registrado con éxito! (ID: {nuevo_cid})")
                    st.rerun()
                except models.BusinessLogicError as e:
                    st.error(f"Error de validación: {e}")
                except Exception as e:
                    st.error(f"Error inesperado: {e}")

    # 3. Registrar Abono / Pago
    with tab_c_abono:
        st.subheader("💵 Registrar Pago o Abono a Cuenta Corriente")
        clientes_abono = models.obtener_clientes()
        if not clientes_abono:
            st.info("No hay clientes registrados.")
        else:
            dict_cli_abono = {
                f"{c['nombre']} (Saldo Deudor: ${c['saldo_deudor']:,.2f})": c
                for c in clientes_abono
            }
            sel_cli_abono = st.selectbox("Seleccione el Cliente:", list(dict_cli_abono.keys()), key="select_cli_abono")
            cli_a_abonar = dict_cli_abono[sel_cli_abono]

            with st.container(border=True):
                st.markdown(f"#### Ficha: {cli_a_abonar['nombre']}")
                st.markdown(f"**Deuda Actual:** :red[**${cli_a_abonar['saldo_deudor']:,.2f}**]")

                col_ab1, col_ab2 = st.columns(2)
                with col_ab1:
                    monto_abono = st.number_input(
                        "Monto del Abono / Pago ($) *",
                        min_value=1.0,
                        max_value=max(1.0, float(cli_a_abonar["saldo_deudor"])) if cli_a_abonar["saldo_deudor"] > 0 else 1000000.0,
                        value=float(cli_a_abonar["saldo_deudor"]) if cli_a_abonar["saldo_deudor"] > 0 else 1000.0,
                        step=500.0,
                        format="%.2f"
                    )
                    metodo_abono = st.selectbox("Forma de Pago del Abono:", ["Efectivo", "Transferencia", "Mercado Pago", "Tarjeta"])
                with col_ab2:
                    nuevo_saldo_previsto = max(0.0, cli_a_abonar["saldo_deudor"] - monto_abono)
                    st.markdown("#### Balance Estimado:")
                    st.markdown(f"**Saldo Restante:** :green[**${nuevo_saldo_previsto:,.2f}**]")
                    nota_abono = st.text_input("Nota / Comprobante (Opcional):", placeholder="Ej: Pago parcial efectivo")

                if st.button("✅ Confirmar y Registrar Abono", type="primary"):
                    try:
                        mov_id = models.registrar_abono_cliente(
                            cliente_id=cli_a_abonar["id"],
                            monto=monto_abono,
                            metodo_pago=metodo_abono,
                            descripcion=nota_abono or None
                        )
                        st.success(f"🎉 Abono registrado con éxito (#{mov_id}) por ${monto_abono:,.2f}. Nuevo saldo: ${nuevo_saldo_previsto:,.2f}")
                        st.rerun()
                    except models.BusinessLogicError as e:
                        st.error(f"Error: {e}")
                    except Exception as e:
                        st.error(f"Error al registrar abono: {e}")

    # 4. Ficha e Historial Cronológico
    with tab_c_ficha:
        st.subheader("📜 Historial de Cuenta Corriente")
        clientes_ficha = models.obtener_clientes()
        if not clientes_ficha:
            st.info("No hay clientes registrados.")
        else:
            dict_cli_ficha = {f"{c['nombre']} (${c['saldo_deudor']:,.2f})": c for c in clientes_ficha}
            sel_ficha = st.selectbox("Seleccione el cliente a consultar:", list(dict_cli_ficha.keys()), key="sel_ficha_cli")
            cli_f = dict_cli_ficha[sel_ficha]

            with st.container(border=True):
                c_f1, c_f2, c_f3 = st.columns(3)
                c_f1.markdown(f"**Cliente:** {cli_f['nombre']}")
                c_f1.caption(f"📞 {cli_f['telefono'] or 'S/T'} | ✉️ {cli_f['email'] or 'S/E'}")
                c_f2.markdown(f"**Límite de Crédito:** ${cli_f['limite_credito']:,.2f}" if cli_f['limite_credito'] > 0 else "**Límite:** Sin límite")
                c_f3.markdown(f"**Saldo Deudor:** :red[**${cli_f['saldo_deudor']:,.2f}**]" if cli_f['saldo_deudor'] > 0 else "**Saldo Deudor:** :green[**$0.00**]")

            movimientos = models.obtener_movimientos_cliente(cli_f["id"])
            if not movimientos:
                st.info("Este cliente no tiene movimientos registrados aún.")
            else:
                df_movs = pd.DataFrame(movimientos)
                df_movs["tipo_fmt"] = df_movs["tipo"].map({"CARGO": "🔴 CARGO (Compra Fiada)", "PAGO": "🟢 PAGO (Abono)"})
                df_movs["monto_fmt"] = df_movs["monto"].apply(lambda x: f"${x:,.2f}")
                
                df_mostrar = df_movs[["fecha_hora", "tipo_fmt", "monto_fmt", "descripcion", "ticket_id"]].rename(
                    columns={
                        "fecha_hora": "Fecha y Hora",
                        "tipo_fmt": "Tipo de Movimiento",
                        "monto_fmt": "Monto",
                        "descripcion": "Detalle / Concepto",
                        "ticket_id": "Ticket #"
                    }
                )
                st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

    # 5. Edición y Baja de Clientes
    with tab_c_edit:
        st.subheader("✏️ Modificar o Dar de Baja Cliente")
        clientes_edit = models.obtener_clientes()
        if not clientes_edit:
            st.info("No hay clientes registrados.")
        else:
            dict_cli_edit = {f"{c['nombre']} (ID: {c['id']})": c for c in clientes_edit}
            sel_cli_ed = st.selectbox("Seleccione el cliente a editar:", list(dict_cli_edit.keys()), key="sel_cli_ed")
            cli_ed = dict_cli_edit[sel_cli_ed]
            cid = cli_ed["id"]

            with st.form(f"form_edit_cli_{cid}"):
                c_ed1, c_ed2 = st.columns(2)
                with c_ed1:
                    e_nom = st.text_input("Nombre y Apellido *", value=cli_ed["nombre"])
                    e_tel = st.text_input("Teléfono / WhatsApp", value=cli_ed["telefono"])
                with c_ed2:
                    e_mail = st.text_input("Correo Electrónico", value=cli_ed["email"])
                    e_limite = st.number_input("Límite de Crédito ($)", min_value=0.0, value=float(cli_ed["limite_credito"]), step=5000.0)

                btn_guardar_cli = st.form_submit_button("💾 Guardar Cambios de Cliente", type="primary")
                if btn_guardar_cli:
                    try:
                        models.actualizar_cliente(cid, e_nom, e_tel, e_mail, e_limite)
                        st.success("✅ Datos del cliente actualizados.")
                        st.rerun()
                    except models.BusinessLogicError as e:
                        st.error(f"Error: {e}")

            with st.expander("🗑️ Zona de Baja: Eliminar Cliente"):
                st.warning("Solo se permite eliminar clientes sin deuda pendiente ($0.00).")
                chk_del_cli = st.checkbox("Confirmo que deseo eliminar este cliente", key=f"chk_del_c_{cid}")
                if st.button("Confirmar Eliminación de Cliente", type="secondary", disabled=not chk_del_cli, key=f"btn_del_c_{cid}"):
                    try:
                        models.eliminar_cliente(cid)
                        st.success("Cliente eliminado exitosamente.")
                        st.rerun()
                    except models.BusinessLogicError as e:
                        st.error(f"No se pudo eliminar: {e}")


# ==============================================================================
# MÓDULO 3: GESTIÓN DE PRODUCTOS E INVENTARIO
# ==============================================================================
elif modulo == "📦 Productos e Inventario":
    st.header("📦 Gestión de Productos e Inventario")

    tab_catalogo, tab_nuevo, tab_editar, tab_ajuste, tab_alertas = st.tabs([
        "📋 Catálogo de Productos",
        "➕ Nuevo Producto",
        "✏️ Editar Producto",
        "🔄 Ajuste de Stock",
        "🚨 Monitor de Stock Crítico"
    ])

    # 1. Catálogo Completo
    with tab_catalogo:
        categorias = models.obtener_categorias()
        col_filtro1, col_filtro2 = st.columns([2, 1])
        with col_filtro1:
            busqueda = st.text_input("🔍 Buscar por nombre o código / barra:", "")
        with col_filtro2:
            opciones_cat = {"Todas las categorías": None}
            for c in categorias:
                opciones_cat[c["nombre"]] = c["id"]
            cat_seleccionada = st.selectbox("Filtrar por Categoría:", list(opciones_cat.keys()))
            cat_id_filtro = opciones_cat[cat_seleccionada]

        productos = models.obtener_productos(busqueda=busqueda or None, categoria_id=cat_id_filtro)

        if productos:
            for p in productos:
                with st.container(border=True):
                    col_p_img, col_p_det, col_p_precios, col_p_stock = st.columns([1, 2.5, 2, 2])

                    with col_p_img:
                        img_prod = obtener_ruta_imagen_absoluta(p.get("imagen_path"))
                        if img_prod:
                            st.image(img_prod, use_container_width=True)
                        else:
                            st.markdown(
                                """<div style="border:1px dashed #ccc; border-radius:6px; padding:20px 0; text-align:center; color:#999;">
                                📷<br><small>Sin foto</small></div>""",
                                unsafe_allow_html=True
                            )

                    with col_p_det:
                        st.markdown(f"### {p['nombre']}")
                        st.markdown(f"**Código / Barra:** `{p['codigo']}`")
                        st.caption(f"Categoría: **{p['categoria_nombre']}**")

                    with col_p_precios:
                        st.markdown(f"**Costo:** ${p['precio_costo']:,.2f}")
                        st.markdown(f"**Margen:** {p['margen_ganancia']:.1f}%")
                        tipo_precio = "Manual" if p["usa_precio_manual"] == 1 else "Auto"
                        st.markdown(f"**Venta:** :green[**${p['precio_venta']:,.2f}**] *({tipo_precio})*")

                    with col_p_stock:
                        st.markdown(f"**Stock Mínimo:** {p['stock_minimo']} unid.")
                        if p["stock_actual"] <= p["stock_minimo"]:
                            st.error(f"🚨 **Stock:** **{p['stock_actual']}** unidades")
                            st.caption("⚠️ Requiere reposición")
                        else:
                            st.success(f"📦 **Stock:** **{p['stock_actual']}** unidades")
                            st.caption("Nivel adecuado")
        else:
            st.info("No se encontraron productos coincidentes.")

    # 2. Alta de Producto con Imagen, Código de Barras y Stock Mínimo
    with tab_nuevo:
        st.subheader("Registrar Nuevo Producto")
        with st.form("form_nuevo_producto", clear_on_submit=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                codigo = st.text_input("Código de Barras / SKU *", placeholder="Ej: 7791234567890 o PROD-001", help="Puedes usar la lectora de código de barras directamente aquí.")
                nombre = st.text_input("Nombre del producto *", placeholder="Ej: Gaseosa Cola 1.5L")

                cat_options = {c["nombre"]: c["id"] for c in categorias}
                cat_options_con_ninguna = {"(Sin Categoría)": None, **cat_options}
                cat_elegida = st.selectbox("Categoría", list(cat_options_con_ninguna.keys()))
                cat_id_elegida = cat_options_con_ninguna[cat_elegida]

                imagen_subida = st.file_uploader(
                    "Foto del Producto (JPG / PNG)",
                    type=["jpg", "jpeg", "png"],
                    help="Sube una fotografía del artículo."
                )

            with col_f2:
                costo = st.number_input("Precio de Costo ($)", min_value=0.0, value=100.0, step=10.0, format="%.2f")
                margen = st.number_input("Margen de Ganancia (%)", min_value=0.0, value=30.0, step=5.0, format="%.2f")

                precio_sugerido = models.calcular_precio_venta(costo, margen)
                st.info(f"💡 Precio Calculado Automático: **${precio_sugerido:,.2f}**")

                usa_manual = st.checkbox("Sobreescribir precio de venta manualmente")
                precio_manual = None
                if usa_manual:
                    precio_manual = st.number_input(
                        "Precio de Venta Manual ($)",
                        min_value=0.0,
                        value=precio_sugerido,
                        step=10.0,
                        format="%.2f"
                    )

                col_stk1, col_stk2 = st.columns(2)
                with col_stk1:
                    stock_inicial = st.number_input("Stock Inicial", min_value=0, value=15, step=1)
                with col_stk2:
                    stock_minimo_input = st.number_input(
                        "Stock Mínimo de Alerta",
                        min_value=0,
                        value=5,
                        step=1,
                        help="Umbral mínimo para emitir alertas de reposición."
                    )

            enviado = st.form_submit_button("💾 Guardar Producto", type="primary")
            if enviado:
                try:
                    ruta_img_guardada = None
                    if imagen_subida is not None:
                        ruta_img_guardada = guardar_archivo_imagen(imagen_subida, f"prod_{codigo}")

                    nuevo_id = models.crear_producto(
                        codigo=codigo,
                        nombre=nombre,
                        categoria_id=cat_id_elegida,
                        precio_costo=costo,
                        margen_ganancia=margen,
                        usa_precio_manual=usa_manual,
                        precio_venta_manual=precio_manual if usa_manual else None,
                        stock_actual=stock_inicial,
                        stock_minimo=stock_minimo_input,
                        imagen_path=ruta_img_guardada
                    )
                    st.success(f"✅ ¡Producto creado con éxito! (ID: {nuevo_id})")
                    st.rerun()
                except models.BusinessLogicError as e:
                    st.error(f"Error de validación: {e}")
                except Exception as e:
                    st.error(f"Error inesperado: {e}")

    # 3. Edición Completa de Producto Existente
    with tab_editar:
        st.subheader("✏️ Edición Completa de Producto")
        todos_prods_edit = models.obtener_productos()

        if not todos_prods_edit:
            st.info("No hay productos registrados para editar.")
        else:
            dict_opciones_edit = {
                f"[{p['codigo']}] {p['nombre']} (Stock: {p['stock_actual']} | Mín: {p['stock_minimo']})": p
                for p in todos_prods_edit
            }
            prod_edit_label = st.selectbox(
                "Seleccione un producto para editar:",
                options=list(dict_opciones_edit.keys()),
                key="select_producto_a_editar"
            )
            prod_actual = dict_opciones_edit[prod_edit_label]
            pid = prod_actual["id"]

            st.markdown("---")

            col_ed1, col_ed2 = st.columns(2, gap="large")

            with col_ed1:
                st.markdown("#### 📝 Información General y Foto")
                codigo_edit = st.text_input(
                    "Código de Barras / SKU *",
                    value=prod_actual["codigo"],
                    key=f"edit_cod_{pid}"
                )
                nombre_edit = st.text_input(
                    "Nombre del producto *",
                    value=prod_actual["nombre"],
                    key=f"edit_nom_{pid}"
                )

                cat_options = {c["nombre"]: c["id"] for c in categorias}
                cat_options_con_ninguna = {"(Sin Categoría)": None, **cat_options}
                lista_nombres_cat = list(cat_options_con_ninguna.keys())

                cat_actual_nombre = "(Sin Categoría)"
                for c_nombre, c_id in cat_options.items():
                    if c_id == prod_actual["categoria_id"]:
                        cat_actual_nombre = c_nombre
                        break
                index_cat_actual = lista_nombres_cat.index(cat_actual_nombre) if cat_actual_nombre in lista_nombres_cat else 0

                cat_edit_elegida = st.selectbox(
                    "Categoría",
                    options=lista_nombres_cat,
                    index=index_cat_actual,
                    key=f"edit_cat_{pid}"
                )
                cat_edit_id = cat_options_con_ninguna[cat_edit_elegida]

                st.markdown("##### 📷 Fotografía del Producto")
                img_actual_abs = obtener_ruta_imagen_absoluta(prod_actual.get("imagen_path"))
                eliminar_foto_check = False

                if img_actual_abs:
                    c_f1, c_f2 = st.columns([1, 1.5])
                    with c_f1:
                        st.image(img_actual_abs, caption="Foto actual", width=120)
                    with c_f2:
                        eliminar_foto_check = st.checkbox("🗑️ Eliminar foto actual", key=f"del_foto_{pid}")
                else:
                    st.caption("ℹ️ Sin foto asignada actualmente.")

                nueva_foto_subida = st.file_uploader(
                    "Subir nueva foto (reemplaza o agrega)",
                    type=["jpg", "jpeg", "png"],
                    key=f"upload_foto_{pid}"
                )

            with col_ed2:
                st.markdown("#### 💰 Precios y Control de Inventario")
                costo_edit = st.number_input(
                    "Precio de Costo ($)",
                    min_value=0.0,
                    value=float(prod_actual["precio_costo"]),
                    step=10.0,
                    format="%.2f",
                    key=f"edit_costo_{pid}"
                )
                margen_edit = st.number_input(
                    "Margen de Ganancia (%)",
                    min_value=0.0,
                    value=float(prod_actual["margen_ganancia"]),
                    step=5.0,
                    format="%.2f",
                    key=f"edit_margen_{pid}"
                )

                precio_sugerido_edit = models.calcular_precio_venta(costo_edit, margen_edit)
                st.info(f"💡 Precio Calculado Automático: **${precio_sugerido_edit:,.2f}**")

                usa_manual_edit = st.checkbox(
                    "Sobreescribir precio de venta manualmente",
                    value=bool(prod_actual["usa_precio_manual"]),
                    key=f"edit_manual_{pid}"
                )
                precio_manual_edit = None
                if usa_manual_edit:
                    precio_manual_edit = st.number_input(
                        "Precio de Venta Manual ($)",
                        min_value=0.0,
                        value=float(prod_actual["precio_venta"]),
                        step=10.0,
                        format="%.2f",
                        key=f"edit_pval_{pid}"
                    )

                col_stk_e1, col_stk_e2 = st.columns(2)
                with col_stk_e1:
                    stock_actual_edit = st.number_input(
                        "Stock Actual",
                        min_value=0,
                        value=int(prod_actual["stock_actual"]),
                        step=1,
                        key=f"edit_stk_{pid}"
                    )
                with col_stk_e2:
                    stock_minimo_edit = st.number_input(
                        "Stock Mínimo de Alerta",
                        min_value=0,
                        value=int(prod_actual["stock_minimo"]),
                        step=1,
                        help="Umbral mínimo para activar alertas de reposición.",
                        key=f"edit_min_{pid}"
                    )

            st.write("")
            col_save_btn, col_del_btn = st.columns([1.5, 1], gap="medium")

            with col_save_btn:
                if st.button("💾 Guardar Cambios", type="primary", use_container_width=True, key=f"btn_save_{pid}"):
                    try:
                        ruta_img_final = None
                        if nueva_foto_subida is not None:
                            ruta_img_final = guardar_archivo_imagen(nueva_foto_subida, f"prod_{codigo_edit}")

                        models.actualizar_producto(
                            producto_id=pid,
                            codigo=codigo_edit,
                            nombre=nombre_edit,
                            categoria_id=cat_edit_id,
                            precio_costo=costo_edit,
                            margen_ganancia=margen_edit,
                            usa_precio_manual=usa_manual_edit,
                            precio_venta_manual=precio_manual_edit if usa_manual_edit else None,
                            stock_actual=stock_actual_edit,
                            stock_minimo=stock_minimo_edit,
                            imagen_path=ruta_img_final,
                            eliminar_imagen=eliminar_foto_check and nueva_foto_subida is None
                        )
                        st.success(f"✅ ¡Producto '{nombre_edit}' actualizado con éxito!")
                        st.rerun()
                    except models.BusinessLogicError as e:
                        st.error(f"Error de validación: {e}")
                    except Exception as e:
                        st.error(f"Error inesperado al guardar: {e}")

            with col_del_btn:
                with st.expander("🗑️ Zona de Baja: Eliminar Producto"):
                    st.warning("⚠️ Acción irreversible. No se puede eliminar si posee ventas históricas registradas.")
                    confirmar_del = st.checkbox("Confirmo que deseo eliminar este producto", key=f"chk_del_{pid}")
                    if st.button("🗑️ Confirmar Eliminación", type="secondary", disabled=not confirmar_del, use_container_width=True, key=f"btn_del_{pid}"):
                        try:
                            models.eliminar_producto(pid)
                            st.success(f"Producto '{prod_actual['nombre']}' eliminado correctamente.")
                            st.rerun()
                        except models.BusinessLogicError as e:
                            st.error(f"No se pudo eliminar: {e}")
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")

    # 4. Ajuste Rápido de Stock
    with tab_ajuste:
        st.subheader("🔄 Ajuste de Stock en Almacén")
        todos_los_prods = models.obtener_productos()

        if not todos_los_prods:
            st.info("No hay productos disponibles para ajustar.")
        else:
            dict_prods_ajuste = {
                f"[{p['codigo']}] {p['nombre']} (Stock actual: {p['stock_actual']} | Mín: {p['stock_minimo']})": p
                for p in todos_los_prods
            }
            sel_ajuste = st.selectbox("Seleccione el producto a modificar:", list(dict_prods_ajuste.keys()))
            prod_a_ajustar = dict_prods_ajuste[sel_ajuste]

            col_ajuste_izq, col_ajuste_der = st.columns([1, 1], gap="medium")

            with col_ajuste_izq:
                with st.container(border=True):
                    st.markdown("#### 📦 Ajustar Cantidad en Almacén")
                    tipo_ajuste = st.radio("Método de Ajuste", ["Establecer Conteo Físico Exacto", "Sumar Ingreso de Mercadería"])

                    if tipo_ajuste == "Establecer Conteo Físico Exacto":
                        nuevo_stock_val = st.number_input(
                            "Nuevo Stock Total",
                            min_value=0,
                            value=int(prod_a_ajustar["stock_actual"]),
                            step=1
                        )
                    else:
                        ingreso_cant = st.number_input("Cantidad ingresada", min_value=1, value=10, step=1)
                        nuevo_stock_val = prod_a_ajustar["stock_actual"] + ingreso_cant

                    if st.button("Guardar Stock Actual", type="primary"):
                        try:
                            models.ajustar_stock(prod_a_ajustar["id"], nuevo_stock_val)
                            st.success(f"Stock actualizado a {nuevo_stock_val} unidades.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar stock: {e}")

            with col_ajuste_der:
                with st.container(border=True):
                    st.markdown("#### ⚙️ Umbral de Stock Mínimo")
                    nuevo_minimo = st.number_input(
                        "Stock Mínimo Personalizado",
                        min_value=0,
                        value=int(prod_a_ajustar["stock_minimo"]),
                        step=1,
                        help="Umbral de alerta para este producto específico."
                    )
                    if st.button("Guardar Stock Mínimo"):
                        try:
                            models.actualizar_stock_minimo(prod_a_ajustar["id"], nuevo_minimo)
                            st.success("Stock mínimo actualizado correctamente.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar: {e}")

    # 5. Monitor Exclusivo de Stock Crítico
    with tab_alertas:
        st.subheader("🚨 Artículos que Requieren Reposición Inmediata")
        bajo_stock_list = models.obtener_productos_bajo_stock()

        if not bajo_stock_list:
            st.success("🎉 ¡Excelente! No hay productos con stock igual o inferior a su mínimo.")
        else:
            st.warning(f"Se encontraron **{len(bajo_stock_list)}** artículos con necesidad de reposición.")

            df_criticos = pd.DataFrame(bajo_stock_list)[[
                "codigo", "nombre", "categoria_nombre", "stock_actual", "stock_minimo", "deficit"
            ]].rename(columns={
                "codigo": "Código",
                "nombre": "Producto",
                "categoria_nombre": "Categoría",
                "stock_actual": "Stock Actual",
                "stock_minimo": "Stock Mínimo",
                "deficit": "Déficit / Faltante"
            })
            st.dataframe(df_criticos, use_container_width=True, hide_index=True)


# ==============================================================================
# MÓDULO 4: GESTIÓN DE CATEGORÍAS
# ==============================================================================
elif modulo == "🏷️ Categorías":
    st.header("🏷️ Gestión de Categorías")
    col_nueva, col_lista = st.columns([1, 1.2], gap="large")

    with col_nueva:
        st.subheader("Nueva Categoría")
        with st.form("form_categoria", clear_on_submit=True):
            nombre_cat = st.text_input("Nombre de la Categoría", placeholder="Ej: Bebidas, Almacén, Limpieza")
            btn_guardar_cat = st.form_submit_button("Crear Categoría", type="primary")

            if btn_guardar_cat:
                try:
                    cat_id = models.crear_categoria(nombre_cat)
                    st.success(f"Categoría '{nombre_cat}' creada con éxito (ID: {cat_id}).")
                    st.rerun()
                except models.BusinessLogicError as e:
                    st.error(str(e))

    with col_lista:
        st.subheader("Categorías Existentes")
        lista_categorias = models.obtener_categorias()
        if not lista_categorias:
            st.info("Aún no existen categorías registradas.")
        else:
            for cat in lista_categorias:
                c1, c2 = st.columns([3, 1])
                c1.write(f"📁 **{cat['nombre']}** (ID: {cat['id']})")
                if c2.button("Eliminar", key=f"del_cat_{cat['id']}"):
                    models.eliminar_categoria(cat['id'])
                    st.warning(f"Categoría '{cat['nombre']}' eliminada.")
                    st.rerun()


# ==============================================================================
# MÓDULO 5: ARQUEO DE CAJA Y CIERRE DIARIO
# ==============================================================================
elif modulo == "📊 Arqueo de Caja / Control Diario":
    st.header("📊 Control Diario & Cierre de Caja")

    col_fecha, col_btn_cierre = st.columns([1, 1.5], gap="large")
    with col_fecha:
        fecha_elegida = st.date_input("Fecha de consulta:", value=date.today())

    resumen = models.obtener_arqueo_caja(fecha_elegida.strftime("%Y-%m-%d"))

    # Métricas Principales (KPI Cards)
    m1, m2, m3 = st.columns(3)
    m1.metric("💰 Total Ventas del Día", f"${resumen['total_vendido']:,.2f}")
    m2.metric("📈 Ganancia Estimada", f"${resumen['ganancia_estimada']:,.2f}")
    m3.metric("🧾 Tickets / Operaciones", resumen['total_operaciones'])

    st.markdown("---")

    # BOTÓN DESTACADO: REALIZAR CIERRE DE CAJA DEL DÍA
    st.subheader("🔒 Cierre Oficial de Caja Diario")
    
    col_cierre_btn, _ = st.columns([1.5, 1])
    with col_cierre_btn:
        ejecutar_cierre = st.button("🔒 Realizar Cierre de Caja del Día", type="primary", use_container_width=True)

    if ejecutar_cierre:
        st.session_state["cierre_activo"] = True
        st.session_state["cierre_fecha_activa"] = fecha_elegida.strftime("%Y-%m-%d")

    # Panel de Descarga, WhatsApp y Envío de Correo si se activó el cierre
    if st.session_state.get("cierre_activo") and st.session_state.get("cierre_fecha_activa") == fecha_elegida.strftime("%Y-%m-%d"):
        with st.container(border=True):
            st.success(f"🎉 **Cierre de Caja procesado para el día {fecha_elegida.strftime('%d/%m/%Y')}**")

            nombre_neg = config_negocio.get("nombre_negocio", "Mi Comercio")
            pdf_bytes = reportes.generar_pdf_cierre_caja(
                fecha_str=fecha_elegida.strftime("%Y-%m-%d"),
                resumen=resumen,
                nombre_negocio=nombre_neg
            )

            col_acc1, col_acc2, col_acc3 = st.columns(3, gap="medium")

            with col_acc1:
                st.download_button(
                    label="⬇️ Descargar PDF del Cierre",
                    data=pdf_bytes,
                    file_name=f"Cierre_Caja_{fecha_elegida.strftime('%Y-%m-%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            with col_acc2:
                msg_wsp = (
                    f"📊 *CIERRE DE CAJA - {nombre_neg.upper()}*\n"
                    f"📅 *Fecha:* {fecha_elegida.strftime('%d/%m/%Y')}\n"
                    f"💰 *Total Facturado:* ${resumen['total_vendido']:,.2f}\n"
                    f"📈 *Ganancia Estimada:* ${resumen['ganancia_estimada']:,.2f}\n"
                    f"🧾 *Total Operaciones:* {resumen['total_operaciones']} tickets\n\n"
                    f"*Desglose por Medio de Pago:*\n"
                )
                for dp in resumen.get("desglose_por_forma_pago", []):
                    msg_wsp += f"• {dp['forma_pago']}: ${dp['total']:,.2f} ({dp['operaciones']} ops)\n"

                url_wsp = f"https://wa.me/?text={urllib.parse.quote(msg_wsp)}"
                st.link_button("📲 Compartir Cierre por WhatsApp", url_wsp, use_container_width=True)

            with col_acc3:
                email_dest = config_negocio.get("email_destinatario", "").strip()
                if email_dest and config_negocio.get("smtp_usuario") and config_negocio.get("smtp_password"):
                    if st.button("✉️ Enviar / Reenviar por Email", use_container_width=True):
                        exito, mensaje = reportes.enviar_email_cierre(
                            destinatario=email_dest,
                            pdf_bytes=pdf_bytes,
                            fecha_str=fecha_elegida.strftime("%Y-%m-%d"),
                            resumen=resumen,
                            config_smtp=config_negocio
                        )
                        if exito:
                            st.success(mensaje)
                        else:
                            st.error(mensaje)
                else:
                    st.caption("ℹ️ Configure el correo en '⚙️ Configuración' para habilitar el envío automático.")

            clave_envio = f"email_sent_{fecha_elegida.strftime('%Y-%m-%d')}"
            if not st.session_state.get(clave_envio):
                if email_dest and config_negocio.get("smtp_usuario") and config_negocio.get("smtp_password"):
                    exito, mensaje = reportes.enviar_email_cierre(
                        destinatario=email_dest,
                        pdf_bytes=pdf_bytes,
                        fecha_str=fecha_elegida.strftime("%Y-%m-%d"),
                        resumen=resumen,
                        config_smtp=config_negocio
                    )
                    st.session_state[clave_envio] = True
                    if exito:
                        st.info(f"📧 Correo automático: {mensaje}")
                    else:
                        st.warning(f"⚠️ Correo automático: {mensaje}")

    st.markdown("---")

    col_desglose, col_tickets = st.columns([1, 1.5], gap="large")

    with col_desglose:
        st.subheader("💳 Ventas por Forma de Pago")
        if resumen["desglose_por_forma_pago"]:
            df_desglose = pd.DataFrame(resumen["desglose_por_forma_pago"]).rename(
                columns={
                    "forma_pago": "Forma de Pago",
                    "operaciones": "Operaciones",
                    "total": "Total ($)"
                }
            )
            st.dataframe(df_desglose, use_container_width=True, hide_index=True)
            st.bar_chart(df_desglose.set_index("Forma de Pago")["Total ($)"])
        else:
            st.info("No hay ventas registradas en esta fecha.")

    with col_tickets:
        st.subheader("📜 Detalle de Ventas Registradas")
        if resumen["ventas"]:
            for v in resumen["ventas"]:
                cli_info = f" [Cliente: {v['cliente_nombre']}]" if v.get("cliente_nombre") else ""
                with st.expander(f"Ticket #{v['id']} - {v['fecha_hora']} | ${v['total_venta']:,.2f} ({v['forma_pago']}){cli_info}"):
                    detalles = models.obtener_detalle_de_venta(v["id"])
                    if detalles:
                        df_det = pd.DataFrame(detalles)[["codigo", "nombre", "cantidad", "precio_unitario", "subtotal"]].rename(
                            columns={
                                "codigo": "Código",
                                "nombre": "Producto",
                                "cantidad": "Cant.",
                                "precio_unitario": "Precio Unit.",
                                "subtotal": "Subtotal"
                            }
                        )
                        st.dataframe(df_det, use_container_width=True, hide_index=True)
        else:
            st.info("Sin registros de tickets para la fecha seleccionada.")


# ==============================================================================
# MÓDULO 6: CONFIGURACIÓN DEL NEGOCIO
# ==============================================================================
elif modulo == "⚙️ Configuración del Negocio":
    st.header("⚙️ Configuración del Comercio")
    st.caption("Administra tus datos bancarios para cobros con QR y la configuración de notificaciones por email.")

    with st.form("form_config_negocio"):
        col_c1, col_c2 = st.columns(2, gap="large")

        with col_c1:
            st.markdown("### 🏦 Datos Bancarios y QR de Cobro")
            nombre_neg_input = st.text_input("Nombre de Fantasía del Negocio", value=config_negocio.get("nombre_negocio", "Mi Comercio"))
            titular_input = st.text_input("Titular de la Cuenta", value=config_negocio.get("titular_cuenta", ""))
            banco_input = st.text_input("Banco o Billetera Virtual (ej: Mercado Pago, Santander)", value=config_negocio.get("banco", ""))
            alias_input = st.text_input("Alias CBU/CVU", value=config_negocio.get("alias", ""))
            cbu_input = st.text_input("CBU / CVU Numérico", value=config_negocio.get("cbu", ""))

            st.markdown("#### 📷 Código QR de Cobro (Estático)")
            qr_actual_abs = obtener_ruta_imagen_absoluta(config_negocio.get("qr_imagen_path"))
            if qr_actual_abs:
                st.image(qr_actual_abs, caption="Código QR cargado actualmente", width=140)
            
            qr_subido = st.file_uploader(
                "Subir o Reemplazar Código QR (JPG / PNG)",
                type=["jpg", "jpeg", "png"],
                help="Sube una captura del código QR de tu cuenta para mostrar a los clientes en el Punto de Venta."
            )

        with col_c2:
            st.markdown("### ✉️ Configuración de Correo SMTP")
            st.caption("Para el envío automático del PDF de Cierre de Caja.")

            smtp_srv_input = st.text_input("Servidor SMTP", value=config_negocio.get("smtp_servidor", "smtp.gmail.com"))
            smtp_prt_input = st.number_input("Puerto SMTP (587 recomendado para TLS)", min_value=1, max_value=65535, value=int(config_negocio.get("smtp_puerto", 587)))
            smtp_usr_input = st.text_input("Usuario / Email Remitente", value=config_negocio.get("smtp_usuario", ""), placeholder="tu_cuenta@gmail.com")
            smtp_pwd_input = st.text_input("Contraseña de Aplicación", value=config_negocio.get("smtp_password", ""), type="password", help="En Gmail, utiliza una 'Contraseña de Aplicación' generada desde la seguridad de Google.")
            email_dest_input = st.text_input("Email Destinatario del Cierre Diario", value=config_negocio.get("email_destinatario", ""), placeholder="dueno@negocio.com")

        guardar_cfg_btn = st.form_submit_button("💾 Guardar Configuración", type="primary")

        if guardar_cfg_btn:
            ruta_qr_final = config_negocio.get("qr_imagen_path")
            if qr_subido is not None:
                ruta_qr_final = guardar_archivo_imagen(qr_subido, "qr_pago")

            nueva_config = {
                "nombre_negocio": nombre_neg_input.strip() or "Mi Comercio",
                "titular_cuenta": titular_input.strip(),
                "banco": banco_input.strip(),
                "alias": alias_input.strip(),
                "cbu": cbu_input.strip(),
                "qr_imagen_path": ruta_qr_final,
                "smtp_servidor": smtp_srv_input.strip(),
                "smtp_puerto": int(smtp_prt_input),
                "smtp_usuario": smtp_usr_input.strip(),
                "smtp_password": smtp_pwd_input.strip(),
                "email_destinatario": email_dest_input.strip(),
                "admin_password": config_negocio.get("admin_password", "admin123")
            }

            if guardar_configuracion(nueva_config):
                st.success("✅ Configuración guardada correctamente.")
                st.rerun()
            else:
                st.error("Error al persistir la configuración.")

    st.markdown("---")

    # PANEL: CAMBIAR CONTRASEÑA DE DUEÑO / ADMINISTRADOR
    st.subheader("🔑 Clave de Dueño / Administrador")
    with st.expander("Cambiar Contraseña de Dueño / Administrador", expanded=False):
        st.caption("Esta clave protege acciones críticas como el vaciado de datos y reseteo de fábrica.")
        with st.form("form_cambiar_clave_admin"):
            col_k1, col_k2 = st.columns(2)
            with col_k1:
                clave_actual_in = st.text_input("Contraseña Actual *", type="password", placeholder="Clave actual...")
            with col_k2:
                clave_nueva_in = st.text_input("Nueva Contraseña *", type="password", placeholder="Mínimo 4 caracteres...")

            btn_guardar_clave = st.form_submit_button("💾 Actualizar Contraseña de Dueño", type="primary")
            if btn_guardar_clave:
                exito, msg = cambiar_clave_admin(clave_actual_in, clave_nueva_in)
                if exito:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

    st.markdown("---")

    # SECCIÓN DE PELIGRO: RESET DE FÁBRICA / LIMPIEZA DE DATOS
    with st.expander("⚠️ Restablecer Sistema / Limpieza de Datos", expanded=False):
        st.error("🚨 **ZONA DE PELIGRO - ACCIÓN DESTRUCTIVA**")
        st.markdown(
            "Esta herramienta permite vaciar selectivamente la base de datos para comenzar desde cero "
            "o reiniciar un nuevo ejercicio contable. Los números de ticket y códigos autoincrementales volverán a 1."
        )

        col_rst1, col_rst2 = st.columns(2, gap="large")

        with col_rst1:
            st.markdown("#### Seleccione los datos a eliminar:")
            rst_ventas = st.checkbox("Borrar Historial de Ventas, Tickets y Arqueos de Caja", value=True)
            rst_clientes = st.checkbox("Borrar Clientes y Cuentas Corrientes (\"La Libreta\")", value=True)
            rst_productos = st.checkbox("Borrar Catálogo de Productos, Categorías y Fotos", value=False)

        with col_rst2:
            st.markdown("#### Confirmación de Seguridad:")
            clave_admin = st.text_input(
                "Contraseña de Administrador *",
                type="password",
                placeholder="Ingrese contraseña para autorizar...",
                help="Ingrese su clave de administrador configurada (por defecto 'admin123')."
            )

        st.write("")
        if st.button("💣 Confirmar y Vaciar Datos", type="primary", use_container_width=True):
            if not (rst_ventas or rst_clientes or rst_productos):
                st.warning("⚠️ Debe seleccionar al menos una opción para restablecer.")
            elif not validar_clave_admin(clave_admin):
                st.error("❌ Contraseña de administrador incorrecta. Operación cancelada.")
            else:
                try:
                    resultado = models.vaciar_base_de_datos(
                        limpiar_ventas=rst_ventas,
                        limpiar_clientes=rst_clientes,
                        limpiar_productos=rst_productos,
                        uploads_dir=UPLOADS_DIR
                    )
                    detalles = []
                    if resultado["ventas_borradas"]:
                        detalles.append("Ventas y Tickets")
                    if resultado["clientes_borrados"]:
                        detalles.append("Clientes y Movimientos")
                    if resultado["productos_borrados"]:
                        detalles.append(f"Productos, Categorías ({resultado['fotos_eliminadas']} fotos)")

                    st.session_state.carrito = []
                    st.success(f"🎉 ¡Sistema restablecido a cero con éxito! Se eliminó: {', '.join(detalles)}.")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al restablecer la base de datos: {e}")
