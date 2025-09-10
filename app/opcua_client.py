"""
OPC UA Client Module für Multi-Server-Support
Unterstützt gleichzeitige Verbindungen zu mehreren OPC UA Servern
mit robuster Fehlerbehandlung und AnythingLLM-Integration
"""

import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

try:
    from asyncua import Client, ua
    from asyncua.common.events import Event
    from asyncua.common.subscription import SubHandler
    OPCUA_AVAILABLE = True
except ImportError:
    OPCUA_AVAILABLE = False
    logging.warning("asyncua library nicht verfügbar. Installieren mit: pip install asyncua")

logger = logging.getLogger("iot-bridge.opcua")

@dataclass
class OPCUAServerConfig:
    """Konfiguration für einen OPC UA Server"""
    name: str
    url: str
    enabled: bool = True
    username: Optional[str] = None
    password: Optional[str] = None
    security_mode: str = "None"
    variables: Dict[str, str] = field(default_factory=dict)
    event_nodes: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    connection_timeout: int = 10
    monitoring_interval: int = 1000

class OPCUAEventHandler(SubHandler):
    """Event-Handler für OPC UA Subscriptions"""
    
    def __init__(self, server_name: str, llm_client=None):
        super().__init__()
        self.server_name = server_name
        self.llm_client = llm_client
        self.logger = logging.getLogger(f"iot-bridge.opcua.{server_name}")
        
    def datachange_notification(self, node, val, data):
        """Behandelt Datenänderungsbenachrichtigungen"""
        try:
            node_id = str(node)
            timestamp = datetime.now()
            
            self.logger.debug("Datenänderung: %s = %s", node_id, val)
            
            # Kritische Werte prüfen und weiterleiten
            if self._is_critical_value(node_id, val):
                self._handle_critical_value(node_id, val, timestamp)
                
        except Exception as e:
            self.logger.exception("Fehler bei Datenänderungsbehandlung: %s", e)
    
    def event_notification(self, event):
        """Behandelt OPC UA Event-Benachrichtigungen"""
        try:
            # Event-Eigenschaften extrahieren
            source_name = self._get_event_property(event, 'SourceName', 'Unknown')
            message = self._get_event_property(event, 'Message', 'No message')
            severity = self._get_event_property(event, 'Severity', 500)
            event_type = self._get_event_property(event, 'EventType', 'Unknown')
            
            # LocalizedText-Objekte behandeln
            if hasattr(message, 'Text'):
                message = message.Text
            
            self.logger.info("OPC UA Event: %s - %s (Severity: %d)", 
                           source_name, message, severity)
            
            # Event an AnythingLLM weiterleiten
            if self.llm_client:
                self._forward_event_to_llm(source_name, message, severity, event_type)
                
        except Exception as e:
            self.logger.exception("Fehler bei Event-Behandlung: %s", e)
    
    def _get_event_property(self, event, property_name: str, default_value):
        """Sichere Extraktion von Event-Eigenschaften"""
        try:
            return getattr(event, property_name, default_value)
        except:
            return default_value
    
    def _is_critical_value(self, node_id: str, value: Any) -> bool:
        """Prüft ob ein Wert kritische Schwellenwerte überschreitet"""
        if not isinstance(value, (int, float)):
            return False
            
        node_lower = node_id.lower()
        
        # Temperatur-Grenzwerte
        if any(temp_keyword in node_lower for temp_keyword in ['temperature', 'temp', 'celsius']):
            return value > 85.0 or value < -15.0
        
        # Druck-Grenzwerte  
        elif any(pressure_keyword in node_lower for pressure_keyword in ['pressure', 'bar', 'psi']):
            return value < 0.5 or value > 20.0
            
        # Geschwindigkeits-Grenzwerte
        elif any(speed_keyword in node_lower for speed_keyword in ['speed', 'rpm', 'velocity']):
            return value > 6000 or value < 0
            
        # Fehler-/Defekt-Zähler
        elif any(error_keyword in node_lower for error_keyword in ['error', 'defect', 'fault']):
            return value > 5
            
        # Produktions-Effizienz
        elif any(eff_keyword in node_lower for eff_keyword in ['efficiency', 'oee']):
            return value < 70.0  # Unter 70% Effizienz
            
        return False
    
    def _handle_critical_value(self, node_id: str, value: Any, timestamp: datetime):
        """Behandelt kritische Werte"""
        if not self.llm_client:
            return
            
        # Error-Code basierend auf Variable bestimmen
        error_code = self._determine_error_code(node_id, value)
        machine_name = self._extract_machine_name(node_id)
        description = self._create_critical_value_description(node_id, value)
        
        self.llm_client.send_machine_error(machine_name, error_code, description)
        self.logger.warning("Kritischer Wert gemeldet: %s = %s", node_id, value)
    
    def _forward_event_to_llm(self, source_name: str, message: str, severity: int, event_type: str):
        """Leitet OPC UA Events an AnythingLLM weiter"""
        if not self.llm_client:
            return
            
        error_code = self._severity_to_error_code(severity)
        machine_name = f"{self.server_name}_{source_name}"
        description = f"OPC UA Event [{event_type}]: {message}"
        
        self.llm_client.send_machine_error(machine_name, error_code, description)
    
    def _determine_error_code(self, node_id: str, value: Any) -> str:
        """Bestimmt Error-Code basierend auf Variable und Server"""
        node_lower = node_id.lower()
        server_lower = self.server_name.lower()
        
        # Server-spezifische Error-Codes
        if "production" in server_lower:
            if "temperature" in node_lower:
                return "E001" if value > 85 else "E002"
            elif "pressure" in node_lower:
                return "E003" if value > 20 else "E004"
            elif "speed" in node_lower:
                return "E005"
            else:
                return "E099"
                
        elif "quality" in server_lower:
            if "defect" in node_lower:
                return "Q001"
            elif "efficiency" in node_lower:
                return "Q002"
            else:
                return "Q099"
                
        elif "local" in server_lower or "plc" in server_lower:
            if "motor" in node_lower:
                return "M001"
            elif "sensor" in node_lower:
                return "S001"
            else:
                return "PLC001"
                
        return "W999"  # Unbekannt
    
    def _extract_machine_name(self, node_id: str) -> str:
        """Extrahiert Maschinennamen aus Node-ID"""
        # Verschiedene Patterns für Maschinennamen
        patterns = [
            r"Machine(\d+)",
            r"Line(\d+)",
            r"Station(\d+)",
            r"Robot(\d+)",
            r"Press(\d+)"
        ]
        
        import re
        for pattern in patterns:
            match = re.search(pattern, node_id, re.IGNORECASE)
            if match:
                return f"{self.server_name}_{match.group(0)}"
        
        return f"{self.server_name}_Equipment"
    
    def _create_critical_value_description(self, node_id: str, value: Any) -> str:
        """Erstellt beschreibende Fehlermeldung für kritische Werte"""
        node_lower = node_id.lower()
        
        if "temperature" in node_lower:
            if value > 85:
                return f"Kritische Übertemperatur: {value}°C (Grenzwert: 85°C)"
            else:
                return f"Kritische Untertemperatur: {value}°C (Grenzwert: -15°C)"
                
        elif "pressure" in node_lower:
            if value > 20:
                return f"Kritischer Überdruck: {value} bar (Grenzwert: 20 bar)"
            else:
                return f"Kritischer Unterdruck: {value} bar (Grenzwert: 0.5 bar)"
                
        elif "speed" in node_lower:
            return f"Kritische Geschwindigkeit: {value} rpm (Grenzwert: 6000 rpm)"
            
        elif "error" in node_lower or "defect" in node_lower:
            return f"Kritische Fehleranzahl: {value} (Grenzwert: 5)"
            
        elif "efficiency" in node_lower:
            return f"Kritische Effizienz: {value}% (Grenzwert: 70%)"
            
        return f"Kritischer Wert erreicht: {node_id} = {value}"
    
    def _severity_to_error_code(self, severity: int) -> str:
        """Konvertiert OPC UA Severity zu Error-Code"""
        if severity >= 900:
            return "E_CRITICAL"
        elif severity >= 700:
            return "E_HIGH"
        elif severity >= 500:
            return "W_MEDIUM"
        elif severity >= 300:
            return "W_LOW"
        else:
            return "I_INFO"

