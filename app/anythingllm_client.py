import requests
import os
from typing import Optional
from datetime import datetime

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.widget_uuid = "68d8890d-7266-47f0-912f-672fc5c0afc7"
        self.embed_api_url = f"{self.base_url}/api/embed"
        print(f"🔗 AnythingLLM Embed-Widget initialisiert: {self.embed_api_url}")
        print(f"🎯 Widget UUID: {self.widget_uuid}")

    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    print("✅ AnythingLLM-Verbindung erfolgreich getestet")
                    return True
            return False
        except Exception as e:
            print(f"❌ AnythingLLM-Verbindungstest fehlgeschlagen: {e}")
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeitstempel: {timestamp})"
        
        # Embed-Chat-API verwenden (aus dem Widget-Code)
        chat_endpoint = f"{self.embed_api_url}/{self.widget_uuid}/chat"
        
        payload = {"message": message}
        
        try:
            print(f"📤 Sende an Embed-Widget: {chat_endpoint}")
            response = requests.post(
                chat_endpoint,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=15
            )
            
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:300]}")
            
            if response.status_code == 200:
                print(f"✅ Maschinenfehler erfolgreich an AnythingLLM gesendet")
                try:
                    return response.json()
                except:
                    return {"success": True, "raw_response": response.text}
            else:
                print(f"❌ Widget-API Fehler: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Widget-API Fehler: {e}")
            return None

def send_to_anythingllm(machine, code, description):
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
