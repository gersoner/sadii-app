import streamlit as st
import psycopg2
from psycopg2.extras import DictCursor
import pandas as pd
from pypdf import PdfReader
from fpdf import FPDF
from ia_engine import analizar_texto_legal
import datetime
import hashlib
import re
import paypalrestsdk  
from contract_engine import generar_contrato_opcion_compra

# ============================================================
# 1. FUNCIÓN DE CONEXIÓN GLOBAL (POSTGRESQL EN LA NUBE)
# ============================================================
def obtener_conexion_db():
    """Establece una conexión segura con el PostgreSQL en la nube usando variables de entorno"""
    try:
        conexion = psycopg2.connect(
            host=st.secrets["postgres"]["host"],
            database=st.secrets["postgres"]["database"],
            user=st.secrets["postgres"]["user"],
            password=st.secrets["postgres"]["password"],
            port=st.secrets["postgres"]["port"]
        )
        return conexion
    except Exception as e:
        st.error(f"Error crítico de conexión al backend de producción: {e}")
        return None

# ============================================================
# 2. INICIALIZACIÓN AUTOMÁTICA DE TABLAS EN PRODUCTION
# ============================================================
def verificar_e_inicializar_configuracion():
    conexion = obtener_conexion_db()
    if conexion is None:
        return
    try:
        cursor = conexion.cursor()
        
        # Crear tabla de configuración si no existe
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracion_sistema (
                clave TEXT PRIMARY KEY,
                valor TEXT,
                descripcion TEXT
            )
        ''')
        
        # Valores iniciales para la base de datos comercial
        valores_defecto = [
            ('plan_precio_usd', '25.00', 'Precio mensual de la suscripción en USD para PayPal'),
            ('plan_nombre', 'Licencia SADII Standard - 30 Creditos', 'Nombre del producto que ve el cliente'),
            ('tasa_cambio_dop', '60.00', 'Tasa de cambio interna para mostrar el aproximado en RD$'),
            ('oferta_activa', '0', '1 si hay oferta especial activa, 0 si es precio regular')
        ]
        
        for clave, valor, desc in valores_defecto:
            cursor.execute('''
                INSERT INTO configuracion_sistema (clave, valor, descripcion)
                VALUES (%s, %s, %s)
                ON CONFLICT (clave) DO NOTHING
            ''', (clave, valor, desc))
            
        conexion.commit()
    except Exception as e:
        st.error(f"Error inicializando parámetros del sistema: {e}")
    finally:
        conexion.close()

# Inicialización al arrancar
verificar_e_inicializar_configuracion()

# ============================================================
# 3. CONFIGURACIÓN DE CREDENCIALES DE PAYPAL (LIVE PRODUCTION)
# ============================================================
# Extrae de forma segura los valores desde los secretos de producción del host
PAYPAL_MODE = st.secrets["paypal"].get("mode", "live")  

paypalrestsdk.configure({
    "mode": PAYPAL_MODE,
    "client_id": st.secrets["paypal"]["client_id"],
    "client_secret": st.secrets["paypal"]["client_secret"]
})

# ==========================================
# 4. CONFIGURACIÓN ESTÉTICA Y SEGURIDAD UI
# ==========================================
st.set_page_config(page_title="SADII | LegalTech SaaS", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px; white-space: pre-wrap; background-color: #ffffff;
        border-radius: 8px; padding: 10px 20px; font-weight: 600;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
    }
    .stTabs [aria-selected="true"] { background-color: #1E3A8A !important; color: white !important; }
    div[data-testid="stMetricValue"] { font-size: 28px; font-weight: bold; color: #1E3A8A; }
    .report-box {
        background-color: #ffffff; padding: 24px; border-radius: 12px;
        border-left: 5px solid #1E3A8A; box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
    }
    .mora-box { background-color: #FEE2E2; border-left: 5px solid #EF4444; padding: 15px; border-radius: 8px; font-weight: bold; color: #991B1B; }
    .atiempo-box { background-color: #D1FAE5; border-left: 5px solid #10B981; padding: 15px; border-radius: 8px; font-weight: bold; color: #065F46; }
    .admin-box { background-color: #EFF6FF; border-left: 5px solid #3B82F6; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
    .error-box { background-color: #FEF2F2; border-left: 5px solid #EF4444; padding: 20px; border-radius: 8px; color: #991B1B; font-weight: bold; margin-bottom: 15px;}
    .upgrade-box { background-color: #FFFBEB; border: 1px solid #FCD34D; padding: 25px; border-radius: 12px; text-align: center; margin-top: 10px; box-shadow: 0px 4px 10px rgba(0,0,0,0.03); }
    .perfil-box { background-color: #ffffff; padding: 20px; border-radius: 8px; border: 1px solid #E5E7EB; box-shadow: 0px 2px 4px rgba(0,0,0,0.02); }
    </style>
""", unsafe_allow_html=True)

def encriptar_contrasena(contrasena):
    return hashlib.sha256(contrasena.encode()).hexdigest()

# ==========================================
# 5. INITIALIZACIÓN DE ESTADOS DE SESIÓN
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'usuario_id' not in st.session_state:
    st.session_state['usuario_id'] = None
if 'usuario_nombre' not in st.session_state:
    st.session_state['usuario_nombre'] = ""
if 'usuario_rol' not in st.session_state:
    st.session_state['usuario_rol'] = "Abogado"
if 'usuario_licencia' not in st.session_state:
    st.session_state['usuario_licencia'] = "Beta_Tester"

# ==========================================
# 6. CORE OPERATIVO COMPATIBLE CON POSTGRESQL
# ==========================================

def obtener_configuracion_sistema():
    conexion = obtener_conexion_db()
    if conexion is None: return {}
    cursor = conexion.cursor()
    cursor.execute('SELECT clave, valor FROM configuracion_sistema')
    filas = cursor.fetchall()
    conexion.close()
    return {clave: valor for clave, valor in filas}

def actualizar_configuracion_sistema(clave, nuevo_valor):
    conexion = obtener_conexion_db()
    if conexion is None: return
    cursor = conexion.cursor()
    cursor.execute('UPDATE configuracion_sistema SET valor = %s WHERE clave = %s', (str(nuevo_valor), clave))
    conexion.commit()
    conexion.close()

def verificar_usuario(correo, contrasena):
    conexion = obtener_conexion_db()
    if conexion is None: return None
    cursor = conexion.cursor()
    hash_clave = encriptar_contrasena(contrasena)
    cursor.execute('SELECT id, nombre, rol, tipo_licencia FROM usuarios WHERE correo = %s AND contrasena_hash = %s', (correo, hash_clave))
    usuario = cursor.fetchone()
    conexion.close()
    return usuario

def consultar_creditos_actuales(usuario_id):
    if usuario_id is None: return 0
    conexion = obtener_conexion_db()
    if conexion is None: return 0
    cursor = conexion.cursor()
    cursor.execute('SELECT creditos_disponibles FROM usuarios WHERE id = %s', (usuario_id,))
    resultado = cursor.fetchone()
    conexion.close()
    return resultado[0] if resultado else 0

def deducir_credito_usuario(usuario_id):
    conexion = obtener_conexion_db()
    if conexion is None: return
    cursor = conexion.cursor()
    cursor.execute('UPDATE usuarios SET creditos_disponibles = creditos_disponibles - 1 WHERE id = %s AND creditos_disponibles > 0', (usuario_id,))
    conexion.commit()
    conexion.close()

def aplicar_upgrade_licencia_db(usuario_id, creditos_nuevos=30):
    conexion = obtener_conexion_db()
    if conexion is None: return
    cursor = conexion.cursor()
    cursor.execute('''
        UPDATE usuarios 
        SET tipo_licencia = 'SADII_Standard', 
            creditos_disponibles = creditos_disponibles + %s 
        WHERE id = %s
    ''', (creditos_nuevos, usuario_id))
    conexion.commit()
    conexion.close()

def admin_recargar_creditos(usuario_id, cantidad):
    conexion = obtener_conexion_db()
    if conexion is None: return
    cursor = conexion.cursor()
    cursor.execute('UPDATE usuarios SET creditos_disponibles = creditos_disponibles + %s WHERE id = %s', (cantidad, usuario_id))
    conexion.commit()
    conexion.close()

def consultar_perfil_completo(usuario_id):
    conexion = obtener_conexion_db()
    if conexion is None: return None
    cursor = conexion.cursor()
    cursor.execute('SELECT nombre, correo, telefono, rnc_cedula, firma_legal, tipo_licencia FROM usuarios WHERE id = %s', (usuario_id,))
    datos = cursor.fetchone()
    conexion.close()
    return datos

def actualizar_contrasena_db(usuario_id, nueva_clave):
    conexion = obtener_conexion_db()
    if conexion is None: return
    cursor = conexion.cursor()
    hash_nuevo = encriptar_contrasena(nueva_clave)
    cursor.execute('UPDATE usuarios SET contrasena_hash = %s WHERE id = %s', (hash_nuevo, usuario_id))
    conexion.commit()
    conexion.close()

# ==========================================
# 7. CONTROL DE ACCESO PRIMARIO
# ==========================================
if not st.session_state['autenticado']:
    st.markdown("<h1 style='text-align: center; color: #1E3A8A; font-weight: 800; margin-top: 30px;'>⚖️ BIENVENIDO A TOGADO (SADII)</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #6B7280; font-size: 16px;'>Plataforma Cloud de Auditoría Inmobiliaria y Control Temporal Dominicano</p>", unsafe_allow_html=True)
    
    col_login1, col_login2, col_login3 = st.columns([1, 1.8, 1])
    with col_login2:
        tab_login, tab_registro = st.tabs(["🔑 Iniciar Sesión", "📝 Crear Cuenta Profesional"])
        
        with tab_login:
            st.markdown("### Acceso Abogados")
            input_correo = st.text_input("Correo Electrónico profesional:", key="login_email")
            input_clave = st.text_input("Contraseña:", type="password", key="login_pass")
            boton_login = st.button("Ingresar al Sistema", type="primary", use_container_width=True)
            
            if boton_login:
                datos_usuario = verificar_usuario(input_correo, input_clave)
                if datos_usuario:
                    st.session_state['autenticado'] = True
                    st.session_state['usuario_id'] = datos_usuario[0]
                    st.session_state['usuario_nombre'] = datos_usuario[1]
                    st.session_state['usuario_rol'] = datos_usuario[2]
                    st.session_state['usuario_licencia'] = datos_usuario[3]
                    st.rerun()
                else:
                    st.error("❌ Credenciales inválidas. Verifique su correo o contraseña.")
                    
        with tab_registro:
            st.markdown("### Registro de Nueva Firma / Consultor")
            reg_nombre = st.text_input("Nombre del Abogado / Gestor:", key="reg_nom")
            reg_correo = st.text_input("Correo Electrónico de Trabajo:", key="reg_corr")
            reg_clave = st.text_input("Cree su Contraseña de Acceso:", type="password", key="reg_clav")
            reg_rnc = st.text_input("RNC o Cédula (Sin guiones):", key="reg_rnc_doc")
            reg_telefono = st.text_input("Teléfono de Contacto:", key="reg_tel")
            reg_firma = st.text_input("Firma Legal / Empresa (Opcional):", placeholder="Ej: Ferrer & Asociados", key="reg_firm")
                
            boton_registro = st.button("Registrar Firma en la Suite", use_container_width=True, type="primary")
            
            if boton_registro:
                rnc_limpio = re.sub(r'\D', '', reg_rnc)
                if not reg_nombre or not reg_correo or not reg_clave or not reg_rnc:
                    st.warning("⚠️ Los campos Nombre, Correo, Contraseña y RNC/Cédula son obligatorios.")
                elif len(rnc_limpio) != 9 and len(rnc_limpio) != 11:
                    st.error("❌ El RNC o Cédula debe tener exactamente 9 u 11 dígitos.")
                else:
                    try:
                        conexion = obtener_conexion_db()
                        cursor = conexion.cursor()
                        cursor.execute('''
                            INSERT INTO usuarios (nombre, correo, contrasena_hash, telefono, rnc_cedula, firma_legal, creditos_disponibles) 
                            VALUES (%s, %s, %s, %s, %s, %s, 3)
                        ''', (reg_nombre, reg_correo, encriptar_contrasena(reg_clave), reg_telefono, rnc_limpio, reg_firma))
                        conexion.commit()
                        conexion.close()
                        st.success("🎉 ¡Firma registrada con éxito! Ya puedes iniciar sesión.")
                    except Exception as e:
                        st.error("❌ Este correo electrónico ya se encuentra registrado o el backend experimenta congestión.")
    st.stop()

# ==========================================
# 8. GESTIÓN DE EXPEDIENTES Y DICTÁMENES
# ==========================================
def calcular_dias_habiles_y_vencimiento(fecha_inicio, dias_a_sumar=45):
    fecha_actual = fecha_inicio
    dias_contados = 0
    while dias_contados < dias_a_sumar:
        fecha_actual += datetime.timedelta(days=1)
        if fecha_actual.weekday() < 5:
            dias_contados += 1
    return fecha_actual

def extraer_texto_pdf(archivo_pdf):
    lector = PdfReader(archivo_pdf)
    texto_completo = ""
    for pagina in lector.pages:
        texto_completo += pagina.extract_text() + "\n"
    return texto_completo

class PDFReporte(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 58, 138)
        self.cell(0, 10, "SADII | AUDITORÍA COMPLEMENTARIA LEY 108-05", ln=True, align="L")
        self.set_draw_color(30, 58, 138)
        self.line(10, 18, 200, 18)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"SaaS Dictamen Confidencial - Generado el {datetime.date.today().strftime('%d/%m/%Y')} - Pág {self.page_no()}", align="C")

def generar_pdf_descargable(contenido_reporte, catastral, propietario):
    pdf = PDFReporte()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 12, "INFORME DE DUE DILIGENCE INMOBILIARIO", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Designación Catastral:", 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, str(catastral), ln=True)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Propietario Registral:", 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, str(propietario), ln=True)
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    texto_limpio = contenido_reporte.replace("**", "").replace("#", "")
    pdf.multi_cell(0, 6, texto_limpio.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

def guardar_en_base_datos_avanzada(usuario_id, designacion, propietario, analisis, riesgo, reglamento, f_deposito, f_vencimiento, estado_plazo):
    conexion = obtener_conexion_db()
    if conexion is None: return
    cursor = conexion.cursor()
    cursor.execute('''
        INSERT INTO auditorias (usuario_id, designacion_catastral, propietario, analisis_ia, nivel_riesgo, reglamento_afectado, fecha_deposito, fecha_vencimiento_ji, estado_plazo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (usuario_id, designacion, propietario, analisis, riesgo, reglamento, f_deposito, f_vencimiento, estado_plazo))
    conexion.commit()
    conexion.close()

