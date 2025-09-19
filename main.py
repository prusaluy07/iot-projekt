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
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import threading

# OPC UA Integration
try:
    from opcua_client import MultiOPCUAClient, test_opcua_connection
    OPCUA_AVAILABLE = True
except ImportError:
    OPCUA_AVAILABLE = False
    logging.warning("OPC UA Module nicht verfügbar - opcua_client.py fehlt oder asyncua nicht installiert")

# MQTT Integration (optional)
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logging.warning("MQTT nicht verfügbar - paho-mqtt nicht installiert")

# Logging-Konfiguration
def setup_logging():
    """Konfiguriert das Logging-System"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "standard")
    
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    if log_format.lower() == "json":
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}'
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout
    )
    
    return logging.getLogger("iot-bridge")

# Logger initialisieren
logger = setup_logging()

# Datenmodelle
class ErrorMessage(BaseModel):
    machine: str
    code: str
    description: str

class OPCUATestRequest(BaseModel):
    server_url: str
    timeout: int = 10

# Globale Variablen
llm_client = None
multi_opcua_client = None
mqtt_client = None
mqtt_enabled = False
auto_generator_enabled = False
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
    
    initial_delay = int(os.getenv("AUTO_GENERATOR_INITIAL_DELAY", "10"))
    interval = int(os.getenv("AUTO_GENERATOR_INTERVAL", "60"))
    
    logger.info("Auto-Generator gestartet - warte %d Sekunden vor erstem Fehler", initial_delay)
    
    # Einmalige Wartezeit nach Start
    for i in range(initial_delay):
        if not auto_generator_enabled:
            logger.info("Auto-Generator während Initialisierung gestoppt")
            return
        time.sleep(1)
    
    logger.info("Auto-Generator initialisiert - beginne mit Fehlergeneration (alle %d Sekunden)", interval)
    
    while auto_generator_enabled:
        try:
            machine, code, description = generate_random_error()
            
            logger.info("Generiere Auto-Fehler: %s/%s", machine, code)
            logger.debug("Auto-Fehler Details: %s - %s", code, description)
            
            if llm_client:
                result = llm_client.send_machine_error(machine, code, description)
                if result and result.get("success"):
                    if result.get("api_response"):
                        logger.info("Auto-Fehler erfolgreich an AnythingLLM API gesendet")
                    else:
                        logger.info("Auto-Fehler lokal gespeichert (API nicht verfügbar)")
                else:
                    logger.error("Auto-Fehler fehlgeschlagen")
            else:
                logger.error("LLM-Client nicht verfügbar")
            
            # Warten bis zum nächsten Fehler
            for i in range(interval):
                if not auto_generator_enabled:
                    break
                time.sleep(1)
            
            if not auto_generator_enabled:
                break
                
        except Exception as e:
            logger.exception("Auto-Generator Fehler: %s", e)
    
    logger.info("Auto-Generator gestoppt")

def setup_mqtt():
    """MQTT Client Setup - Optional"""
    global mqtt_client, mqtt_enabled
    
    if not MQTT_AVAILABLE:
        logger.warning("MQTT nicht verfügbar - paho-mqtt nicht installiert")
        return False
    
    if os.getenv("ENABLE_MQTT", "false").lower() != "true":
        logger.info("MQTT deaktiviert (ENABLE_MQTT=false)")
        return False
    
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("MQTT erfolgreich verbunden")
            client.subscribe("machines/+/errors")
            client.subscribe("opc/+/alarms")
            global mqtt_enabled
            mqtt_enabled = True
        else:
            logger.error("MQTT Verbindung fehlgeschlagen: %d", rc)

    def on_message(client, userdata, msg):
        try:
            topic_parts = msg.topic.split('/')
            machine = topic_parts[1] if len(topic_parts) > 1 else "unknown"
            
            payload = json.loads(msg.payload.decode())
            error_code = payload.get('code', 'unknown')
            description = payload.get('description', 'Keine Beschreibung')
            
            logger.info("MQTT empfangen: %s/%s", machine, error_code)
            logger.debug("MQTT Details: Topic=%s, Payload=%s", msg.topic, payload)
            
            if llm_client:
                result = llm_client.send_machine_error(machine, error_code, description)
                if result and result.get("success"):
                    logger.info("MQTT-Fehler erfolgreich verarbeitet")
                else:
                    logger.warning("MQTT-Fehler konnte nicht verarbeitet werden")
            
        except json.JSONDecodeError as e:
            logger.error("Ungültige JSON in MQTT-Nachricht: %s", e)
        except Exception as e:
            logger.exception("MQTT-Verarbeitung fehlgeschlagen: %s", e)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    
    try:
        logger.info("Verbinde mit MQTT Broker: %s:%d", mqtt_broker, mqtt_port)
        mqtt_client.connect(mqtt_broker, mqtt_port, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        logger.exception("MQTT Verbindung fehlgeschlagen: %s", e)
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global llm_client, multi_opcua_client, auto_generator_enabled, generator_thread
    logger.info("IoT-AnythingLLM Bridge startet...")
    
    # AnythingLLM Client initialisieren
    try:
        llm_client = AnythingLLMClient()
        
        if llm_client.test_connection():
            logger.info("AnythingLLM bereit")
        else:
            logger.warning("AnythingLLM nicht erreichbar")
    except Exception as e:
        logger.exception("Fehler bei AnythingLLM-Initialisierung: %s", e)
    
    # OPC UA Multi-Client initialisieren
    if OPCUA_AVAILABLE and os.getenv("ENABLE_OPCUA", "false").lower() == "true":
        try:
            logger.info("Initialisiere OPC UA Multi-Client...")
            multi_opcua_client = MultiOPCUAClient(llm_client)
            
            # Alle konfigurierten Server verbinden
            connection_results = await multi_opcua_client.connect_all_servers()
            connected_count = sum(1 for success in connection_results.values() if success)
            total_servers = len(connection_results)
            
            logger.info("OPC UA Multi-Client: %d/%d Server erfolgreich verbunden", 
                       connected_count, total_servers)
            
            if connected_count > 0:
                logger.info("Verbundene OPC UA Server: %s", 
                           multi_opcua_client.get_connected_servers())
            
            if connected_count < total_servers:
                logger.warning("Nicht verbundene OPC UA Server: %s", 
                              multi_opcua_client.get_disconnected_servers())
            
        except Exception as e:
            logger.exception("OPC UA Multi-Client Initialisierung fehlgeschlagen: %s", e)
            multi_opcua_client = None
    elif not OPCUA_AVAILABLE:
        logger.warning("OPC UA nicht verfügbar - opcua_client.py oder asyncua fehlt")
    else:
        logger.info("OPC UA deaktiviert (ENABLE_OPCUA=false)")
    
    # MQTT setup (optional)
    try:
        if setup_mqtt():
            logger.info("MQTT bereit")
        else:
            logger.info("MQTT nicht verfügbar")
    except Exception as e:
        logger.exception("Fehler bei MQTT-Setup: %s", e)
    
    # Auto-Generator starten
    auto_generator_enabled = os.getenv("ENABLE_AUTO_GENERATOR", "true").lower() == "true"
    if auto_generator_enabled:
        try:
            generator_thread = threading.Thread(target=auto_error_generator, daemon=True)
            generator_thread.start()
            logger.info("Auto-Generator Thread gestartet")
        except Exception as e:
            logger.exception("Fehler beim Starten des Auto-Generators: %s", e)
    
    logger.info("Bridge erfolgreich gestartet!")
    
    yield
    
    # Shutdown
    logger.info("Bridge wird heruntergefahren...")
    
    # OPC UA Server trennen
    if multi_opcua_client:
        try:
            await multi_opcua_client.disconnect_all_servers()
            logger.info("OPC UA Server-Verbindungen getrennt")
        except Exception as e:
            logger.exception("Fehler beim OPC UA Disconnect: %s", e)
    
    # Auto-Generator stoppen
    auto_generator_enabled = False
    
    # MQTT trennen
    if mqtt_client and mqtt_enabled:
        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
            logger.info("MQTT-Verbindung getrennt")
        except Exception as e:
            logger.exception("Fehler beim MQTT-Disconnect: %s", e)

# FastAPI App mit Lifespan
app = FastAPI(
    title="IoT-OPC-AnythingLLM Bridge",
    description="Bridge zwischen OPC UA/MQTT und AnythingLLM mit Multi-Server-Support",
    version="2.0.0",
    lifespan=lifespan
)

# Bestehende Endpoints
@app.get("/")
async def root():
    logger.debug("Root-Endpoint aufgerufen")
    
    # OPC UA Status ermitteln
    opcua_status = "Nicht verfügbar"
    if multi_opcua_client:
        connected_servers = multi_opcua_client.get_connected_servers()
        total_servers = len(multi_opcua_client.servers)
        opcua_status = f"{len(connected_servers)}/{total_servers} verbunden"
    elif not OPCUA_AVAILABLE:
        opcua_status = "Nicht installiert"
    
    return {
        "message": "IoT-AnythingLLM Bridge läuft",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "anythingllm_status": "Verbunden" if llm_client and llm_client.test_connection() else "Getrennt",
        "opcua_status": opcua_status,
        "mqtt_status": "Verbunden" if mqtt_enabled else "Deaktiviert",
        "auto_generator": "Aktiv" if auto_generator_enabled else "Deaktiviert",
        "log_level": logging.getLevelName(logger.level),
        "endpoints": {
            "manual_error": "/manual-error",
            "test": "/test",
            "status": "/status",
            "test_error": "/test-error",
            "auto_generator": "/auto-generator/*",
            "opcua": "/opcua/*"
        }
    }

@app.get("/status")
async def status():
    """Detaillierter System-Status"""
    anythingllm_status = llm_client.test_connection() if llm_client else False
    
    # OPC UA Status
    opcua_info = {"available": OPCUA_AVAILABLE, "enabled": False, "servers": {}}
    if multi_opcua_client:
        opcua_info["enabled"] = True
        opcua_status = await multi_opcua_client.get_server_status()
        opcua_info.update(opcua_status)
    
    status_data = {
        "anythingllm": "Online" if anythingllm_status else "Offline",
        "opcua": opcua_info,
        "mqtt": "Online" if mqtt_enabled else "Deaktiviert",
        "auto_generator": "Aktiv" if auto_generator_enabled else "Deaktiviert",
        "system": {
            "log_level": logging.getLevelName(logger.level),
            "mqtt_available": MQTT_AVAILABLE,
            "opcua_available": OPCUA_AVAILABLE
        },
        "timestamp": datetime.now().isoformat()
    }
    
    logger.debug("Status abgefragt: %s", status_data)
    return status_data

# Bestehende Error-Endpoints
@app.post("/manual-error")
async def manual_error(error: ErrorMessage):
    """Manuelles Senden eines Fehlers an AnythingLLM"""
    if not llm_client:
        logger.error("Manual-Error Anfrage, aber LLM-Client nicht initialisiert")
        raise HTTPException(status_code=500, detail="AnythingLLM Client nicht initialisiert")
    
    logger.info("Manueller Fehler: %s/%s", error.machine, error.code)
    logger.debug("Manueller Fehler Details: %s - %s", error.code, error.description)
    
    try:
        result = llm_client.send_machine_error(error.machine, error.code, error.description)
        
        if result and result.get("success"):
            if result.get("api_response"):
                logger.info("Manueller Fehler erfolgreich an AnythingLLM API gesendet")
            else:
                logger.info("Manueller Fehler lokal gespeichert (API nicht verfügbar)")
            
            return {
                "success": True, 
                "message": f"Fehler {error.code} von {error.machine} erfolgreich gesendet",
                "result": result
            }
        else:
            logger.error("Manueller Fehler fehlgeschlagen")
            raise HTTPException(status_code=500, detail="Fehler beim Senden an AnythingLLM")
            
    except Exception as e:
        logger.exception("Manueller Fehler Exception: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test-error")
async def test_error():
    """Sendet einen Test-Fehler an AnythingLLM"""
    if not llm_client:
        logger.error("Test-Error Anfrage, aber LLM-Client nicht initialisiert")
        raise HTTPException(status_code=500, detail="AnythingLLM Client nicht initialisiert")
    
    logger.info("Sende Test-Fehler")
    
    try:
        result = llm_client.send_machine_error("Testmaschine_42", "E999", "Dies ist ein API-Test-Fehler")
        
        success = result is not None and result.get("success", False)
        logger.info("Test-Fehler Ergebnis: %s", "erfolgreich" if success else "fehlgeschlagen")
        
        return {
            "success": success,
            "result": result,
            "message": "Test-Fehler erfolgreich gesendet!" if result else "Test-Fehler fehlgeschlagen"
        }
    except Exception as e:
        logger.exception("Test-Error Exception: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# OPC UA Endpoints
@app.get("/opcua/status")
async def opcua_status():
    """Status aller OPC UA Server"""
    if not OPCUA_AVAILABLE:
        raise HTTPException(status_code=503, detail="OPC UA nicht verfügbar - asyncua nicht installiert")
    
    if not multi_opcua_client:
        raise HTTPException(status_code=503, detail="OPC UA nicht aktiviert")
    
    try:
        status = await multi_opcua_client.get_server_status()
        return status
    except Exception as e:
        logger.exception("Fehler beim OPC UA Status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/opcua/variables")
async def read_opcua_variables():
    """Liest alle OPC UA Variablen von allen verbundenen Servern"""
    if not multi_opcua_client:
        raise HTTPException(status_code=503, detail="OPC UA nicht verfügbar")
    
    try:
        variables = await multi_opcua_client.read_all_variables()
        return {
            "timestamp": datetime.now().isoformat(),
            "servers": variables,
            "total_variables": sum(len(server_vars) for server_vars in variables.values())
        }
    except Exception as e:
        logger.exception("Fehler beim Lesen der OPC UA Variablen: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/opcua/reconnect")
async def reconnect_opcua_servers():
    """Versucht Reconnect für getrennte OPC UA Server"""
    if not multi_opcua_client:
        raise HTTPException(status_code=503, detail="OPC UA nicht verfügbar")
    
    try:
        logger.info("OPC UA Reconnect angefordert")
        reconnect_results = await multi_opcua_client.reconnect_failed_servers()
        status = await multi_opcua_client.get_server_status()
        
        return {
            "message": "Reconnect-Versuch abgeschlossen",
            "reconnect_results": reconnect_results,
            "current_status": status
        }
    except Exception as e:
        logger.exception("Fehler beim OPC UA Reconnect: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/opcua/test-connection")
async def test_opcua_connection_endpoint(request: OPCUATestRequest):
    """Testet Verbindung zu einem OPC UA Server"""
    if not OPCUA_AVAILABLE:
        raise HTTPException(status_code=503, detail="OPC UA nicht verfügbar")
    
    try:
        logger.info("Teste OPC UA Verbindung zu: %s", request.server_url)
        success = await test_opcua_connection(request.server_url, request.timeout)
        
        return {
            "server_url": request.server_url,
            "connection_successful": success,
            "tested_at": datetime.now().isoformat(),
            "timeout": request.timeout
        }
    except Exception as e:
        logger.exception("Fehler beim OPC UA Verbindungstest: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# Auto-Generator Endpoints (bestehend)
@app.post("/auto-generator/start")
async def start_auto_generator():
    """Startet den Auto-Generator"""
    global auto_generator_enabled, generator_thread
    
    if auto_generator_enabled:
        logger.info("Auto-Generator start angefragt, läuft bereits")
        return {"message": "Auto-Generator läuft bereits", "status": "active"}
    
    logger.info("Starte Auto-Generator")
    try:
        auto_generator_enabled = True
        generator_thread = threading.Thread(target=auto_error_generator, daemon=True)
        generator_thread.start()
        return {"message": "Auto-Generator gestartet", "status": "started"}
    except Exception as e:
        logger.exception("Fehler beim Starten des Auto-Generators: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auto-generator/stop")
async def stop_auto_generator():
    """Stoppt den Auto-Generator"""
    global auto_generator_enabled
    
    if not auto_generator_enabled:
        logger.info("Auto-Generator stop angefragt, läuft nicht")
        return {"message": "Auto-Generator läuft nicht", "status": "inactive"}
    
    logger.info("Stoppe Auto-Generator")
    auto_generator_enabled = False
    
    return {"message": "Auto-Generator gestoppt", "status": "stopped"}

@app.get("/auto-generator/status")
async def auto_generator_status():
    """Status des Auto-Generators"""
    status_data = {
        "enabled": auto_generator_enabled,
        "status": "Aktiv" if auto_generator_enabled else "Inaktiv",
        "interval": f"{os.getenv('AUTO_GENERATOR_INTERVAL', '60')} Sekunden",
        "initial_delay": f"{os.getenv('AUTO_GENERATOR_INITIAL_DELAY', '10')} Sekunden",
        "demo_machines": len(DEMO_MACHINES),
        "demo_errors": len(DEMO_ERRORS)
    }
    
    logger.debug("Auto-Generator Status abgefragt: %s", status_data)
    return status_data

if __name__ == "__main__":
    # Startup-Wartezeit
    startup_delay = int(os.getenv("STARTUP_DELAY", "5"))
    
    if startup_delay > 0:
        print(f"Warte {startup_delay} Sekunden vor System-Start...")
        time.sleep(startup_delay)
    
    logger.info("Starte IoT-AnythingLLM Bridge...")
    logger.info("Umgebungsvariablen:")
    logger.info("   ANYTHINGLLM_URL: %s", os.getenv('ANYTHINGLLM_URL', 'NICHT_GESETZT'))
    logger.info("   ENABLE_OPCUA: %s", os.getenv('ENABLE_OPCUA', 'false'))
    logger.info("   ENABLE_MQTT: %s", os.getenv('ENABLE_MQTT', 'false'))
    logger.info("   ENABLE_AUTO_GENERATOR: %s", os.getenv('ENABLE_AUTO_GENERATOR', 'true'))
    logger.info("   LOG_LEVEL: %s", os.getenv('LOG_LEVEL', 'INFO'))
    logger.info("   LOG_FORMAT: %s", os.getenv('LOG_FORMAT', 'standard'))
    logger.info("   STARTUP_DELAY: %s Sekunden", startup_delay)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
