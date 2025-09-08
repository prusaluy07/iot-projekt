import requests
import os
import json
from typing import Optional
from datetime import datetime

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "DEIN_API_KEY")
        self.workspace_slug = "wago-edge-copilot"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(f"AnythingLLM Client initialisiert: {self.base_url}")
        print(f"Workspace: {self.workspace_slug}")

    def test_connection(self) -> bool:
        try:
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
        
        # Funktionierender Chat-Endpoint
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        
        payload = {
            "message": message
        }
        
        try:
            print(f"Sende an AnythingLLM Chat-API: {chat_url}")
            response = requests.post(
                chat_url,
                headers=self.headers,
                json=payload,
                timeout=15
            )
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"AnythingLLM Antwort: {result.get('textResponse', '')[:100]}...")
                    
                    # Erfolgreiche API-Antwort
                    return {
                        "success": True,
                        "api_response": True,
                        "anythingllm_response": result.get('textResponse', ''),
                        "sources": result.get('sources', []),
                        "conversation_id": payload.get('conversationId'),
                        "response_id": result.get('id')
                    }
                except json.JSONDecodeError:
                    print("Invalid JSON response")
                    return None
            else:
                print(f"API-Fehler: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"API-Fehler: {e}")
            return None

    def send_chat_message(self, message: str, conversation_id: str = None) -> Optional[dict]:
        """Sendet eine Chat-Nachricht an AnythingLLM"""
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        
        payload = {"message": message}
        if conversation_id:
            payload["conversationId"] = conversation_id
        
        try:
            response = requests.post(chat_url, headers=self.headers, json=payload, timeout=15)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Chat-Fehler: {e}")
            return None

def send_to_anythingllm(machine, code, description):
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