def cargar_historial_completo_usuario(usuario_id):
    conexion = obtener_conexion_db()
    if conexion is None: return pd.DataFrame()
    query = 'SELECT fecha, designacion_catastral, propietario, nivel_riesgo, analisis_ia, reglamento_afectado, fecha_deposito, fecha_vencimiento_ji, estado_plazo FROM auditorias WHERE usuario_id = %s ORDER BY fecha DESC'
    df = pd.read_sql_query(query, conexion, params=(usuario_id,))
    conexion.close()
    return df

def admin_cargar_todos_los_usuarios():
    conexion = obtener_conexion_db()
    if conexion is None: return pd.DataFrame()
    df = pd.read_sql_query("SELECT id, nombre, correo, rnc_cedula, firma_legal, tipo_licencia, creditos_disponibles FROM usuarios ORDER BY id ASC", conexion)
    conexion.close()
    return df

# ==========================================
# 9. ARQUITECTURA VISUAL (DASHBOARD)
# ==========================================
st.markdown("<h1 style='text-align: center; color: #1E3A8A; font-weight: 800;'>⚖️ SUITE LEGALTECH - TOGADO</h1>", unsafe_allow_html=True)
st.markdown("---")

creditos_actuales = consultar_creditos_actuales(st.session_state['usuario_id'])

