import requests
import os
import json
import time
import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime

CLIENT_VERSION = "v20250909_2012_006"

def get_status_icon(status_type: str, value: Any) -> str:
    """Gibt dynamisches Icon basierend auf Status und Wert zurück"""
    
    if status_type == "http_status":
        if 200 <= value < 300:
            return "🟢"  # Erfolg
        elif 300 <= value < 400:
            return "🔵"  # Umleitung/Info
        elif 400 <= value < 500:
            return "🔴"  # Client-Fehler
        elif 500 <= value:
            return "🟡"  # Server-Fehler
        else:
            return "⚪"  # Unbekannt
    
    elif status_type == "connection":
        if value in ["connected", "online", "bereit", "erfolgreich"]:
            return "🟢"
        elif value in ["connecting", "standby", "wartet", "verarbeitung"]:
            return "🔵"
        elif value in ["warning", "teilweise", "timeout"]:
            return "🟡"
        elif value in ["disconnected", "offline", "fehler", "fehlgeschlagen"]:
            return "🔴"
        else:
            return "⚪"
    
    elif status_type == "process":
        if value in ["success", "completed", "erfolgreich"]:
            return "🟢"
        elif value in ["running", "processing", "läuft"]:
            return "🔵"
        elif value in ["warning", "partial", "warnung"]:
            return "🟡"
        elif value in ["error", "failed", "fehler"]:
            return "🔴"
        else:
            return "⚪"
    
    elif status_type == "retry_attempt":
        if value == 1:
            return "🔵"  # Erster Versuch
        elif value <= 3:
            return "🟡"  # Weitere Versuche
        else:
            return "🔴"  # Viele Versuche
    
    return "⚪"  # Default

