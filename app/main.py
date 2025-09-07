import asyncio
import json
import os
import time
from datetime import datetime
from anythingllm_client import AnythingLLMClient, send_to_anythingllm
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Datenmodelle
class ErrorMessage(BaseModel):
    machine: str
    code: str
    description: str

# FastAPI App
app = FastAPI(
    title="IoT-OPC-AnythingLLM Bridge",
    description="Bridge zwischen OPC UA/MQTT und AnythingLLM",
    version="1.0.0"
)

# AnythingLLM Client
llm_client = AnythingLLMClient()

# MQTT Client Setup
mqtt_client = None

def setup_mqtt():
    """MQTT Client Setup"""
    global mqtt_client
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ MQTT erfolgreich verbunden")
            client.subscribe("machines/+/errors")
            client.subscribe("opc/+/alarms")
        else:
            print(f"❌ MQTT Verbindung fehlgeschlagen: {rc}")

    def on_message(client, userdata, msg):
        """Verarbeitet eingehende MQTT-Nachrichten"""
        try:
            topic_parts = msg.topic.split('/')
            machine = topic_parts[1] if len(topic_parts) > 1 else "unknown"
            
            payload = json.loads(msg.payload.decode())
            error_code = payload.get('code', 'unknown')
            description = payload.get('description', 'Keine Beschreibung')
            
            print(f"📨 MQTT empfangen: {machine}/{error_code}")
            
            # An AnythingLLM senden
            llm_client.send_machine_error(machine, error_code, description)
            
        except json.JSONDecodeError:
            print("❌ Ungültige JSON in MQTT-Nachricht")
        except Exception as e:
            print(f"❌ Fehler beim Verarbeiten der MQTT-Nachricht: {e}")

    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    # MQTT Broker verbinden
    mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    
    try:
        print(f"🔗 Verbinde mit MQTT Broker: {mqtt_broker}:{mqtt_port}")
        mqtt_client.connect(mqtt_broker, mqtt_port, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        print(f"❌ MQTT Verbindung fehlgeschlagen: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    print("🚀 IoT-AnythingLLM Bridge startet...")
    
    # AnythingLLM testen
    if llm_client.test_connection():
        print("✅ AnythingLLM bereit")
    else:
        print("⚠️  AnythingLLM nicht erreichbar - aber App startet trotzdem")
    
    # MQTT setup
    if setup_mqtt():
        print("✅ MQTT bereit")
    else:
        print("⚠️  MQTT nicht verfügbar - aber App startet trotzdem")
    
    print("🎉 Bridge erfolgreich gestartet!")

@app.get("/")
async def root():
    return {
        "message": "IoT-AnythingLLM Bridge läuft",
        "version": "1.0.0",
        "endpoints": {
            "manual_error": "/manual-error",
            "test": "/test",
            "status": "/status"
        }
    }

@app.get("/status")
async def status():
    """Status der Bridge"""
    anythingllm_status = llm_client.test_connection()
    
    return {
        "anythingllm": "✅ Online" if anythingllm_status else "❌ Offline",
        "mqtt": "✅ Online" if mqtt_client and mqtt_client.is_connected() else "❌ Offline",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/manual-error")
async def manual_error(error: ErrorMessage):
    """Manuelles Senden eines Fehlers an AnythingLLM"""
    try:
        result = llm_client.send_machine_error(error.machine, error.code, error.description)
        
        if result:
            return {
                "success": True, 
                "message": f"Fehler {error.code} von {error.machine} erfolgreich gesendet",
                "result": result
            }
        else:
            raise HTTPException(status_code=500, detail="Fehler beim Senden an AnythingLLM")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test")
async def test_all():
    """Testet alle Verbindungen"""
    # Test AnythingLLM
    test_result = send_to_anythingllm("TestMaschine", "TEST001", "Verbindungstest")
    
    return {
        "anythingllm_test": "✅ Erfolgreich" if test_result else "❌ Fehlgeschlagen",
        "mqtt_status": "✅ Verbunden" if mqtt_client and mqtt_client.is_connected() else "❌ Getrennt",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/test-error")
async def test_error():
    """Sendet einen Test-Fehler"""
    result = send_to_anythingllm("Testmaschine_42", "E999", "Dies ist ein Testfehler vom IoT-Bridge")
    return {"success": result is not None, "result": result}

if __name__ == "__main__":
    print("🚀 Starte IoT-AnythingLLM Bridge...")
    print("📋 Umgebungsvariablen:")
    print(f"   ANYTHINGLLM_URL: {os.getenv('ANYTHINGLLM_URL', 'NICHT_GESETZT')}")
    print(f"   MQTT_BROKER: {os.getenv('MQTT_BROKER', 'NICHT_GESETZT')}")
    
    # FastAPI Server starten
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info"
    )