st.sidebar.markdown("<h3 style='color: #1E3A8A;'>💼 Licencia Activa</h3>", unsafe_allow_html=True)
st.sidebar.info(f"**Abogado:** {st.session_state['usuario_nombre']}\n\n**Análisis Disponibles:** {creditos_actuales if st.session_state['usuario_rol'] != 'Admin' else 'ILIMITADOS ♾️'}")

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state['autenticado'] = False
    st.session_state['usuario_id'] = None
    st.rerun()

lista_pestanas = ["🔍 Módulo de Análisis Predictivo", "📊 Cuadro de Mando & Control de Mora Registral", "⚙️ Mi Perfil"]
if st.session_state['usuario_rol'] == 'Admin':
    lista_pestanas.append("👑 Consola del Administrador")

pestanas = st.tabs(lista_pestanas)

# PESTAÑA 1: ANALIZAR DOCUMENTO
with pestanas[0]:
    st.markdown("### 📥 Auditoría de Expediente y Registro de Plazos (Res. 788-2022)")
    
    if creditos_actuales <= 0 and st.session_state['usuario_rol'] != 'Admin':
        st.markdown("""
            <div class='error-box'>
                🚨 PERFIL SUSPENDIDO POR CONSUMO DE CRÉDITOS: Has agotado tus análisis gratuitos de cortesía.
            </div>
        """, unsafe_allow_html=True)
        
        config_comercial = obtener_configuracion_sistema()
        precio_usd_dinamico = float(config_comercial.get('plan_precio_usd', 25.00))
        nombre_plan_dinamico = config_comercial.get('plan_nombre', 'Licencia SADII Standard - 30 Creditos')
        
        st.markdown(f"""
            <div class='upgrade-box'>
                <h3 style='color: #1E3A8A; margin-top:0;'>🚀 Haz el Upgrade a {nombre_plan_dinamico}</h3>
                <p style='color: #4B5563;'>Obtén acceso completo e inmediato a <b>30 créditos de auditoría mensuales</b> a través de PayPal.</p>
                <h2 style='color: #10B981; margin: 10px 0;'>${precio_usd_dinamico:.2f} USD <small style='font-size:14px; color:#6B7280;'>/ mes</small></h2>
            </div>
        """, unsafe_allow_html=True)
        
        boton_pago_paypal = st.button("💳 Confirmar Pago Seguro con PayPal", type="primary", use_container_width=True)
        
        if boton_pago_paypal:
            with st.spinner("Creando orden de pago en los servidores seguros de PayPal..."):
                payment = paypalrestsdk.Payment({
                    "intent": "sale",
                    "payer": {"payment_method": "paypal"},
                    "redirect_urls": {
                        "return_url": "https://togado.com/?pago=exito",
                        "cancel_url": "https://togado.com/?pago=cancelado"
                    },
                    "transactions": [{
                        "item_list": {
                            "items": [{
                                "name": nombre_plan_dinamico,
                                "sku": "SADII-STD",
                                "price": f"{precio_usd_dinamico:.2f}",
                                "currency": "USD",
                                "quantity": 1
                            }]
                        },
                        "amount": {"total": f"{precio_usd_dinamico:.2f}", "currency": "USD"},
                        "description": f"Suscripción Mensual SADII - ID {st.session_state['usuario_id']}"
                    }]
                })

                if payment.create():
                    for link in payment.links:
                        if link.rel == "approval_url":
                            approval_url = link.href
                            st.markdown(f"#### 🔗 [Haga clic aquí para autorizar el pago en la ventana segura de PayPal]({approval_url})")
                            st.info("💡 Una vez complete el pago en la pestaña de PayPal, regrese aquí y use el botón de abajo para verificar la transacción.")
                            
                            if st.button("🔄 Validar Transacción Autorizada", key="verif_pay"):
                                aplicar_upgrade_licencia_db(st.session_state['usuario_id'], 30)
                                st.success("🎉 ¡PayPal validó la transacción con éxito! Cuenta promovida a Plan Estándar.")
                                st.balloons()
                                st.rerun()
                else:
                    st.error(f"Fallo al conectar con PayPal: {payment.error}")
                    
    else:
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            archivo_cargado = st.file_uploader("Arrastre aquí la Certificación (PDF):", type=["pdf"])
        with col_f2:
            catastro = st.text_input("Designación Catastral única:", placeholder="Ej: Parcela 10-A")
            prop = st.text_input("Titular bajo estudio:")
            fecha_deposito_ingresada = st.date_input("Fecha de Depósito:", datetime.date.today())

        if st.button("🚀 Iniciar Auditoría", type="primary", use_container_width=True):
            if archivo_cargado and catastro:
                if st.session_state['usuario_role'] != 'Admin':
                    deducir_credito_usuario(st.session_state['usuario_id'])
                texto_extraido = extraer_texto_pdf(archivo_cargado)
                resultado_ia = analizar_texto_legal(texto_extraido)
                fecha_vencimiento_legal = calcular_dias_habiles_y_vencimiento(fecha_deposito_ingresada, 45)
                guardar_en_base_datos_avanzada(st.session_state['usuario_id'], catastro, prop, resultado_ia, "Estándar", "Ley 108-05", fecha_deposito_ingresada.strftime('%Y-%m-%d'), fecha_vencimiento_legal.strftime('%Y-%m-%d'), "A Tiempo 🟢")
                st.success("Auditoría Completada")
                st.rerun()

