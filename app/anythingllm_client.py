import requests
import os
import json
import time
import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime

CLIENT_VERSION = "v20250909_1151_004"

def log_and_print(level: str, message: str, *args):
    """Hilfsfunktion: Nur print-Ausgabe"""
    formatted_message = message % args if args else message
    
    # Nur Print-Ausgabe
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {formatted_message}")

class AnythingLLMClient:
    """Client für AnythingLLM API-Integration mit Retry-Mechanismus und Fallback"""
    
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "DEIN_API_KEY")
        self.workspace_slug = os.getenv("ANYTHINGLLM_WORKSPACE", "wago-edge-copilot")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.timeout = int(os.getenv("ANYTHINGLLM_TIMEOUT", "30"))
        self.max_retries = int(os.getenv("ANYTHINGLLM_RETRIES", "3"))
        
        log_and_print("INFO", "AnythingLLM Client initialisiert: %s", self.base_url)
        log_and_print("INFO", "Client Version: %s", CLIENT_VERSION)
        log_and_print("INFO", "Konfigurierter Workspace: %s", self.workspace_slug)
        log_and_print("INFO", "Timeout: %ds, Retries: %d", self.timeout, self.max_retries)

    def get_workspaces(self) -> Dict[str, Any]:
        """Ruft alle verfügbaren Workspaces ab"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/workspaces", 
                headers=self.headers, 
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                log_and_print("WARNING", "Workspaces abrufen fehlgeschlagen: HTTP %d", response.status_code)
                return {}
        except Exception as e:
            log_and_print("ERROR", "Fehler beim Abrufen der Workspaces: %s", e)
            return {}

    def log_available_workspaces(self):
        """Loggt alle verfügbaren Workspaces beim Startup"""
        log_and_print("INFO", "Lade verfügbare AnythingLLM Workspaces...")
        
        workspaces_data = self.get_workspaces()
        
        if not workspaces_data:
            log_and_print("WARNING", "Keine Workspaces gefunden oder API nicht erreichbar")
            return
        
        workspaces = workspaces_data.get("workspaces", [])
        
        if not workspaces:
            log_and_print("WARNING", "Workspace-Liste ist leer")
            return
        
        log_and_print("INFO", "Verfügbare Workspaces (%d gefunden):", len(workspaces))
        print("-" * 60)
        
        for workspace in workspaces:
            workspace_id = workspace.get("id")
            workspace_name = workspace.get("name", "Unbekannt")
            workspace_slug = workspace.get("slug", "unbekannt")
            created_at = workspace.get("createdAt", "")
            
            # Datum formatieren
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    created_str = created_at[:10]
            else:
                created_str = "Unbekannt"
            
            # Workspace-Status
            status_icon = "✅" if workspace_slug == self.workspace_slug else "⚪"
            
            log_and_print("INFO", "%s ID: %s | Name: %s", status_icon, workspace_id, workspace_name)
            log_and_print("INFO", "    Slug: %s | Erstellt: %s", workspace_slug, created_str)
            
            # API-URL für diesen Workspace
            api_url = f"{self.base_url}/api/v1/workspace/{workspace_slug}/chat"
            log_and_print("INFO", "    API: %s", api_url)
            print("")
        
        print("-" * 60)
        log_and_print("INFO", "Aktiver Workspace: %s", self.workspace_slug)
        
        # Prüfen ob der konfigurierte Workspace existiert
        configured_exists = any(ws.get("slug") == self.workspace_slug for ws in workspaces)
        if not configured_exists:
            log_and_print("ERROR", "WARNUNG: Konfigurierter Workspace '%s' nicht gefunden!", self.workspace_slug)
            available_slugs = [ws.get("slug") for ws in workspaces]
            log_and_print("ERROR", "Verfügbare Slugs: %s", available_slugs)

    def test_connection(self) -> bool:
        """Testet die Verbindung zu AnythingLLM"""
        try:
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    log_and_print("INFO", "AnythingLLM-Ping erfolgreich")
                    
                    # Nach erfolgreichem Ping Workspaces laden
                    self.log_available_workspaces()
                    return True
            log_and_print("WARNING", "AnythingLLM-Ping fehlgeschlagen: Status %d", response.status_code)
            return False
        except Exception as e:
            log_and_print("ERROR", "AnythingLLM-Verbindungstest fehlgeschlagen: %s", e)
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[Dict[str, Any]]:
        """Sendet Maschinenfehler an AnythingLLM mit Retry-Mechanismus"""
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        # Chat-URL und Payload vorbereiten
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        payload = {"message": message}
        
        log_and_print("INFO", "Starte API-Übertragung: %s/%s", machine, code)
        
        # Retry-Mechanismus
        for attempt in range(self.max_retries):
            try:
                log_and_print("INFO", "Sende an AnythingLLM (Versuch %d/%d)", attempt + 1, self.max_retries)
                
                response = requests.post(
                    chat_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                log_and_print("INFO", "AnythingLLM Response Status: %d", response.status_code)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        log_and_print("INFO", "AnythingLLM API erfolgreich (Versuch %d): %s/%s", 
                                      attempt + 1, machine, code)
                        
                        # ERFOLG: Sofort return - keine weiteren Versuche!
                        return {
                            "success": True,
                            "api_response": True,
                            "anythingllm_response": result.get('textResponse', ''),
                            "sources": result.get('sources', []),
                            "response_id": result.get('id'),
                            "attempt": attempt + 1,
                            "method": "api"
                        }
                        
                    except json.JSONDecodeError as e:
                        log_and_print("ERROR", "Invalid JSON response (Versuch %d): %s", attempt + 1, e)
                        log_and_print("DEBUG", "Raw response: %s", response.text[:500])
                        
                else:
                    log_and_print("WARNING", "HTTP Error %d (Versuch %d): %s", 
                                 response.status_code, attempt + 1, response.text[:200])
                             
            except requests.exceptions.Timeout:
                log_and_print("WARNING", "Timeout bei Versuch %d/%d (nach %ds)", 
                             attempt + 1, self.max_retries, self.timeout)
                             
            except requests.exceptions.ConnectionError as e:
                log_and_print("ERROR", "Verbindungsfehler bei Versuch %d: %s", attempt + 1, e)
                
            except Exception as e:
                log_and_print("ERROR", "API-Fehler bei Versuch %d: %s", attempt + 1, e)
                # Bei unerwarteten Fehlern: Retry-Schleife verlassen
                break
            
            # Wartezeit zwischen Versuchen (nur wenn nicht letzter Versuch)
            if attempt < self.max_retries - 1:
                # Längere Wartezeit bei Timeout
                wait_time = 5 if 'Timeout' in str(sys.exc_info()[1]) else 2
                log_and_print("INFO", "Warte %ds vor nächstem Versuch...", wait_time)
                time.sleep(wait_time)
        
        # Nur hier ankommen wenn ALLE Versuche fehlgeschlagen sind
        log_and_print("WARNING", "Alle %d API-Versuche fehlgeschlagen - verwende lokale Speicherung", 
                      self.max_retries)
        return self._store_locally(machine, code, description)

    def _store_locally(self, machine: str, code: str, description: str) -> Dict[str, Any]:
        """Speichert Maschinenfehler lokal als Fallback"""
        timestamp = datetime.now().isoformat()
        formatted_text = f"Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        error_data = {
            "timestamp": timestamp,
            "machine": machine,
            "code": code,
            "description": description,
            "formatted_text": formatted_text,
            "anythingllm_import_text": f"[Maschinenfehler OPC UA]\n{formatted_text}\n\nMaschine: {machine}\nFehlercode: {code}\nBeschreibung: {description}\nZeitstempel: {timestamp}\n" + "="*60
        }
        
        try:
            os.makedirs("/app/data", exist_ok=True)
            date_str = datetime.now().strftime('%Y%m%d')
            
            # JSON-Datei für strukturierte Daten
            json_filename = f"/app/data/machine_errors_{date_str}.json"
            if os.path.exists(json_filename):
                with open(json_filename, 'r', encoding='utf-8') as f:
                    errors = json.load(f)
            else:
                errors = []
            
            errors.append(error_data)
            
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(errors, f, indent=2, ensure_ascii=False)
            
            # Import-Text für AnythingLLM
            import_filename = f"/app/data/anythingllm_import_{date_str}.txt"
            with open(import_filename, 'a', encoding='utf-8') as f:
                f.write(f"\n{error_data['anythingllm_import_text']}\n")
            
            log_and_print("INFO", "Maschinenfehler lokal gespeichert: %s/%s", machine, code)
            log_and_print("DEBUG", "JSON: %s, Import: %s", json_filename, import_filename)
            
            return {
                "success": True,
                "local_storage": True,
                "api_response": False,
                "json_file": json_filename,
                "import_file": import_filename,
                "method": "local_storage"
            }
            
        except Exception as e:
            log_and_print("ERROR", "Lokale Speicherung fehlgeschlagen: %s", e)
            return {
                "success": False,
                "error": str(e),
                "method": "failed"
            }

    def send_chat_message(self, message: str, conversation_id: str = None) -> Optional[Dict[str, Any]]:
        """Sendet eine Chat-Nachricht an AnythingLLM"""
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        
        payload = {"message": message}
        if conversation_id:
            payload["conversationId"] = conversation_id
        
        try:
            log_and_print("DEBUG", "Sende Chat-Nachricht: %s", message[:100])
            response = requests.post(
                chat_url, 
                headers=self.headers, 
                json=payload, 
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                log_and_print("INFO", "Chat-Nachricht erfolgreich gesendet")
                return result
            else:
                log_and_print("WARNING", "Chat-Nachricht fehlgeschlagen: HTTP %d", response.status_code)
                return None
                
        except Exception as e:
            log_and_print("EXCEPTION", "Chat-Fehler: %s", e)
            return None

    def get_stored_errors(self, date: str = None) -> list:
        """Gibt gespeicherte Fehler zurück"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        filename = f"/app/data/machine_errors_{date}.json"
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            log_and_print("EXCEPTION", "Fehler beim Laden der Daten: %s", e)
            return []

    def get_import_text(self, date: str = None) -> str:
        """Gibt den Import-Text für AnythingLLM zurück"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        filename = f"/app/data/anythingllm_import_{date}.txt"
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return f.read()
            return "Keine Daten für dieses Datum gefunden."
        except Exception as e:
            log_and_print("EXCEPTION", "Fehler beim Laden des Import-Texts: %s", e)
            return f"Fehler beim Laden: {e}"

    def get_statistics(self) -> Dict[str, Any]:
        """Gibt Statistiken über gespeicherte Fehler zurück"""
        date_str = datetime.now().strftime('%Y%m%d')
        errors = self.get_stored_errors(date_str)
        
        if not errors:
            return {"total": 0, "machines": {}, "codes": {}, "date": date_str}
        
        machines = {}
        codes = {}
        
        for error in errors:
            machine = error.get("machine", "Unknown")
            code = error.get("code", "Unknown")
            
            machines[machine] = machines.get(machine, 0) + 1
            codes[code] = codes.get(code, 0) + 1
        
        return {
            "total": len(errors),
            "machines": machines,
            "codes": codes,
            "date": date_str,
            "latest_error": errors[-1] if errors else None
        }

    def health_check(self) -> Dict[str, Any]:
        """Vollständiger Gesundheitscheck"""
        health = {
            "anythingllm_ping": False,
            "workspace_exists": False,
            "api_key_valid": False,
            "local_storage": False,
            "config": {
                "base_url": self.base_url,
                "workspace_slug": self.workspace_slug,
                "timeout": self.timeout,
                "retries": self.max_retries
            }
        }
        
        # Ping-Test
        try:
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            health["anythingllm_ping"] = response.status_code == 200 and response.json().get("online", False)
        except:
            pass
        
        # Workspace-Test
        if health["anythingllm_ping"]:
            workspaces_data = self.get_workspaces()
            workspaces = workspaces_data.get("workspaces", [])
            health["workspace_exists"] = any(ws.get("slug") == self.workspace_slug for ws in workspaces)
            health["api_key_valid"] = len(workspaces) > 0  # Wenn wir Workspaces bekommen, ist der Key gültig
        
        # Lokale Speicherung testen
        try:
            os.makedirs("/app/data", exist_ok=True)
            test_file = "/app/data/health_check.tmp"
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            health["local_storage"] = True
        except:
            pass
        
        return health


def send_to_anythingllm(machine: str, code: str, description: str) -> Optional[Dict[str, Any]]:
    """Kompatibilitätsfunktion für einfache Nutzung"""
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)


def show_stored_errors():
    """Hilfsfunktion: Zeigt alle gespeicherten Fehler des heutigen Tages"""
    client = AnythingLLMClient()
    errors = client.get_stored_errors()
    
    if not errors:
        print("Keine gespeicherten Fehler für heute gefunden.")
        return
    
    print(f"Gespeicherte Fehler heute ({len(errors)} Stück):")
    print("-" * 60)
    
    for error in errors:
        timestamp = error.get('timestamp', 'Unknown')
        machine = error.get('machine', 'Unknown')
        code = error.get('code', 'Unknown')
        description = error.get('description', 'No description')
        
        print(f"{timestamp}: {machine}/{code} - {description}")


def get_anythingllm_import_text() -> str:
    """Hilfsfunktion: Gibt den Import-Text für AnythingLLM zurück"""
    client = AnythingLLMClient()
    return client.get_import_text()


if __name__ == "__main__":
    # Test-Skript
    print("AnythingLLM Client Test")
    print("=" * 40)
    
    client = AnythingLLMClient()
    
    # Verbindungstest
    if client.test_connection():
        print("✅ Verbindung erfolgreich")
        
        # Health Check
        health = client.health_check()
        print(f"Health Check: {health}")
        
        # Test-Nachricht senden
        result = client.send_machine_error("TestMaschine", "E999", "Client-Test")
        print(f"Test-Ergebnis: {result}")
        
        # Statistiken
        stats = client.get_statistics()
        print(f"Statistiken: {stats}")
        
    else:
        print("❌ Verbindung fehlgeschlagen")
