import sqlite3
import hashlib

def encriptar_contrasena(contrasena):
    return hashlib.sha256(contrasena.encode()).hexdigest()

def inicializar_base_datos():
    conexion = sqlite3.connect('auditoria_legal.db')
    cursor = conexion.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. TABLA DE USUARIOS (Estructura Fiscal Dominicana)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            contrasena_hash TEXT NOT NULL,
            telefono TEXT,
            rnc_cedula TEXT NOT NULL,       -- Campo obligatorio para KYC y facturación fiscal
            firma_legal TEXT,              -- Nombre del despacho u oficina
            rol TEXT DEFAULT 'Abogado',
            tipo_licencia TEXT DEFAULT 'Beta_Tester',
            creditos_disponibles INTEGER DEFAULT 3,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. TABLA DE AUDITORÍAS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auditorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            designacion_catastral TEXT NOT NULL,
            propietario TEXT NOT NULL,
            analisis_ia TEXT NOT NULL,
            nivel_riesgo TEXT NOT NULL,
            reglamento_afectado TEXT,
            fecha_deposito TEXT,
            fecha_vencimiento_ji TEXT,
            estado_plazo TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    ''')
    
    # 3. CREACIÓN DE TU CUENTA ADMINISTRADORA CON LOS NUEVOS CAMPOS
    clave_admin_encriptada = encriptar_contrasena("sadii2026")
    
    cursor.execute('''
        INSERT OR IGNORE INTO usuarios (id, nombre, correo, contrasena_hash, telefono, rnc_cedula, firma_legal, rol, tipo_licencia, creditos_disponibles)
        VALUES (1, 'Gerson Ferrer', 'gerson@sadii.legal', ?, '809-555-5555', 'N/A-ADMIN', 'Ferrer & Asociados', 'Admin', 'Enterprise', 9999)
    ''', (clave_admin_encriptada,))
    
    conexion.commit()
    conexion.close()
    print("⚖️ Base de datos adaptada a la normativa fiscal dominicana (RNC/Cédula) con éxito.")

if __name__ == "__main__":
    inicializar_base_datos()