# PESTAÑA 2: HISTORIAL
with pestanas[1]:
    df_historial = cargar_historial_completo_usuario(st.session_state['usuario_id'])
    if not df_historial.empty:
        st.dataframe(df_historial, use_container_width=True)

# PESTAÑA 3: PERFIL & SUSCRIPCIONES
with pestanas[2]:
    datos_perfil = consultar_perfil_completo(st.session_state['usuario_id'])
    if datos_perfil:
        st.markdown("### ⚙️ Panel de Control de la Firma")
        
        config_comercial = obtener_configuracion_sistema()
        precio_usd_dinamico = float(config_comercial.get('plan_precio_usd', 25.00))
        tasa_dop_dinamica = float(config_comercial.get('tasa_cambio_dop', 60.00))
        nombre_plan_dinamico = config_comercial.get('plan_nombre', 'Licencia SADII Standard - 30 Creditos')
        
        precio_rd_calculado = precio_usd_dinamico * tasa_dop_dinamica

        col_p1, col_p2 = st.columns([1.2, 1])
        
        with col_p1:
            st.markdown(f"""
                <div class='perfil-box'>
                    <h4 style='color: #1E3A8A; margin-top:0;'>📋 Datos de la Firma</h4>
                    <p><b>Nombre:</b> {datos_perfil[0]}</p>
                    <p><b>Correo:</b> {datos_perfil[1]}</p>
                    <p><b>Teléfono:</b> {datos_perfil[2]}</p>
                    <p><b>RNC / Cédula:</b> {datos_perfil[3]}</p>
                    <p><b>Firma Legal:</b> {datos_perfil[4] if datos_perfil[4] else 'Consultor Independiente'}</p>
                    <p><b>Plan Activo:</b> <span style='color: #1E3A8A; font-weight: bold;'>{datos_perfil[5].upper()}</span></p>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
                <div class='upgrade-box'>
                    <h4 style='color: #1E3A8A; margin-top:0;'>🚀 Membresía {nombre_plan_dinamico}</h4>
                    <p style='color: #4B5563; font-size: 14px;'>Aumenta tu capacidad operativa con créditos de auditoría mensuales gestionados vía PayPal.</p>
                    <h3 style='color: #10B981; margin: 10px 0;'>${precio_usd_dinamico:.2f} USD <small style='font-size:12px; color:#6B7280;'>/ mes</small></h3>
                    <p style='color: #6B7280; font-size: 11px;'>Aproximadamente <b>RD$ {precio_rd_calculado:,.2f}</b> al cambio interno actual ({tasa_dop_dinamica} DOP/USD).</p>
                </div>
            """, unsafe_allow_html=True)
            
            boton_pago_perfil = st.button("💳 Suscribirse ahora con PayPal", type="primary", use_container_width=True, key="pago_perfil_btn")
            
            if boton_pago_perfil:
                with st.spinner("Conectando con la pasarela de PayPal..."):
                    payment = paypalrestsdk.Payment({
                        "intent": "sale",
                        "payer": {"payment_method": "paypal"},
                        "redirect_urls": {
                            "return_url": "https://togado.com/?pago=exito",
                            "cancel_url": "https://togado.com/?pago=cancelado"
                        },
                        "transactions": [{
                            "item_list": {
                                "items": [{
                                    "name": nombre_plan_dinamico,
                                    "sku": "SADII-STD",
                                    "price": f"{precio_usd_dinamico:.2f}",
                                    "currency": "USD",
                                    "quantity": 1
                                }]
                            },
                            "amount": {"total": f"{precio_usd_dinamico:.2f}", "currency": "USD"},
                            "description": f"Suscripción Mensual SADII - ID {st.session_state['usuario_id']}"
                        }]
                    })
                    
                    if payment.create():
                        for link in payment.links:
                            if link.rel == "approval_url":
                                approval_url = link.href
                                st.markdown(f"#### 🔗 [Abrir Ventana Segura de PayPal]({approval_url})")
                                st.info("💡 Completa el pago, regresa y presiona verificar.")
                                
                                if st.button("🔄 Validar Transacción Autorizada", key="verif_pay_perfil"):
                                    aplicar_upgrade_licencia_db(st.session_state['usuario_id'], 30)
                                    st.success("🎉 ¡Membresía activada con éxito!")
                                    st.balloons()
                                    st.rerun()
                    else:
                        st.error(f"Error de comunicación con PayPal: {payment.error}")
                        
        with col_p2:
            st.markdown("#### 🔒 Seguridad")
            nueva_clave = st.text_input("Nueva Contraseña:", type="password", key="perfil_new_pass")
            confirmar_clave = st.text_input("Confirmar Nueva Contraseña:", type="password", key="perfil_conf_pass")
            
            if st.button("💾 Guardar Cambios", type="secondary", use_container_width=True):
                if nueva_clave and nueva_clave == confirmar_clave:
                    actualizar_contrasena_db(st.session_state['usuario_id'], nueva_clave)
                    st.success("🔒 Contraseña actualizada correctamente.")
                elif nueva_clave != confirmar_clave:
                    st.error("❌ Las contraseñas no coinciden.")

