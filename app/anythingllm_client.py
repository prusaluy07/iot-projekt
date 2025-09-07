import requests
import os
from typing import Optional
from datetime import datetime

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "KE7053N-30JM5PZ-KAPMXDP-KXJQC3N")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(f"AnythingLLM Client initialisiert: {self.base_url}")

    def test_connection(self) -> bool:
        try:
            # Ping funktioniert ohne Auth
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    print("AnythingLLM-Verbindung erfolgreich getestet")
                    return True
            return False
        except Exception as e:
            print(f"AnythingLLM-Verbindungstest fehlgeschlagen: {e}")
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        # Workspace-Chat-API (die einzige mit JSON-Response)
        chat_endpoints = [
            {
                "url": f"{self.base_url}/api/v1/workspace/1/chat",
                "payload": {"message": message}
            },
            {
                "url": f"{self.base_url}/api/v1/workspace/wago-edge-copilot/chat", 
                "payload": {"message": message}
            },
            {
                "url": f"{self.base_url}/api/v1/workspace/1/chat",
                "payload": {"message": message, "sessionId": "iot-bridge-session"}
            }
        ]
        
        for endpoint in chat_endpoints:
            try:
                print(f"Teste Workspace-Chat: {endpoint['url']}")
                response = requests.post(
                    endpoint['url'],
                    headers=self.headers,
                    json=endpoint['payload'],
                    timeout=15
                )
                
                print(f"Status: {response.status_code}")
                response_text = response.text[:300]
                print(f"Response: {response_text}")
                
                # Prüfen ob JSON-Response (kein HTML)
                if not response_text.strip().startswith('<!DOCTYPE'):
                    if response.status_code == 200:
                        print("Workspace-Chat erfolgreich!")
                        try:
                            return response.json()
                        except:
                            return {"success": True, "response": response_text}
                    else:
                        print(f"JSON-Error: {response_text}")
                        
            except Exception as e:
                print(f"Fehler: {e}")
                continue
        
        print("Workspace-Chat fehlgeschlagen - verwende lokale Speicherung")
        return self._store_locally(machine, code, description)

def send_to_anythingllm(machine, code, description):
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
