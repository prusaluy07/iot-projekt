import requests
import os
import json
from typing import Optional
from datetime import datetime
import uuid

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.widget_uuid = "68d8890d-7266-47f0-912f-672fc5c0afc7"
        self.session_id = str(uuid.uuid4())  # Eindeutige Session für diese Client-Instanz
        print(f"🔗 AnythingLLM Widget initialisiert: {self.base_url}")
        print(f"🎯 Widget: {self.widget_uuid}")
        print(f"📱 Session: {self.session_id}")

    def test_connection(self) -> bool:
        try:
            # Widget-Status prüfen (wir wissen, dass das funktioniert)
            response = requests.get(
                f"{self.base_url}/api/embed/{self.widget_uuid}",
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                print("✅ Widget-Verbindung erfolgreich getestet")
                print(f"   Chat-History: {len(result.get('history', []))} Nachrichten")
                return True
            return False
        except Exception as e:
            print(f"❌ Widget-Verbindungstest fehlgeschlagen: {e}")
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        chat_endpoint = f"{self.base_url}/api/embed/{self.widget_uuid}/chat"
        
        # Verschiedene Payload-Formate für Widget-Chat
        payloads = [
            # Mit Session-ID
            {
                "message": message,
                "sessionId": self.session_id
            },
            # Ohne Stream
            {
                "message": message,
                "stream": False
            },
            # Minimal
            {
                "message": message
            },
            # Mit Mode
            {
                "message": message,
                "mode": "query"
            }
        ]
        
        for i, payload in enumerate(payloads):
            try:
                print(f"📤 Teste Widget-Chat Format {i+1}: {payload}")
                response = requests.post(
                    chat_endpoint,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=15
                )
                
                print(f"   Status: {response.status_code}")
                response_text = response.text[:300]
                print(f"   Response: {response_text}")
                
                if response.status_code == 200:
                    print(f"✅ Widget-Chat erfolgreich mit Format {i+1}")
                    try:
                        return response.json()
                    except:
                        return {"success": True, "format": i+1, "response": response_text}
                        
            except Exception as e:
                print(f"   Fehler: {e}")
                continue
        
        print("❌ Alle Widget-Chat-Formate fehlgeschlagen")
        return None

def send_to_anythingllm(machine, code, description):
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