# PESTAÑA OBLIGATORIA SI ES ADMIN
if st.session_state['usuario_rol'] == 'Admin' and len(pestanas) > 3:
    with pestanas[3]:
        st.markdown("### 👑 Consola del Administrador")
        
        st.markdown("#### ⚙️ Parámetros Comerciales y Pasarela de Pagos")
        config_actual = obtener_configuracion_sistema()
        
        col_adm1, col_adm2, col_adm3 = st.columns(3)
        
        with col_adm1:
            nuevo_precio = st.number_input(
                "Precio de Suscripción (USD):", 
                value=float(config_actual.get('plan_precio_usd', 25.00)), 
                step=1.0
            )
        with col_adm2:
            nueva_tasa = st.number_input(
                "Tasa de Cambio Interna (1 USD a DOP):", 
                value=float(config_actual.get('tasa_cambio_dop', 60.00)), 
                step=0.1
            )
        with col_adm3:
            nuevo_nombre_plan = st.text_input(
                "Nombre Comercial del Plan:", 
                value=config_actual.get('plan_nombre', 'Licencia SADII Standard - 30 Creditos')
            )
            
        if st.button("💾 Aplicar Cambios Globales en Producción", type="primary"):
            actualizar_configuracion_sistema('plan_precio_usd', f"{nuevo_precio:.2f}")
            actualizar_configuracion_sistema('tasa_cambio_dop', f"{nueva_tasa:.2f}")
            actualizar_configuracion_sistema('plan_nombre', nuevo_nombre_plan)
            st.success("🚀 Parámetros actualizados en PostgreSQL Cloud.")
            st.rerun()
            
        st.markdown("---")
        
        st.markdown("#### 👥 Usuarios Registrados en el Sistema")
        df_usuarios = admin_cargar_todos_los_usuarios()
        st.dataframe(df_usuarios, use_container_width=True)