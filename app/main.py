import asyncio
import json
import os
import time
import random
from contextlib import asynccontextmanager
from datetime import datetime
from anythingllm_client import AnythingLLMClient, send_to_anythingllm
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import threading

# Datenmodelle
class ErrorMessage(BaseModel):
    machine: str
    code: str
    description: str

# Globale Variablen
llm_client = None
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

def log_with_timestamp(message: str):
    """Gibt Nachrichten mit Zeitstempel aus"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

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
    
    log_with_timestamp(f"Auto-Generator gestartet - warte {initial_delay} Sekunden vor erstem Fehler")
    
    # Einmalige Wartezeit nach Start
    for i in range(initial_delay):
        if not auto_generator_enabled:
            log_with_timestamp("Auto-Generator während Initialisierung gestoppt")
            return
        time.sleep(1)
    
    log_with_timestamp(f"Auto-Generator initialisiert - beginne mit Fehlergeneration (alle {interval} Sekunden)")
    
    while auto_generator_enabled:
        try:
            # Zufälligen Fehler generieren
            machine, code, description = generate_random_error()
            
            log_with_timestamp(f"Generiere Auto-Fehler: {machine}/{code}")
            
            if llm_client:
                result = llm_client.send_machine_error(machine, code, description)
                if result and result.get("success"):
                    log_with_timestamp(f"Auto-Fehler erfolgreich verarbeitet")
                else:
                    log_with_timestamp(f"Auto-Fehler fehlgeschlagen")
            else:
                log_with_timestamp("LLM-Client nicht verfügbar")
            
            # Warten bis zum nächsten Fehler
            for i in range(interval):
                if not auto_generator_enabled:
                    break
                time.sleep(1)
            
            if not auto_generator_enabled:
                break
                
        except Exception as e:
            log_with_timestamp(f"Auto-Generator Fehler: {e}")
    
    log_with_timestamp("Auto-Generator gestoppt")
    
def setup_mqtt():
    """MQTT Client Setup - Optional"""
    global mqtt_client, mqtt_enabled
    
    if os.getenv("ENABLE_MQTT", "false").lower() != "true":
        log_with_timestamp("MQTT deaktiviert (ENABLE_MQTT=false)")
        return False
    
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            log_with_timestamp("✅ MQTT erfolgreich verbunden")
            client.subscribe("machines/+/errors")
            client.subscribe("opc/+/alarms")
            global mqtt_enabled
            mqtt_enabled = True
        else:
            log_with_timestamp(f"❌ MQTT Verbindung fehlgeschlagen: {rc}")

    def on_message(client, userdata, msg):
        """Verarbeitet eingehende MQTT-Nachrichten"""
        try:
            topic_parts = msg.topic.split('/')
            machine = topic_parts[1] if len(topic_parts) > 1 else "unknown"
            
            payload = json.loads(msg.payload.decode())
            error_code = payload.get('code', 'unknown')
            description = payload.get('description', 'Keine Beschreibung')
            
            log_with_timestamp(f"📨 MQTT empfangen: {machine}/{error_code}")
            
            if llm_client:
                llm_client.send_machine_error(machine, error_code, description)
            
        except json.JSONDecodeError:
            log_with_timestamp("❌ Ungültige JSON in MQTT-Nachricht")
        except Exception as e:
            log_with_timestamp(f"❌ MQTT-Verarbeitung fehlgeschlagen: {e}")

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    
    try:
        log_with_timestamp(f"🔗 Verbinde mit MQTT Broker: {mqtt_broker}:{mqtt_port}")
        mqtt_client.connect(mqtt_broker, mqtt_port, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        log_with_timestamp(f"❌ MQTT Verbindung fehlgeschlagen: {e}")
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global llm_client, auto_generator_enabled, generator_thread
    log_with_timestamp("🚀 IoT-AnythingLLM Bridge startet...")
    
    # AnythingLLM Client initialisieren
    llm_client = AnythingLLMClient()
    
    # AnythingLLM testen
    if llm_client.test_connection():
        log_with_timestamp("✅ AnythingLLM bereit")
    else:
        log_with_timestamp("⚠️ AnythingLLM nicht erreichbar")
    
    # MQTT setup (optional)
    if setup_mqtt():
        log_with_timestamp("✅ MQTT bereit")
    else:
        log_with_timestamp("ℹ️ MQTT nicht verfügbar")
    
    # Auto-Generator starten
    auto_generator_enabled = os.getenv("ENABLE_AUTO_GENERATOR", "true").lower() == "true"
    if auto_generator_enabled:
        generator_thread = threading.Thread(target=auto_error_generator, daemon=True)
        generator_thread.start()
    
    log_with_timestamp("🎉 Bridge erfolgreich gestartet!")
    
    yield
    
    # Shutdown
    log_with_timestamp("🛑 Bridge wird heruntergefahren...")
    auto_generator_enabled = False
    if mqtt_client and mqtt_enabled:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

# FastAPI App mit Lifespan
app = FastAPI(
    title="IoT-OPC-AnythingLLM Bridge",
    description="Bridge zwischen OPC UA/MQTT und AnythingLLM mit Auto-Generator",
    version="1.1.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {
        "message": "IoT-AnythingLLM Bridge läuft",
        "version": "1.1.0",
        "timestamp": datetime.now().isoformat(),
        "anythingllm_status": "✅ Verbunden" if llm_client and llm_client.test_connection() else "❌ Getrennt",
        "mqtt_status": "✅ Verbunden" if mqtt_enabled else "⚪ Deaktiviert",
        "auto_generator": "✅ Aktiv" if auto_generator_enabled else "⚪ Deaktiviert",
        "endpoints": {
            "manual_error": "/manual-error",
            "test": "/test",
            "status": "/status",
            "test_error": "/test-error",
            "auto_generator": "/auto-generator"
        }
    }

@app.get("/status")
async def status():
    """Status der Bridge"""
    anythingllm_status = llm_client.test_connection() if llm_client else False
    
    return {
        "anythingllm": "✅ Online" if anythingllm_status else "❌ Offline",
        "mqtt": "✅ Online" if mqtt_enabled else "⚪ Deaktiviert",
        "auto_generator": "✅ Aktiv" if auto_generator_enabled else "⚪ Deaktiviert",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/manual-error")
async def manual_error(error: ErrorMessage):
    """Manuelles Senden eines Fehlers an AnythingLLM"""
    if not llm_client:
        raise HTTPException(status_code=500, detail="AnythingLLM Client nicht initialisiert")
    
    log_with_timestamp(f"📝 Manueller Fehler: {error.machine}/{error.code}")
    
    try:
        result = llm_client.send_machine_error(error.machine, error.code, error.description)
        
        if result and result.get("success"):
            log_with_timestamp(f"✅ Manueller Fehler erfolgreich verarbeitet")
            return {
                "success": True, 
                "message": f"Fehler {error.code} von {error.machine} erfolgreich gesendet",
                "result": result
            }
        else:
            log_with_timestamp(f"❌ Manueller Fehler fehlgeschlagen")
            raise HTTPException(status_code=500, detail="Fehler beim Senden an AnythingLLM")
            
    except Exception as e:
        log_with_timestamp(f"❌ Manueller Fehler Exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test")
async def test_all():
    """Testet alle Verbindungen"""
    log_with_timestamp("🧪 Teste alle Verbindungen")
    
    if not llm_client:
        return {"error": "AnythingLLM Client nicht initialisiert"}
    
    anythingllm_test = llm_client.test_connection()
    
    return {
        "anythingllm_test": "✅ Erfolgreich" if anythingllm_test else "❌ Fehlgeschlagen",
        "mqtt_status": "✅ Verbunden" if mqtt_enabled else "⚪ Deaktiviert",
        "auto_generator": "✅ Aktiv" if auto_generator_enabled else "⚪ Deaktiviert",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/test-error")
async def test_error():
    """Sendet einen Test-Fehler an AnythingLLM"""
    if not llm_client:
        raise HTTPException(status_code=500, detail="AnythingLLM Client nicht initialisiert")
    
    log_with_timestamp("🧪 Sende Test-Fehler")
    
    result = llm_client.send_machine_error("Testmaschine_42", "E999", "Dies ist ein API-Test-Fehler")
    return {
        "success": result is not None and result.get("success", False),
        "result": result,
        "message": "Test-Fehler erfolgreich gesendet!" if result else "Test-Fehler fehlgeschlagen"
    }

@app.post("/auto-generator/start")
async def start_auto_generator():
    """Startet den Auto-Generator"""
    global auto_generator_enabled, generator_thread
    
    if auto_generator_enabled:
        return {"message": "Auto-Generator läuft bereits", "status": "active"}
    
    log_with_timestamp("🚀 Starte Auto-Generator")
    auto_generator_enabled = True
    generator_thread = threading.Thread(target=auto_error_generator, daemon=True)
    generator_thread.start()
    
    return {"message": "Auto-Generator gestartet", "status": "started"}

@app.post("/auto-generator/stop")
async def stop_auto_generator():
    """Stoppt den Auto-Generator"""
    global auto_generator_enabled
    
    if not auto_generator_enabled:
        return {"message": "Auto-Generator läuft nicht", "status": "inactive"}
    
    log_with_timestamp("🛑 Stoppe Auto-Generator")
    auto_generator_enabled = False
    
    return {"message": "Auto-Generator gestoppt", "status": "stopped"}

@app.get("/auto-generator/status")
async def auto_generator_status():
    """Status des Auto-Generators"""
    return {
        "enabled": auto_generator_enabled,
        "status": "🟢 Aktiv" if auto_generator_enabled else "🔴 Inaktiv",
        "interval": "60 Sekunden",
        "demo_machines": len(DEMO_MACHINES),
        "demo_errors": len(DEMO_ERRORS)
    }

if __name__ == "__main__":
    # Konfigurierbare Startup-Wartezeit
    startup_delay = int(os.getenv("STARTUP_DELAY", "15"))
    
    if startup_delay > 0:
        print(f"Warte {startup_delay} Sekunden vor System-Start...")
        time.sleep(startup_delay)
    
    log_with_timestamp("🚀 Starte IoT-AnythingLLM Bridge...")
    log_with_timestamp("📋 Umgebungsvariablen:")
    log_with_timestamp(f"   ANYTHINGLLM_URL: {os.getenv('ANYTHINGLLM_URL', 'NICHT_GESETZT')}")
    log_with_timestamp(f"   ENABLE_MQTT: {os.getenv('ENABLE_MQTT', 'false')}")
    log_with_timestamp(f"   ENABLE_AUTO_GENERATOR: {os.getenv('ENABLE_AUTO_GENERATOR', 'true')}")
    log_with_timestamp(f"   STARTUP_DELAY: {startup_delay} Sekunden")
    log_with_timestamp(f"   AUTO_GENERATOR_INITIAL_DELAY: {os.getenv('AUTO_GENERATOR_INITIAL_DELAY', '10')} Sekunden")
    log_with_timestamp(f"   AUTO_GENERATOR_INTERVAL: {os.getenv('AUTO_GENERATOR_INTERVAL', '60')} Sekunden")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
