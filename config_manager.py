"""
Gestor de configuración del negocio (Datos Bancarios, QR de Pago, Parámetros de Email/SMTP
y Clave de Dueño / Administrador).
Persiste la configuración en un archivo JSON local en el directorio del proyecto.
"""
import os
import json
from typing import Dict, Any, Tuple

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_negocio.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "nombre_negocio": "Mi Comercio",
    "titular_cuenta": "Titular de la Cuenta",
    "cbu": "0000003100012345678901",
    "alias": "comercio.pagos",
    "banco": "Banco / Billetera Virtual",
    "qr_imagen_path": None,
    "smtp_servidor": "smtp.gmail.com",
    "smtp_puerto": 587,
    "smtp_usuario": "",
    "smtp_password": "",
    "email_destinatario": "",
    "admin_password": "admin123"
}


def cargar_configuracion() -> Dict[str, Any]:
    """Carga la configuración existente o retorna la configuración por defecto."""
    if not os.path.exists(CONFIG_FILE):
        guardar_configuracion(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(data)
            return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()


def guardar_configuracion(nueva_config: Dict[str, Any]) -> bool:
    """Guarda la configuración actualizada en disco."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(nueva_config, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def validar_clave_admin(clave: str) -> bool:
    """Valida si la clave ingresada coincide con la clave de dueño guardada."""
    cfg = cargar_configuracion()
    clave_guardada = str(cfg.get("admin_password", "admin123")).strip()
    return str(clave).strip() == clave_guardada


def cambiar_clave_admin(clave_actual: str, nueva_clave: str) -> Tuple[bool, str]:
    """Valida la clave actual y actualiza la clave de administrador."""
    if not validar_clave_admin(clave_actual):
        return False, "La contraseña actual es incorrecta."

    nueva_limpia = nueva_clave.strip()
    if len(nueva_limpia) < 4:
        return False, "La nueva contraseña debe tener al menos 4 caracteres."

    cfg = cargar_configuracion()
    cfg["admin_password"] = nueva_limpia
    if guardar_configuracion(cfg):
        return True, "Contraseña de administrador actualizada con éxito."
    return False, "Error al guardar la nueva contraseña en disco."
