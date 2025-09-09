import asyncio
import json
import os
import time
import random
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from anythingllm_client import AnythingLLMClient, send_to_anythingllm
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import threading
from anythingllm_client import AnythingLLMClient, send_to_anythingllm, CLIENT_VERSION
from icon_standards import get_icon, get_status_icon, format_status_message, ICONS

APP_VERSION = "app_v20250909_2238_008"

def log_and_print(level: str, message: str, *args):
    """Hilfsfunktion: Print-Ausgabe mit Icon-Standards"""
    formatted_message = message % args if args else message
    
    # Icon basierend auf Log-Level
    level_icon = get_icon("log_level", level, ICONS["log_level"]["info"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level_icon} {formatted_message}")

# Logging-Konfiguration
def setup_logging():
    """Konfiguriert das Logging-System"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "standard")
    
    # Log-Level aus String konvertieren
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    # Format festlegen
    if log_format.lower() == "json":
        # Strukturiertes JSON-Logging für Container
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}'
        )
    else:
        # Standard-Format mit Zeitstempel
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    # Root-Logger konfigurieren
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout
    )
    
    # Handler für unsere Anwendung
    logger = logging.getLogger("iot-bridge")
    logger.setLevel(numeric_level)
    
    return logger

# Logger initialisieren
logger = setup_logging()

# Datenmodelle
class ErrorMessage(BaseModel):
    machine: str
    code: str
    description: str

# Globale Variablen
llm_client = None
mqtt_client = None
mqtt_enabled = False
auto_generator_enabled = True
generator_thread = None

# Demo-Daten für automatische Fehlergeneration
DEMO_MACHINES = [
    "Hydraulikpresse_01", "Hydraulikpresse_02", "CNC_Fräse_03", "CNC_Fräse_04",
    "Schweißroboter_05", "Schweißroboter_06", "Montagestation_07", "Montagestation_08",
    "Lackieranlage_09", "Verpackungsmaschine_10", "Förderband_11", "Qualitätsprüfung_12"
]

DEMO_ERRORS = [
    {"code": "E001", "desc": "Hydraulikdruck unter Sollwert"},
    {"code": "E002", "desc": "Ventil blockiert"},
    {"code": "W105", "desc": "Spindeltemperatur erhöht"},
    {"code": "W106", "desc": "Vibration über Grenzwert"},
    {"code": "E302", "desc": "Drahtvorschub blockiert"},
    {"code": "E303", "desc": "Schweißstrom instabil"},
    {"code": "W201", "desc": "Greifer-Sensor unplausibel"},
    {"code": "W202", "desc": "Pneumatikdruck schwankend"},
    {"code": "E401", "desc": "Lackvorrat unter 20%"},
    {"code": "E402", "desc": "Sprühkopf verstopft"},
    {"code": "W501", "desc": "Verpackungsmaterial fehlt"},
    {"code": "E601", "desc": "Förderband-Motor überlastet"},
    {"code": "W701", "desc": "Kamera-Kalibrierung erforderlich"}
]

def generate_random_error():
    """Generiert einen zufälligen Maschinenfehler"""
    machine = random.choice(DEMO_MACHINES)
    error = random.choice(DEMO_ERRORS)
    return machine, error["code"], error["desc"]

def auto_error_generator():
    """Background-Thread für automatische Fehlergeneration"""
    global auto_generator_enabled, llm_client
    
    # Konfigurierbare Wartezeiten
    initial_delay = int(os.getenv("AUTO_GENERATOR_INITIAL_DELAY", "10"))
    interval = int(os.getenv("AUTO_GENERATOR_INTERVAL", "60"))
    
    log_and_print("INFO", f"{ICONS['system']['start']} Auto-Generator gestartet - warte %d Sekunden vor erstem Fehler", initial_delay)
    
    # Einmalige Wartezeit nach Start
    for i in range(initial_delay):
        if not auto_generator_enabled:
            log_and_print("INFO", f"{ICONS['system']['stop']} Auto-Generator während Initialisierung gestoppt")
            return
        time.sleep(1)
    
    log_and_print("INFO", f"{ICONS['process']['running']} Auto-Generator initialisiert - beginne mit Fehlergeneration (alle %d Sekunden)", interval)
    
    error_count = 0
    while auto_generator_enabled:
        try:
            # Heartbeat-Log alle 10 Durchläufe
            if error_count % 10 == 0:
                heartbeat_icon = ICONS["system"]["heartbeat"]
                log_and_print("DEBUG", f"{heartbeat_icon} Auto-Generator Heartbeat - Fehler generiert: %d", error_count)
            
            # Zufälligen Fehler generieren
            machine, code, description = generate_random_error()
            
            log_and_print("INFO", f"{ICONS['machine']['factory']} Generiere Auto-Fehler: %s/%s", machine, code)
            log_and_print("DEBUG", f"{ICONS['machine']['error']} Auto-Fehler Details: %s - %s", code, description)
            
            if llm_client:
                result = llm_client.send_machine_error(machine, code, description)
                if result and result.get("success"):
                    if result.get("api_response"):
                        attempt = result.get("attempt", 1)
                        success_icon = get_icon("process", "success")
                        log_and_print("INFO", f"{success_icon} Auto-Fehler erfolgreich an AnythingLLM gesendet (Versuch %d)", attempt)
                    else:
                        storage_icon = get_icon("process", "warning")
                        log_and_print("INFO", f"{storage_icon} Auto-Fehler lokal gespeichert (API nicht verfügbar)")
                else:
                    error_icon = get_icon("process", "error")
                    log_and_print("ERROR", f"{error_icon} Auto-Fehler komplett fehlgeschlagen")
            else:
                offline_icon = get_status_icon("offline")
                log_and_print("ERROR", f"{offline_icon} LLM-Client nicht verfügbar")
            
            error_count += 1
            
            # Warten bis zum nächsten Fehler
            for i in range(interval):
                if not auto_generator_enabled:
                    break
                time.sleep(1)
            
            if not auto_generator_enabled:
                break
                
        except Exception as e:
            error_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{error_icon} Auto-Generator Fehler: %s", e)
    
    stop_icon = ICONS["system"]["stop"]
    log_and_print("INFO", f"{stop_icon} Auto-Generator gestoppt")

def restart_auto_generator():
    """Startet Auto-Generator neu (hilfreich bei Problemen)"""
    global auto_generator_enabled, generator_thread
    
    # Alten Thread stoppen
    auto_generator_enabled = False
    if generator_thread and generator_thread.is_alive():
        log_and_print("INFO", f"{ICONS['time']['waiting']} Warte auf Thread-Beendigung...")
        generator_thread.join(timeout=5)
    
    # Neuen Thread starten
    auto_generator_enabled = True
    generator_thread = threading.Thread(target=auto_error_generator, daemon=True)
    generator_thread.start()
    log_and_print("INFO", f"{ICONS['system']['restart']} Auto-Generator neu gestartet")

def setup_mqtt():
    """MQTT Client Setup - Optional"""
    global mqtt_client, mqtt_enabled
    
    if os.getenv("ENABLE_MQTT", "false").lower() != "true":
        disabled_icon = get_status_icon("disabled")
        log_and_print("INFO", f"{disabled_icon} MQTT deaktiviert (ENABLE_MQTT=false)")
        return False
    
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            connected_icon = get_status_icon("online")
            log_and_print("INFO", f"{connected_icon} MQTT erfolgreich verbunden")
            client.subscribe("machines/+/errors")
            client.subscribe("opc/+/alarms")
            global mqtt_enabled
            mqtt_enabled = True
        else:
            error_icon = get_status_icon("error")
            log_and_print("ERROR", f"{error_icon} MQTT Verbindung fehlgeschlagen: %d", rc)

    def on_message(client, userdata, msg):
        """Verarbeitet eingehende MQTT-Nachrichten"""
        try:
            topic_parts = msg.topic.split('/')
            machine = topic_parts[1] if len(topic_parts) > 1 else "unknown"
            
            payload = json.loads(msg.payload.decode())
            error_code = payload.get('code', 'unknown')
            description = payload.get('description', 'Keine Beschreibung')
            
            receive_icon = ICONS["network"]["signal"]
            log_and_print("INFO", f"{receive_icon} MQTT empfangen: %s/%s", machine, error_code)
            log_and_print("DEBUG", f"{ICONS['data']['json']} MQTT Details: Topic=%s, Payload=%s", msg.topic, payload)
            
            if llm_client:
                result = llm_client.send_machine_error(machine, error_code, description)
                if result and result.get("success"):
                    success_icon = get_icon("process", "success")
                    log_and_print("INFO", f"{success_icon} MQTT-Fehler erfolgreich verarbeitet")
                else:
                    warning_icon = get_icon("process", "warning")
                    log_and_print("WARNING", f"{warning_icon} MQTT-Fehler konnte nicht verarbeitet werden")
            
        except json.JSONDecodeError as e:
            error_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{error_icon} Ungültige JSON in MQTT-Nachricht: %s", e)
        except Exception as e:
            error_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{error_icon} MQTT-Verarbeitung fehlgeschlagen: %s", e)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    
    try:
        connecting_icon = get_status_icon("connecting")
        log_and_print("INFO", f"{connecting_icon} Verbinde mit MQTT Broker: %s:%d", mqtt_broker, mqtt_port)
        mqtt_client.connect(mqtt_broker, mqtt_port, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        error_icon = get_status_icon("error")
        log_and_print("ERROR", f"{error_icon} MQTT Verbindung fehlgeschlagen: %s", e)
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global llm_client, auto_generator_enabled, generator_thread
    startup_msg = format_status_message("starting", f"IoT-AnythingLLM Bridge startet... {APP_VERSION}")
    log_and_print("INFO", startup_msg)
    
    # AnythingLLM Client initialisieren
    try:
        llm_client = AnythingLLMClient()
        
        # AnythingLLM testen
        if llm_client.test_connection():
            ready_msg = format_status_message("online", f"AnythingLLM bereit {APP_VERSION}")
            log_and_print("SUCCESS", ready_msg)
        else:
            warning_msg = format_status_message("warning", f"AnythingLLM nicht erreichbar {APP_VERSION}")
            log_and_print("WARNING", warning_msg)
    except Exception as e:
        error_icon = get_status_icon("error")
        log_and_print("ERROR", f"{error_icon} Fehler bei AnythingLLM-Initialisierung: %s", e)
    
    # MQTT setup (optional)
    try:
        if setup_mqtt():
            mqtt_ready = format_status_message("online", "MQTT bereit")
            log_and_print("SUCCESS", mqtt_ready)
        else:
            mqtt_info = format_status_message("standby", "MQTT nicht verfügbar")
            log_and_print("INFO", mqtt_info)
    except Exception as e:
        error_icon = get_status_icon("error")
        log_and_print("ERROR", f"{error_icon} Fehler bei MQTT-Setup: %s", e)
    
    # Auto-Generator starten
    auto_generator_enabled = os.getenv("ENABLE_AUTO_GENERATOR", "true").lower() == "true"
    if auto_generator_enabled:
        try:
            generator_thread = threading.Thread(target=auto_error_generator, daemon=True)
            generator_thread.start()
            generator_msg = format_status_message("online", "Auto-Generator Thread gestartet")
            log_and_print("SUCCESS", generator_msg)
        except Exception as e:
            error_icon = get_status_icon("error")
            log_and_print("ERROR", f"{error_icon} Fehler beim Starten des Auto-Generators: %s", e)
    
    bridge_ready = format_status_message("success", f"Bridge erfolgreich gestartet! {APP_VERSION}")
    log_and_print("SUCCESS", bridge_ready)
    
    yield
    
    # Shutdown
    shutdown_msg = format_status_message("warning", "Bridge wird heruntergefahren...")
    log_and_print("INFO", shutdown_msg)
    auto_generator_enabled = False
    if mqtt_client and mqtt_enabled:
        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
            disconnect_msg = format_status_message("offline", "MQTT-Verbindung getrennt")
            log_and_print("INFO", disconnect_msg)
        except Exception as e:
            error_icon = get_status_icon("error")
            log_and_print("ERROR", f"{error_icon} Fehler beim MQTT-Disconnect: %s", e)

# FastAPI App mit Lifespan
app = FastAPI(
    title="IoT-OPC-AnythingLLM Bridge",
    description="Bridge zwischen OPC UA/MQTT und AnythingLLM mit Auto-Generator",
    version=APP_VERSION,
    lifespan=lifespan
)

@app.get("/")
async def root():
    log_and_print("DEBUG", f"{ICONS['network']['api']} Root-Endpoint aufgerufen")
    return {
        "message": "IoT-AnythingLLM Bridge läuft",
        "version": APP_VERSION,
        "client_version": CLIENT_VERSION,  # ← Verwendet die importierte Version
        "build_info": {
            "app_version": APP_VERSION,
            "client_version": CLIENT_VERSION,  # ← Verwendet die importierte Version
            "build_date": "2025-09-09",
            "last_update": "Icon-Standards und verbessertes Logging"
        },
        "timestamp": datetime.now().isoformat(),
        "anythingllm_status": "Verbunden" if llm_client and llm_client.test_connection() else "Getrennt",
        "mqtt_status": "Verbunden" if mqtt_enabled else "Deaktiviert",
        "auto_generator": "Aktiv" if auto_generator_enabled else "Deaktiviert",
        "log_level": logging.getLevelName(logger.level),
        "endpoints": {
            "manual_error": "/manual-error",
            "test": "/test",
            "status": "/status",
            "test_error": "/test-error",
            "auto_generator": "/auto-generator",
            "version": "/version"
        }
    }

@app.get("/version")
async def get_version():
    """Gibt detaillierte Versionsinformationen zurück"""
    return {
        "app_version": APP_VERSION,
        "client_version": CLIENT_VERSION,
        "build_info": {
            "build_date": "2025-09-09",
            "last_update": "Icon-Standards und verbessertes Logging",
            "features": [
                "Einheitliche Icon-Standards",
                "Dynamische Status-Icons",
                "Retry-Mechanismus mit sofortigem Exit bei Erfolg",
                "Workspace-Discovery beim Startup",
                "Lokale Fallback-Speicherung",
                "Auto-Generator mit konfigurierbaren Intervallen",
                "Health-Check System"
            ]
        },
        "components": {
            "fastapi": "Latest",
            "anythingllm_client": CLIENT_VERSION,
            "icon_standards": "v1.0.0",
            "mqtt": "Optional",
            "opcua": "Planned"
        }
    }

@app.get("/status")
async def status():
    """Status der Bridge"""
    anythingllm_status = llm_client.test_connection() if llm_client else False
    current_time = datetime.now().strftime("%Y%m%d %H%M%S")
    
    status_data = {
        "anythingllm": "Online" if anythingllm_status else "Offline",
        "mqtt": "Online" if mqtt_enabled else "Deaktiviert",
        "auto_generator": "Aktiv" if auto_generator_enabled else "Deaktiviert",
        "timestamp": current_time
    }
    
    log_and_print("DEBUG", f"{ICONS['monitoring']['dashboard']} Status abgefragt: %s", status_data)
    return status_data

@app.post("/manual-error")
async def manual_error(error: ErrorMessage):
    """Manuelles Senden eines Fehlers an AnythingLLM"""
    if not llm_client:
        error_icon = get_status_icon("error")
        log_and_print("ERROR", f"{error_icon} Manual-Error Anfrage, aber LLM-Client nicht initialisiert")
        raise HTTPException(status_code=500, detail="AnythingLLM Client nicht initialisiert")
    
    log_and_print("INFO", f"{ICONS['machine']['error']} Manueller Fehler: %s/%s", error.machine, error.code)
    log_and_print("DEBUG", f"{ICONS['data']['config']} Manueller Fehler Details: %s - %s", error.code, error.description)
    
    try:
        result = llm_client.send_machine_error(error.machine, error.code, error.description)
        
        if result and result.get("success"):
            if result.get("api_response"):
                success_icon = get_icon("process", "success")
                log_and_print("SUCCESS", f"{success_icon} Manueller Fehler erfolgreich an AnythingLLM API gesendet")
            else:
                storage_icon = get_icon("process", "warning")
                log_and_print("INFO", f"{storage_icon} Manueller Fehler lokal gespeichert (API nicht verfügbar)")
            
            return {
                "success": True, 
                "message": f"Fehler {error.code} von {error.machine} erfolgreich gesendet",
                "result": result
            }
        else:
            error_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{error_icon} Manueller Fehler fehlgeschlagen")
            raise HTTPException(status_code=500, detail="Fehler beim Senden an AnythingLLM")
            
    except Exception as e:
        error_icon = get_icon("process", "error")
        log_and_print("ERROR", f"{error_icon} Manueller Fehler Exception: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test")
async def test_all():
    """Testet alle Verbindungen"""
    test_icon = ICONS["monitoring"]["dashboard"]
    log_and_print("INFO", f"{test_icon} Teste alle Verbindungen")
    current_time = datetime.now().strftime("%Y%m%d %H%M%S")
    
    if not llm_client:
        error_icon = get_status_icon("error")
        log_and_print("ERROR", f"{error_icon} Test-Anfrage, aber LLM-Client nicht initialisiert")
        return {"error": "AnythingLLM Client nicht initialisiert"}
    
    try:
        anythingllm_test = llm_client.test_connection()
        test_result = "Erfolgreich" if anythingllm_test else "Fehlgeschlagen"
        log_and_print("DEBUG", f"{ICONS['network']['ping']} AnythingLLM-Test Ergebnis: %s", test_result)
        
        return {
            "anythingllm_test": test_result,
            "mqtt_status": "Verbunden" if mqtt_enabled else "Deaktiviert",
            "auto_generator": "Aktiv" if auto_generator_enabled else "Deaktiviert",
            "timestamp": current_time
        }
    except Exception as e:
        error_icon = get_icon("process", "error")
        log_and_print("ERROR", f"{error_icon} Test-Fehler: %s", e)
        return {"error": str(e)}

@app.post("/test-error")
async def test_error():
    """Sendet einen Test-Fehler an AnythingLLM"""
    if not llm_client:
        error_icon = get_status_icon("error")
        log_and_print("ERROR", f"{error_icon} Test-Error Anfrage, aber LLM-Client nicht initialisiert")
        raise HTTPException(status_code=500, detail="AnythingLLM Client nicht initialisiert")
    
    log_and_print("INFO", f"{ICONS['machine']['robot']} Sende Test-Fehler")
    
    try:
        result = llm_client.send_machine_error("Testmaschine_42", "E999", "Dies ist ein API-Test-Fehler")
        
        success = result is not None and result.get("success", False)
        result_text = "erfolgreich" if success else "fehlgeschlagen"
        result_icon = get_icon("process", "success" if success else "error")
        log_and_print("INFO", f"{result_icon} Test-Fehler Ergebnis: %s", result_text)
        
        return {
            "success": success,
            "result": result,
            "message": "Test-Fehler erfolgreich gesendet!" if result else "Test-Fehler fehlgeschlagen"
        }
    except Exception as e:
        error_icon = get_icon("process", "error")
        log_and_print("ERROR", f"{error_icon} Test-Error Exception: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auto-generator/start")
async def start_auto_generator():
    """Startet den Auto-Generator"""
    global auto_generator_enabled, generator_thread
    
    if auto_generator_enabled:
        running_icon = get_status_icon("online")
        log_and_print("INFO", f"{running_icon} Auto-Generator start angefragt, läuft bereits")
        return {"message": "Auto-Generator läuft bereits", "status": "active"}
    
    start_icon = ICONS["system"]["start"]
    log_and_print("INFO", f"{start_icon} Starte Auto-Generator")
    try:
        auto_generator_enabled = True
        generator_thread = threading.Thread(target=auto_error_generator, daemon=True)
        generator_thread.start()
        return {"message": "Auto-Generator gestartet", "status": "started"}
    except Exception as e:
        error_icon = get_icon("process", "error")
        log_and_print("ERROR", f"{error_icon} Fehler beim Starten des Auto-Generators: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auto-generator/stop")
async def stop_auto_generator():
    """Stoppt den Auto-Generator"""
    global auto_generator_enabled
    
    if not auto_generator_enabled:
        stopped_icon = get_status_icon("offline")
        log_and_print("INFO", f"{stopped_icon} Auto-Generator stop angefragt, läuft nicht")
        return {"message": "Auto-Generator läuft nicht", "status": "inactive"}
    
    stop_icon = ICONS["system"]["stop"]
    log_and_print("INFO", f"{stop_icon} Stoppe Auto-Generator")
    auto_generator_enabled = False
    
    return {"message": "Auto-Generator gestoppt", "status": "stopped"}

@app.post("/auto-generator/restart")
async def restart_auto_generator_endpoint():
    """Startet den Auto-Generator neu (bei Problemen)"""
    try:
        restart_auto_generator()
        return {"message": "Auto-Generator neu gestartet", "status": "restarted"}
    except Exception as e:
        error_icon = get_icon("process", "error")
        log_and_print("ERROR", f"{error_icon} Fehler beim Restart: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auto-generator/status")
async def auto_generator_status():
    """Status des Auto-Generators"""
    global generator_thread
    
    thread_alive = generator_thread.is_alive() if generator_thread else False
    
    status_data = {
        "enabled": auto_generator_enabled,
        "status": "Aktiv" if auto_generator_enabled else "Inaktiv",
        "thread_alive": thread_alive,
        "thread_healthy": auto_generator_enabled and thread_alive,
        "interval": f"{os.getenv('AUTO_GENERATOR_INTERVAL', '60')} Sekunden",
        "initial_delay": f"{os.getenv('AUTO_GENERATOR_INITIAL_DELAY', '10')} Sekunden",
        "demo_machines": len(DEMO_MACHINES),
        "demo_errors": len(DEMO_ERRORS)
    }
    
    return status_data

@app.get("/anythingllm/workspaces")
async def get_anythingllm_workspaces():
    """Gibt alle verfügbaren AnythingLLM Workspaces zurück"""
    if not llm_client:
        raise HTTPException(status_code=500, detail="AnythingLLM Client nicht initialisiert")
    
    try:
        workspaces_data = llm_client.get_workspaces()
        workspaces = workspaces_data.get("workspaces", [])
        
        result = {
            "total_workspaces": len(workspaces),
            "active_workspace": llm_client.workspace_slug,
            "workspaces": []
        }
        
        for ws in workspaces:
            result["workspaces"].append({
                "id": ws.get("id"),
                "name": ws.get("name"),
                "slug": ws.get("slug"),
                "created": ws.get("createdAt"),
                "is_active": ws.get("slug") == llm_client.workspace_slug,
                "api_url": f"{llm_client.base_url}/api/v1/workspace/{ws.get('slug')}/chat"
            })
        
        return result
        
    except Exception as e:
        error_icon = get_icon("process", "error")
        log_and_print("ERROR", f"{error_icon} Fehler beim Abrufen der Workspaces: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Konfigurierbare Startup-Wartezeit
    startup_delay = int(os.getenv("STARTUP_DELAY", "5"))
    
    if startup_delay > 0:
        print(f"{ICONS['time']['waiting']} Warte {startup_delay} Sekunden vor System-Start...")
        time.sleep(startup_delay)
    
    log_and_print("INFO", f"{ICONS['system']['start']} Starte Python-AnythingLLM main %s", APP_VERSION)
    log_and_print("INFO", f"{ICONS['data']['config']} AnythingLLM_Client Version: %s", CLIENT_VERSION)
    log_and_print("INFO", f"{ICONS['system']['config']} Umgebungsvariablen:")
    log_and_print("INFO", f"   {ICONS['network']['api']} ANYTHINGLLM_URL: %s", os.getenv('ANYTHINGLLM_URL', 'NICHT_GESETZT'))
    log_and_print("INFO", f"   {ICONS['network']['mqtt']} ENABLE_MQTT: %s", os.getenv('ENABLE_MQTT', 'false'))
    log_and_print("INFO", f"   {ICONS['machine']['factory']} ENABLE_AUTO_GENERATOR: %s", os.getenv('ENABLE_AUTO_GENERATOR', 'true'))
    log_and_print("INFO", f"   {ICONS['data']['log']} LOG_LEVEL: %s", os.getenv('LOG_LEVEL', 'INFO'))
    log_and_print("INFO", f"   {ICONS['data']['config']} LOG_FORMAT: %s", os.getenv('LOG_FORMAT', 'standard'))
    log_and_print("INFO", f"   {ICONS['time']['timer']} STARTUP_DELAY: %s Sekunden", startup_delay)
    log_and_print("INFO", f"   {ICONS['time']['timer']} AUTO_GENERATOR_INITIAL_DELAY: %s Sekunden", os.getenv('AUTO_GENERATOR_INITIAL_DELAY', '10'))
    log_and_print("INFO", f"   {ICONS['time']['clock']} AUTO_GENERATOR_INTERVAL: %s Sekunden", os.getenv('AUTO_GENERATOR_INTERVAL', '60'))
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