def log_and_print(level: str, message: str, *args):
    """Hilfsfunktion: Nur print-Ausgabe mit Level-Icons"""
    formatted_message = message % args if args else message
    
    # Level-spezifische Icons
    level_icons = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "DEBUG": "🔍",
        "SUCCESS": "✅"
    }
    
    level_icon = level_icons.get(level, "📝")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level_icon} {formatted_message}")

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
        
        log_and_print("INFO", "▶️ AnythingLLM Client initialisiert: %s", self.base_url)
        log_and_print("INFO", "📊 Client Version: %s", CLIENT_VERSION)
        log_and_print("INFO", "🗂️ Konfigurierter Workspace: %s", self.workspace_slug)
        log_and_print("INFO", "⏳ Timeout: %ds, Retries: %d", self.timeout, self.max_retries)

    def get_workspaces(self) -> Dict[str, Any]:
        """Ruft alle verfügbaren Workspaces ab"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/workspaces", 
                headers=self.headers, 
                timeout=10
            )
            
            status_icon = get_status_icon("http_status", response.status_code)
            
            if response.status_code == 200:
                log_and_print("INFO", "%s Workspaces erfolgreich abgerufen (HTTP %d)", status_icon, response.status_code)
                return response.json()
            else:
                log_and_print("WARNING", "%s Workspaces abrufen fehlgeschlagen: HTTP %d", status_icon, response.status_code)
                return {}
        except Exception as e:
            log_and_print("ERROR", "%s Fehler beim Abrufen der Workspaces: %s", get_status_icon("connection", "fehler"), e)
            return {}

    def log_available_workspaces(self):
        """Loggt alle verfügbaren Workspaces beim Startup"""
        log_and_print("INFO", "🔄 Lade verfügbare AnythingLLM Workspaces...")
        
        workspaces_data = self.get_workspaces()
        
        if not workspaces_data:
            log_and_print("WARNING", "%s Keine Workspaces gefunden oder API nicht erreichbar", get_status_icon("connection", "offline"))
            return
        
        workspaces = workspaces_data.get("workspaces", [])
        
        if not workspaces:
            log_and_print("WARNING", "%s Workspace-Liste ist leer", get_status_icon("process", "warning"))
            return
        
        log_and_print("INFO", "📁 Verfügbare Workspaces (%d gefunden):", len(workspaces))
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
            is_active = workspace_slug == self.workspace_slug
            status_icon = get_status_icon("connection", "online" if is_active else "standby")
            
            log_and_print("INFO", "%s ID: %s | Name: %s", status_icon, workspace_id, workspace_name)
            log_and_print("INFO", "    📅 Slug: %s | Erstellt: %s", workspace_slug, created_str)
            
            # API-URL für diesen Workspace
            api_url = f"{self.base_url}/api/v1/workspace/{workspace_slug}/chat"
            log_and_print("INFO", "    🔗 API: %s", api_url)
            print("")
        
        print("-" * 60)
        log_and_print("INFO", "%s Aktiver Workspace: %s", get_status_icon("connection", "online"), self.workspace_slug)
        
        # Prüfen ob der konfigurierte Workspace existiert
        configured_exists = any(ws.get("slug") == self.workspace_slug for ws in workspaces)
        if not configured_exists:
            log_and_print("ERROR", "%s WARNUNG: Konfigurierter Workspace '%s' nicht gefunden!", 
                         get_status_icon("connection", "fehler"), self.workspace_slug)
            available_slugs = [ws.get("slug") for ws in workspaces]
            log_and_print("ERROR", "%s Verfügbare Slugs: %s", get_status_icon("process", "fehler"), available_slugs)

    def test_connection(self) -> bool:
        """Testet die Verbindung zu AnythingLLM"""
        try:
            log_and_print("INFO", "🔍 Teste AnythingLLM Verbindung...")
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            
            status_icon = get_status_icon("http_status", response.status_code)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    log_and_print("SUCCESS", "%s AnythingLLM-Ping erfolgreich (HTTP %d)", 
                                 status_icon, response.status_code)
                    
                    # Nach erfolgreichem Ping Workspaces laden
                    self.log_available_workspaces()
                    return True
            
            log_and_print("WARNING", "%s AnythingLLM-Ping fehlgeschlagen: Status %d", 
                         status_icon, response.status_code)
            return False
            
        except Exception as e:
            log_and_print("ERROR", "%s AnythingLLM-Verbindungstest fehlgeschlagen: %s", 
                         get_status_icon("connection", "fehler"), e)
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[Dict[str, Any]]:
        """Sendet Maschinenfehler an AnythingLLM mit Retry-Mechanismus"""
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        # Chat-URL und Payload vorbereiten
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        payload = {"message": message}
        
        log_and_print("INFO", "🚀 Starte API-Übertragung: %s/%s", machine, code)
        
        # Retry-Mechanismus
        for attempt in range(self.max_retries):
            try:
                attempt_icon = get_status_icon("retry_attempt", attempt + 1)
                log_and_print("INFO", "%s Sende an AnythingLLM (Versuch %d/%d)", 
                             attempt_icon, attempt + 1, self.max_retries)
                
                response = requests.post(
                    chat_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                status_icon = get_status_icon("http_status", response.status_code)
                log_and_print("INFO", "%s AnythingLLM Response Status: %d", status_icon, response.status_code)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        log_and_print("SUCCESS", "%s AnythingLLM API erfolgreich (Versuch %d): %s/%s", 
                                      get_status_icon("process", "success"), attempt + 1, machine, code)
                        
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
                        log_and_print("ERROR", "%s Invalid JSON response (Versuch %d): %s", 
                                     get_status_icon("process", "fehler"), attempt + 1, e)
                        log_and_print("DEBUG", "Raw response: %s", response.text[:500])
                        
                else:
                    log_and_print("WARNING", "%s HTTP Error %d (Versuch %d): %s", 
                                 status_icon, response.status_code, attempt + 1, response.text[:200])
                             
            except requests.exceptions.Timeout:
                log_and_print("WARNING", "%s Timeout bei Versuch %d/%d (nach %ds)", 
                             get_status_icon("connection", "timeout"), attempt + 1, self.max_retries, self.timeout)
                             
            except requests.exceptions.ConnectionError as e:
                log_and_print("ERROR", "%s Verbindungsfehler bei Versuch %d: %s", 
                             get_status_icon("connection", "fehler"), attempt + 1, e)
                
            except Exception as e:
                log_and_print("ERROR", "%s API-Fehler bei Versuch %d: %s", 
                             get_status_icon("process", "fehler"), attempt + 1, e)
                # Bei unerwarteten Fehlern: Retry-Schleife verlassen
                break
            
            # Wartezeit zwischen Versuchen (nur wenn nicht letzter Versuch)
            if attempt < self.max_retries - 1:
                # Längere Wartezeit bei Timeout
                wait_time = 5 if 'Timeout' in str(sys.exc_info()[1]) else 2
                log_and_print("INFO", "%s Warte %ds vor nächstem Versuch...", 
                             get_status_icon("process", "wartet"), wait_time)
                time.sleep(wait_time)
        
        # Nur hier ankommen wenn ALLE Versuche fehlgeschlagen sind
        log_and_print("ERROR", "%s %s %s Alle %d API-Versuche fehlgeschlagen - verwende lokale Speicherung", 
                      get_status_icon("process", "fehler"), get_status_icon("process", "fehler"), 
                      get_status_icon("process", "fehler"), self.max_retries)
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
            
            log_and_print("SUCCESS", "%s Maschinenfehler lokal gespeichert: %s/%s", 
                         get_status_icon("process", "success"), machine, code)
            log_and_print("DEBUG", "📁 JSON: %s, 📄 Import: %s", json_filename, import_filename)
            
            return {
                "success": True,
                "local_storage": True,
                "api_response": False,
                "json_file": json_filename,
                "import_file": import_filename,
                "method": "local_storage"
            }
            
        except Exception as e:
            log_and_print("ERROR", "%s Lokale Speicherung fehlgeschlagen: %s", 
                         get_status_icon("process", "fehler"), e)
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
            log_and_print("DEBUG", "💬 Sende Chat-Nachricht: %s", message[:100])
            response = requests.post(
                chat_url, 
                headers=self.headers, 
                json=payload, 
                timeout=self.timeout
            )
            
            status_icon = get_status_icon("http_status", response.status_code)
            
            if response.status_code == 200:
                result = response.json()
                log_and_print("SUCCESS", "%s Chat-Nachricht erfolgreich gesendet", status_icon)
                return result
            else:
                log_and_print("WARNING", "%s Chat-Nachricht fehlgeschlagen: HTTP %d", 
                             status_icon, response.status_code)
                return None
                
        except Exception as e:
            log_and_print("ERROR", "%s Chat-Fehler: %s", get_status_icon("process", "fehler"), e)
            return None

    def get_stored_errors(self, date: str = None) -> list:
        """Gibt gespeicherte Fehler zurück"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        filename = f"/app/data/machine_errors_{date}.json"
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    errors = json.load(f)
                    log_and_print("SUCCESS", "%s %d Fehler aus lokaler Datei geladen", 
                                 get_status_icon("process", "success"), len(errors))
                    return errors
            log_and_print("INFO", "%s Keine lokalen Fehler für %s gefunden", 
                         get_status_icon("process", "standby"), date)
            return []
        except Exception as e:
            log_and_print("ERROR", "%s Fehler beim Laden der Daten: %s", 
                         get_status_icon("process", "fehler"), e)
            return []

    def health_check(self) -> Dict[str, Any]:
        """Vollständiger Gesundheitscheck"""
        log_and_print("INFO", "🏥 Führe Gesundheitscheck durch...")
        
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
            
            ping_icon = get_status_icon("connection", "online" if health["anythingllm_ping"] else "offline")
            log_and_print("INFO", "%s Ping-Test: %s", ping_icon, 
                         "Erfolgreich" if health["anythingllm_ping"] else "Fehlgeschlagen")
        except:
            log_and_print("WARNING", "%s Ping-Test fehlgeschlagen", get_status_icon("connection", "fehler"))
        
        # Workspace-Test
        if health["anythingllm_ping"]:
            workspaces_data = self.get_workspaces()
            workspaces = workspaces_data.get("workspaces", [])
            health["workspace_exists"] = any(ws.get("slug") == self.workspace_slug for ws in workspaces)
            health["api_key_valid"] = len(workspaces) > 0
            
            ws_icon = get_status_icon("connection", "online" if health["workspace_exists"] else "fehler")
            api_icon = get_status_icon("connection", "online" if health["api_key_valid"] else "fehler")
            
            log_and_print("INFO", "%s Workspace-Check: %s", ws_icon, 
                         "Gefunden" if health["workspace_exists"] else "Nicht gefunden")
            log_and_print("INFO", "%s API-Key-Check: %s", api_icon, 
                         "Gültig" if health["api_key_valid"] else "Ungültig")
        
        # Lokale Speicherung testen
        try:
            os.makedirs("/app/data", exist_ok=True)
            test_file = "/app/data/health_check.tmp"
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            health["local_storage"] = True
            log_and_print("SUCCESS", "%s Lokale Speicherung: Funktionsfähig", 
                         get_status_icon("process", "success"))
        except:
            log_and_print("ERROR", "%s Lokale Speicherung: Fehlgeschlagen", 
                         get_status_icon("process", "fehler"))
        
        return health


def send_to_anythingllm(machine: str, code: str, description: str) -> Optional[Dict[str, Any]]:
    """Kompatibilitätsfunktion für einfache Nutzung"""
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)


if __name__ == "__main__":
    # Test-Skript
    print("🧪 AnythingLLM Client Test")
    print("=" * 40)
    
    client = AnythingLLMClient()
    
    # Verbindungstest
    if client.test_connection():
        log_and_print("SUCCESS", "Verbindung erfolgreich")
        
        # Health Check
        health = client.health_check()
        print(f"Health Check: {health}")
        
        # Test-Nachricht senden
        result = client.send_machine_error("TestMaschine", "E999", "Client-Test")
        print(f"Test-Ergebnis: {result}")
        
    else:
        log_and_print("ERROR", "Verbindung fehlgeschlagen")