class OPCUAServerConnection:
    """Verwaltet eine einzelne OPC UA Server-Verbindung"""
    
    def __init__(self, config: OPCUAServerConfig, llm_client=None):
        self.config = config
        self.llm_client = llm_client
        self.client = None
        self.subscription = None
        self.event_handler = None
        self.connected = False
        self.logger = logging.getLogger(f"iot-bridge.opcua.{config.name}")
        
    async def connect(self) -> bool:
        """Stellt Verbindung zum OPC UA Server her"""
        try:
            self.logger.info("Verbinde mit OPC UA Server: %s", self.config.url)
            
            # Client erstellen und konfigurieren
            self.client = Client(url=self.config.url)
            
            # Authentifizierung
            if self.config.username and self.config.password:
                self.client.set_user(self.config.username)
                self.client.set_password(self.config.password)
                self.logger.debug("Authentifizierung konfiguriert für: %s", self.config.username)
            
            # Verbindung mit Timeout
            await asyncio.wait_for(
                self.client.connect(),
                timeout=self.config.connection_timeout
            )
            
            self.connected = True
            self.config.retry_count = 0
            
            # Server-Informationen abrufen
            await self._log_server_info()
            
            # Subscriptions einrichten
            await self._setup_subscriptions()
            
            self.logger.info("Erfolgreich verbunden mit: %s", self.config.name)
            return True
            
        except asyncio.TimeoutError:
            self.logger.error("Verbindungs-Timeout für %s nach %ds", 
                            self.config.name, self.config.connection_timeout)
            return False
        except Exception as e:
            self.config.retry_count += 1
            self.logger.error("Verbindung fehlgeschlagen für %s (Versuch %d/%d): %s",
                            self.config.name, self.config.retry_count, 
                            self.config.max_retries, e)
            return False
    
    async def disconnect(self):
        """Trennt die Verbindung zum OPC UA Server"""
        try:
            if self.subscription:
                await self.subscription.delete()
                self.subscription = None
                
            if self.client and self.connected:
                await self.client.disconnect()
                
            self.connected = False
            self.logger.info("Verbindung getrennt: %s", self.config.name)
            
        except Exception as e:
            self.logger.exception("Fehler beim Trennen der Verbindung %s: %s", 
                                self.config.name, e)
    
    async def _log_server_info(self):
        """Loggt Server-Informationen für Debugging"""
        try:
            # Server-Informationen
            objects_node = self.client.get_objects_node()
            children = await objects_node.get_children()
            
            self.logger.debug("Server %s - Verfügbare Objekte: %d", 
                            self.config.name, len(children))
            
            # Namespace-Array
            namespaces = await self.client.get_namespace_array()
            self.logger.debug("Server %s - Namespaces: %s", 
                            self.config.name, namespaces[:5])  # Erste 5
            
        except Exception as e:
            self.logger.debug("Konnte Server-Info nicht abrufen für %s: %s", 
                            self.config.name, e)
    
    async def _setup_subscriptions(self):
        """Richtet Subscriptions für Events und Variablen ein"""
        if not self.connected:
            return
            
        try:
            # Event-Handler erstellen
            self.event_handler = OPCUAEventHandler(self.config.name, self.llm_client)
            
            # Subscription erstellen
            self.subscription = await self.client.create_subscription(
                period=self.config.monitoring_interval,
                handler=self.event_handler
            )
            
            # Event-Subscriptions
            await self._subscribe_to_events()
            
            # Variable-Monitoring
            await self._subscribe_to_variables()
            
            self.logger.info("Subscriptions eingerichtet für: %s", self.config.name)
            
        except Exception as e:
            self.logger.exception("Fehler bei Subscription-Setup für %s: %s", 
                                self.config.name, e)
    
    async def _subscribe_to_events(self):
        """Abonniert OPC UA Events"""
        try:
            # Standard Server-Events
            server_node = self.client.get_server_node()
            await self.subscription.subscribe_events(server_node)
            self.logger.debug("Server-Events abonniert: %s", self.config.name)
            
            # Zusätzliche Event-Nodes
            for event_node_id in self.config.event_nodes:
                try:
                    event_node = self.client.get_node(event_node_id)
                    await self.subscription.subscribe_events(event_node)
                    self.logger.debug("Event-Node abonniert: %s", event_node_id)
                except Exception as e:
                    self.logger.warning("Event-Node %s nicht abonnierbar: %s", 
                                      event_node_id, e)
                    
        except Exception as e:
            self.logger.warning("Event-Subscription fehlgeschlagen für %s: %s", 
                              self.config.name, e)
    
    async def _subscribe_to_variables(self):
        """Abonniert Variable-Änderungen"""
        if not self.config.variables:
            return
            
        monitored_count = 0
        for var_name, node_id in self.config.variables.items():
            try:
                node = self.client.get_node(node_id)
                await self.subscription.subscribe_data_change(node)
                monitored_count += 1
                self.logger.debug("Variable überwacht: %s (%s)", var_name, node_id)
            except Exception as e:
                self.logger.warning("Variable %s nicht überwachbar: %s", var_name, e)
        
        self.logger.info("Variablen-Monitoring: %d/%d erfolgreich für %s",
                        monitored_count, len(self.config.variables), self.config.name)
    
    async def read_variables(self) -> Dict[str, Any]:
        """Liest aktuelle Werte aller konfigurierten Variablen"""
        if not self.connected or not self.config.variables:
            return {}
            
        results = {}
        for var_name, node_id in self.config.variables.items():
            try:
                node = self.client.get_node(node_id)
                value = await node.read_value()
                results[var_name] = {
                    'value': value,
                    'timestamp': datetime.now().isoformat(),
                    'node_id': node_id,
                    'server': self.config.name
                }
            except Exception as e:
                self.logger.warning("Lesen fehlgeschlagen: %s.%s - %s", 
                                  self.config.name, var_name, e)
                results[var_name] = {
                    'value': None,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat(),
                    'server': self.config.name
                }
        
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt aktuellen Verbindungsstatus zurück"""
        return {
            'name': self.config.name,
            'url': self.config.url,
            'connected': self.connected,
            'retry_count': self.config.retry_count,
            'max_retries': self.config.max_retries,
            'variables_count': len(self.config.variables),
            'monitoring_interval': self.config.monitoring_interval
        }

class MultiOPCUAClient:
    """Manager für mehrere OPC UA Server-Verbindungen"""
    
    def __init__(self, llm_client=None):
        if not OPCUA_AVAILABLE:
            raise ImportError("asyncua library nicht verfügbar")
            
        self.llm_client = llm_client
        self.servers: Dict[str, OPCUAServerConnection] = {}
        self.logger = logging.getLogger("iot-bridge.opcua")
        
        # Standard-Konfigurationen laden
        self._load_server_configurations()
    
    def _load_server_configurations(self):
        """Lädt Server-Konfigurationen basierend auf den vorgegebenen IPs"""
        
        # Production Server 1 (172.30.2.11)
        production_config = OPCUAServerConfig(
            name="Production_Server",
            url="opc.tcp://172.30.2.11:4840",
            variables={
                "Line1_Temperature": "ns=2;s=Production.Line1.Temperature",
                "Line1_Pressure": "ns=2;s=Production.Line1.Pressure", 
                "Line1_Speed": "ns=2;s=Production.Line1.Speed",
                "Line1_ProductionCount": "ns=2;s=Production.Line1.ProductionCount",
                "Line1_Status": "ns=2;s=Production.Line1.Status",
                "Line2_Temperature": "ns=2;s=Production.Line2.Temperature",
                "Line2_OEE": "ns=2;s=Production.Line2.OEE"
            },
            event_nodes=[
                "ns=2;s=Production.Alarms",
                "ns=2;s=Production.Events"
            ]
        )
        
        # Quality Server (172.30.0.11)
        quality_config = OPCUAServerConfig(
            name="Quality_Server", 
            url="opc.tcp://172.30.0.11:4840",
            variables={
                "QC_Station1_DefectCount": "ns=2;s=Quality.Station1.DefectCount",
                "QC_Station1_TestResult": "ns=2;s=Quality.Station1.TestResult",
                "QC_Station1_Efficiency": "ns=2;s=Quality.Station1.Efficiency",
                "QC_Station2_DefectCount": "ns=2;s=Quality.Station2.DefectCount",
                "QC_Overall_PassRate": "ns=2;s=Quality.Overall.PassRate"
            },
            event_nodes=[
                "ns=2;s=Quality.Alarms",
                "ns=2;s=Quality.QualityEvents"
            ]
        )
        
        # Local PLC (192.168.2.1) - WAGO PLC
        local_plc_config = OPCUAServerConfig(
            name="Local_PLC",
            url="opc.tcp://192.168.2.1:4840", 
            variables={
                "PLC_Status": "ns=4;s=|var|WAGO 750-8202.Application.PLC_PRG.Status",
                "Motor1_Speed": "ns=4;s=|var|WAGO 750-8202.Application.PLC_PRG.Motor1.Speed",
                "Motor1_Temperature": "ns=4;s=|var|WAGO 750-8202.Application.PLC_PRG.Motor1.Temperature",
                "Sensor_Pressure": "ns=4;s=|var|WAGO 750-8202.Application.PLC_PRG.Sensors.Pressure",
                "Safety_Status": "ns=4;s=|var|WAGO 750-8202.Application.PLC_PRG.Safety.Status",
                "Emergency_Stop": "ns=4;s=|var|WAGO 750-8202.Application.PLC_PRG.Safety.EmergencyStop"
            },
            event_nodes=[
                "ns=4;s=|var|WAGO 750-8202.Application.PLC_PRG.Alarms"
            ]
        )
        
        all_configs = [production_config, quality_config, local_plc_config]
        
        # Konfigurationen mit Umgebungsvariablen anpassen
        for config in all_configs:
            env_prefix = f"OPCUA_{config.name.upper()}"
            
            # Server aktiviert?
            config.enabled = os.getenv(f"{env_prefix}_ENABLED", "true").lower() == "true"
            
            if config.enabled:
                # Authentifizierung
                config.username = os.getenv(f"{env_prefix}_USERNAME", config.username)
                config.password = os.getenv(f"{env_prefix}_PASSWORD", config.password)
                
                # Verbindungsparameter
                config.connection_timeout = int(os.getenv(f"{env_prefix}_TIMEOUT", "10"))
                config.monitoring_interval = int(os.getenv(f"{env_prefix}_INTERVAL", "1000"))
                config.max_retries = int(os.getenv(f"{env_prefix}_MAX_RETRIES", "3"))
                
                # Verbindung erstellen
                connection = OPCUAServerConnection(config, self.llm_client)
                self.servers[config.name] = connection
                
                self.logger.info("OPC UA Server konfiguriert: %s (%s)", 
                               config.name, config.url)
            else:
                self.logger.info("OPC UA Server deaktiviert: %s", config.name)
    
    async def connect_all_servers(self) -> Dict[str, bool]:
        """Verbindet mit allen aktivierten Servern"""
        self.logger.info("Verbinde mit %d OPC UA Servern...", len(self.servers))
        
        connection_results = {}
        connection_tasks = []
        
        # Parallele Verbindungsversuche
        for server_name, server_connection in self.servers.items():
            task = asyncio.create_task(
                self._connect_with_retry(server_name, server_connection)
            )
            connection_tasks.append((server_name, task))
        
        # Auf alle Verbindungsversuche warten
        for server_name, task in connection_tasks:
            try:
                success = await task
                connection_results[server_name] = success
            except Exception as e:
                self.logger.exception("Kritischer Fehler bei %s: %s", server_name, e)
                connection_results[server_name] = False
        
        # Ergebnisse zusammenfassen
        connected_count = sum(1 for success in connection_results.values() if success)
        self.logger.info("OPC UA Verbindungen: %d/%d erfolgreich", 
                        connected_count, len(connection_results))
        
        return connection_results
    
    async def _connect_with_retry(self, server_name: str, 
                                server_connection: OPCUAServerConnection) -> bool:
        """Verbindungsversuch mit Retry-Logik"""
        max_retries = server_connection.config.max_retries
        
        for attempt in range(max_retries + 1):
            try:
                if await server_connection.connect():
                    return True
                    
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)  # Exponential backoff, max 30s
                    self.logger.info("Retry für %s in %ds (Versuch %d/%d)", 
                                   server_name, wait_time, attempt + 1, max_retries)
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                self.logger.error("Verbindungsversuch %d/%d für %s fehlgeschlagen: %s",
                                attempt + 1, max_retries + 1, server_name, e)
                
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
        
        self.logger.error("Alle Verbindungsversuche für %s fehlgeschlagen", server_name)
        return False
    
    async def disconnect_all_servers(self):
        """Trennt alle Server-Verbindungen"""
        self.logger.info("Trenne alle OPC UA Server-Verbindungen...")
        
        disconnect_tasks = []
        for server_name, server_connection in self.servers.items():
            task = asyncio.create_task(server_connection.disconnect())
            disconnect_tasks.append(task)
        
        # Auf alle Disconnect-Vorgänge warten
        await asyncio.gather(*disconnect_tasks, return_exceptions=True)
        
        self.logger.info("Alle OPC UA Server-Verbindungen getrennt")
    
    async def read_all_variables(self) -> Dict[str, Dict[str, Any]]:
        """Liest alle konfigurierten Variablen von allen verbundenen Servern"""
        all_results = {}
        
        read_tasks = []
        for server_name, server_connection in self.servers.items():
            if server_connection.connected:
                task = asyncio.create_task(server_connection.read_variables())
                read_tasks.append((server_name, task))
        
        # Alle Lesevorgänge parallel ausführen
        for server_name, task in read_tasks:
            try:
                server_results = await task
                all_results[server_name] = server_results
            except Exception as e:
                self.logger.exception("Lesefehler für Server %s: %s", server_name, e)
                all_results[server_name] = {"error": str(e)}
        
        return all_results
    
    async def get_server_status(self) -> Dict[str, Any]:
        """Gibt Status aller Server zurück"""
        connected_servers = sum(1 for conn in self.servers.values() if conn.connected)
        
        status = {
            'total_servers': len(self.servers),
            'connected_servers': connected_servers,
            'connection_rate': f"{connected_servers}/{len(self.servers)}",
            'servers': {}
        }
        
        for server_name, server_connection in self.servers.items():
            status['servers'][server_name] = server_connection.get_status()
        
        return status
    
    async def reconnect_failed_servers(self) -> Dict[str, bool]:
        """Versucht Reconnect für getrennte Server"""
        self.logger.info("Starte Reconnect für getrennte Server...")
        
        reconnect_results = {}
        
        for server_name, server_connection in self.servers.items():
            if not server_connection.connected:
                if server_connection.config.retry_count < server_connection.config.max_retries:
                    self.logger.info("Reconnect-Versuch für: %s", server_name)
                    success = await server_connection.connect()
                    reconnect_results[server_name] = success
                else:
                    self.logger.warning("Max Retries erreicht für: %s", server_name)
                    reconnect_results[server_name] = False
        
        return reconnect_results
    
    def get_connected_servers(self) -> List[str]:
        """Gibt Liste der verbundenen Server zurück"""
        return [name for name, conn in self.servers.items() if conn.connected]
    
    def get_disconnected_servers(self) -> List[str]:
        """Gibt Liste der getrennten Server zurück"""
        return [name for name, conn in self.servers.items() if not conn.connected]

# Test-Funktionen
async def test_opcua_connection(server_url: str, timeout: int = 10) -> bool:
    """Testet OPC UA Verbindung zu einem Server"""
    try:
        client = Client(url=server_url)
        await asyncio.wait_for(client.connect(), timeout=timeout)
        await client.disconnect()
        return True
    except Exception as e:
        logger.error("Verbindungstest fehlgeschlagen für %s: %s", server_url, e)
        return False

async def discover_opcua_server_structure(server_url: str, max_depth: int = 2) -> Dict[str, Any]:
    """Durchsucht OPC UA Server-Struktur für Debugging"""
    try:
        client = Client(url=server_url)
        await client.connect()
        
        root = client.get_root_node()
        objects = await root.get_child("0:Objects")
        
        structure = await _browse_node_recursive(objects, max_depth)
        
        await client.disconnect()
        return structure
        
    except Exception as e:
        logger.exception("Server-Discovery fehlgeschlagen für %s: %s", server_url, e)
        return {}

async def _browse_node_recursive(node, max_depth: int, current_depth: int = 0) -> Dict[str, Any]:
    """Rekursive Funktion zum Durchsuchen der Node-Struktur"""
    if current_depth >= max_depth:
        return {}
    
    structure = {}
    try:
        children = await node.get_children()
        for child in children[:20]:  # Limitierung für Performance
            try:
                name = await child.read_display_name()
                node_id = str(child.nodeid)
                structure[str(name)] = {
                    'node_id': node_id,
                    'children': await _browse_node_recursive(child, max_depth, current_depth + 1)
                }
            except:
                pass  # Node nicht lesbar
    except:
        pass
    
    return structure
