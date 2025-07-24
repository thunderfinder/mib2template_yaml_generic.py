#!/usr/bin/env python3
"""
mib2template_yaml_generic.py - Genera plantillas de Zabbix (YAML) desde archivos MIB

Genera una plantilla base para Zabbix 6.0+ a partir de cualquier archivo MIB estándar.
Extrae items escalares y columnas de tablas, junto con información de tipos, unidades y enums.

Copyright (C) 2024 - Basado en trabajos de Ryan Armstrong y otros.
Licencia: GNU General Public License v2.0
"""
import sys
import os
import re
import argparse
import subprocess
import uuid
import yaml # Requiere: pip install pyyaml

# Opcional: Para parseo avanzado de MIBs y extracción de enums
# Requiere: pip install pysmi
# Si no está disponible, se usará una extracción básica con snmptranslate
try:
    from pysmi.parser.smi import parserFactory
    from pysmi.codegen.pysnmp import PySnmpCodeGen
    from pysmi.reader import FileReader
    from pysmi.compiler import MibCompiler
    from pysmi import debug
    PYSNMP_AVAILABLE = True
except ImportError:
    PYSNMP_AVAILABLE = False
    print("[INFO] pysmi no encontrado. La extracción de enums será limitada. Para mejor soporte, instale con 'pip install pysmi'.")

# --- Funciones de utilidad para generar UUIDs y nombres consistentes ---

def generate_uuid_from_string(seed_string):
    """Genera un UUID v5 determinista basado en una semilla."""
    namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8') # UUID para 'zabbix_template'
    return str(uuid.uuid5(namespace, seed_string))

def sanitize_name(name):
    """Limpia un nombre para que sea adecuado para usar como nombre de item/key."""
    # Permite más caracteres válidos para keys de Zabbix, incluyendo macros {}
    return re.sub(r'[^a-zA-Z0-9_\-.{}#\[\]]', '_', name)

# --- Clase principal del generador ---

class MIBTemplateYAMLGenerator:
    def __init__(self):
        self.args = None
        self.template_data = {}
        self.processed_symbols = []
        self.value_maps = {} # Para almacenar enums encontrados
        self.pysmi_enums = {} # Para almacenar enums extraídos por pysmi

    def parse_arguments(self):
        """Parsea los argumentos de línea de comandos"""
        parser = argparse.ArgumentParser(
            description='Genera plantilla de Zabbix (YAML) desde archivo MIB',
            formatter_class=argparse.RawTextHelpFormatter,
            epilog="""Ejemplos:
  %(prog)s -f /usr/share/snmp/mibs/SNMPv2-MIB.txt -m SNMPv2-MIB
  %(prog)s -f ./CUSTOM-MIB.mib -m CUSTOM-MIB -N "Mi Template Custom" -o custom_template.yaml"""
        )
        parser.add_argument('-f', '--mib-file', required=True,
                          help='Ruta al archivo MIB (e.g., /usr/share/snmp/mibs/SNMPv2-MIB.txt)')
        parser.add_argument('-m', '--module', required=True,
                          help='Nombre del módulo MIB (e.g., SNMPv2-MIB)')
        parser.add_argument('-o', '--output', default='template.yaml',
                          help='Nombre del archivo de salida YAML (default: template.yaml)')
        
        parser.add_argument('-N', '--template-name',
                          help='Nombre de la plantilla (default: <module> SNMP)')
        parser.add_argument('-G', '--group', default='Templates',
                          help='Grupo de la plantilla (default: Templates)')
        
        # Item configuration
        parser.add_argument('--check-delay', default='1h',
                          help='Intervalo de chequeo para items (default: 1h)')
        parser.add_argument('--disc-delay', default='1h',
                          help='Intervalo de descubrimiento (default: 1h)')
        parser.add_argument('--history', default='30d',
                          help='Retención del historial (default: 30d)')
        parser.add_argument('--trends', default='0', # Por defecto desactivado para CHAR
                          help='Retención de tendencias (default: 0)')
        
        self.args = parser.parse_args()

    def load_mib(self):
        """Carga el MIB y verifica su disponibilidad"""
        try:
            # Verificar que el MIB puede ser cargado
            result = subprocess.run(
                ['snmptranslate', '-T', 'o', '-m', self.args.mib_file, self.args.module], 
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                print(f"[ERROR] Error cargando MIB: {result.stderr.strip()}")
                return False
            print(f"[INFO] MIB '{self.args.module}' cargado correctamente desde '{self.args.mib_file}'")
            return True
        except FileNotFoundError:
            print("[ERROR] snmptranslate no encontrado. Asegúrate de tener net-snmp instalado (snmptranslate, snmpget, etc.).")
            return False
        except subprocess.TimeoutExpired:
            print("[ERROR] Tiempo de espera agotado al intentar cargar el MIB.")
            return False
        except Exception as e:
            print(f"[ERROR] Excepción inesperada al cargar el MIB: {e}")
            return False

    def extract_enums_with_pysmi(self):
        """(Opcional) Extrae enums usando pysmi si está disponible."""
        if not PYSNMP_AVAILABLE:
            return
        try:
            print("[INFO] Intentando extraer enums con pysmi...")
            # Configurar el compilador de pysmi
            # Esto es una simplificación. Un uso más avanzado podría requerir configurar
            # directorios de búsqueda de dependencias.
            
            # Crear directorio temporal para la salida
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                # Compilador
                compiler = MibCompiler(
                    parserFactory(), # Parser por defecto
                    PySnmpCodeGen(), # Generador de código Python
                    FileReader(self.args.mib_file) # Lector del archivo MIB
                )
                # Compilar (en este caso, solo para parsear)
                results = compiler.compile(
                    self.args.module,
                    destination=tmpdir,
                    rebuild=True,
                    dryRun=False
                )
                
                # La información del MIB parseado se encuentra en el directorio tmpdir
                # Como pysmi genera código Python, podemos importarlo (NO RECOMENDADO para producción)
                # o leer el archivo .py generado.
                
                # Una forma más segura es usar pysmi para obtener el MIB en formato interno
                # pero esto requiere un código más complejo.
                # Por ahora, usamos una aproximación más simple:
                # Leer el archivo .py generado y extraer información.
                
                py_file_path = os.path.join(tmpdir, self.args.module.lower() + ".py")
                if os.path.exists(py_file_path):
                    with open(py_file_path, 'r') as pyf:
                        py_content = pyf.read()
                        
                    # Buscar patrones de enums en el código Python generado
                    # Ejemplo: ('up', 1), ('down', 2)
                    enum_pattern = re.compile(r"MibIdentifier\([^)]*?\)\.subtype\(subtypeSpec=ConstraintsUnion\(ValueRangeConstraint\([^)]*?\), ValueRangeConstraint\([^)]*?\)\)\)")
                    # Esta es una simplificación extrema. Un análisis real requiere
                    # recorrer el árbol de sintaxis del MIB.
                    
                    # Alternativa: Usar el propio pysmi para obtener el árbol de sintaxis
                    # Esto es complejo y no se implementa aquí por brevedad.
                    # Se deja como mejora futura.
                    
                    # Como ejemplo, simplemente imprimimos que se ha intentado.
                    print(f"[INFO] pysmi procesó el MIB. (Extracción avanzada de enums no implementada en esta versión simplificada)")
                else:
                     print(f"[WARNING] pysmi no generó el archivo .py esperado para {self.args.module}")
        except Exception as e:
            print(f"[WARNING] Error al usar pysmi para extraer enums: {e}. Continuando con snmptranslate.")

    def get_mib_symbols(self):
        """Obtiene todos los símbolos del MIB"""
        try:
            result = subprocess.run([
                'snmptranslate', '-T', 'l', '-m', self.args.mib_file, self.args.module
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"[ERROR] Error obteniendo símbolos del MIB: {result.stderr.strip()}")
                return []
                
            symbols = result.stdout.strip().split('\n')
            # Filtrar símbolos vacíos y comentarios
            symbols = [s.strip() for s in symbols if s.strip() and not s.startswith('#')]
            print(f"[INFO] Encontrados {len(symbols)} símbolos en el MIB.")
            return symbols
        except subprocess.TimeoutExpired:
            print("[ERROR] Tiempo de espera agotado al obtener símbolos del MIB.")
            return []
        except Exception as e:
            print(f"[ERROR] Excepción al obtener símbolos: {e}")
            return []

    def extract_enums_with_snmptranslate(self, description_output):
        """Intenta extraer definiciones de ENUM o RANGOS desde la salida de snmptranslate -Td."""
        # Esta es una versión mejorada de la extracción básica.
        # Busca patrones como: SYNTAX INTEGER { up(1), down(2) }
        # También puede encontrar patrones de DisplayString, IpAddress, etc.
        enum_match = re.search(r'SYNTAX\s+INTEGER\s*\{([^}]+)\}', description_output)
        if enum_match:
            enum_str = enum_match.group(1)
            mappings = []
            # Separar por comas, teniendo cuidado con paréntesis anidados
            # Esta lógica es básica y puede fallar con casos complejos
            parts = [p.strip() for p in enum_str.split(',')]
            for part in parts:
                # Ejemplo: up(1)
                match = re.match(r'([^(]+)\(([^)]+)\)', part)
                if match:
                    name, value = match.groups()
                    mappings.append({'value': value.strip(), 'newvalue': name.strip()})
            if mappings:
                return mappings
        return None

    def process_symbol(self, symbol):
        """Procesa un símbolo individual del MIB"""
        # Solo procesar símbolos con "::"
        if '::' not in symbol:
            return None

        try:
            # 1. Obtener OID numérico (-On)
            oid_result = subprocess.run(
                ['snmptranslate', '-On', '-m', self.args.mib_file, symbol], 
                capture_output=True, text=True, timeout=10
            )
            if oid_result.returncode != 0:
                return None
            oid = oid_result.stdout.strip()

            # 2. Obtener nombre completo (-Tz)
            full_name_result = subprocess.run(
                ['snmptranslate', '-Tz', '-m', self.args.mib_file, symbol], 
                capture_output=True, text=True, timeout=10
            )
            full_name = full_name_result.stdout.strip() if full_name_result.returncode == 0 else symbol
            
            # 3. Obtener descripción detallada (-Td)
            desc_result = subprocess.run(
                ['snmptranslate', '-Td', '-m', self.args.mib_file, symbol], 
                capture_output=True, text=True, timeout=10
            )
            detailed_desc = ""
            description = ""
            syntax = ""
            if desc_result.returncode == 0:
                detailed_desc = desc_result.stdout
                # Descripción legible
                desc_match = re.search(r'DESCRIPTION\s+"([^"]*)"', detailed_desc, re.DOTALL)
                if desc_match:
                    description = desc_match.group(1).replace('\n', ' ').replace('<', '<').replace('>', '>')
                    description = re.sub(r'\s+', ' ', description).strip()
                # Sintaxis
                syntax_match = re.search(r'SYNTAX\s+([^{]*?)(?:\s*\{|$)', detailed_desc)
                if syntax_match:
                    syntax = syntax_match.group(1).strip()
            
            # 4. Determinar tipo de dato Zabbix
            zabbix_type_info = self.get_zabbix_type_and_units(syntax, detailed_desc)
            
            # 5. Verificar si es tabla o escalar
            is_table = self.is_table_symbol(symbol, oid, syntax, detailed_desc)
            
            # 6. Intentar extraer enums
            enum_mappings = self.extract_enums_with_snmptranslate(detailed_desc)
            
            symbol_info = {
                'symbol': symbol,
                'oid': oid,
                'full_name': full_name,
                'description': description,
                'syntax': syntax,
                'zabbix_type': zabbix_type_info['type'],
                'units': zabbix_type_info['units'],
                'is_table': is_table,
                'enum_mappings': enum_mappings
            }
            
            # Si tiene enums, crear un valuemap
            if enum_mappings:
                # Crear un nombre de valuemap único basado en el OID o nombre del símbolo
                vm_name = f"SNMP {full_name.split('::')[-1]} (from MIB)"
                vm_uuid_seed = f"valuemap_{oid}_{full_name.split('::')[-1]}"
                valuemap = {
                    'uuid': generate_uuid_from_string(vm_uuid_seed),
                    'name': vm_name,
                    'mappings': enum_mappings
                }
                self.value_maps[vm_name] = valuemap
                print(f"[INFO] ValueMap encontrado para {symbol}")
            
            # print(f"[DEBUG] Procesado: {symbol} -> OID: {oid}, Tipo: {zabbix_type_info}, Tabla: {is_table}")
            return symbol_info
            
        except subprocess.TimeoutExpired:
            print(f"[WARNING] Tiempo agotado procesando símbolo: {symbol}")
            return None
        except Exception as e:
            # print(f"[DEBUG] Error procesando símbolo {symbol}: {e}") # Para depuración
            # No mostrar todos los errores para no saturar la salida
            return None # Silenciosamente ignorar símbolos que fallan

    def get_zabbix_type_and_units(self, syntax, detailed_desc=""):
        """Mapea tipos SNMP a tipos Zabbix y extrae unidades si es posible."""
        # Mapa de tipos básico
        type_mapping = {
            'INTEGER': {'type': 'FLOAT', 'units': ''},
            'Integer32': {'type': 'FLOAT', 'units': ''},
            'Unsigned32': {'type': 'FLOAT', 'units': ''},
            'Counter32': {'type': 'FLOAT', 'units': ''}, # O 'COUNTER'
            'Counter64': {'type': 'FLOAT', 'units': ''}, # O 'COUNTER'
            'Gauge32': {'type': 'FLOAT', 'units': ''},
            'TimeTicks': {'type': 'FLOAT', 'units': 's'},
            'OCTET STRING': {'type': 'CHAR', 'units': ''},
            'OBJECT IDENTIFIER': {'type': 'CHAR', 'units': ''},
            'IpAddress': {'type': 'TEXT', 'units': ''},
            'BITS': {'type': 'TEXT', 'units': ''},
            'Opaque': {'type': 'TEXT', 'units': ''},
            'DisplayString': {'type': 'CHAR', 'units': ''},
            'MacAddress': {'type': 'CHAR', 'units': ''},
            'PhysAddress': {'type': 'CHAR', 'units': ''}, # RFC 2579
        }
        
        # Buscar coincidencia exacta primero
        for snmp_type, zabbix_info in type_mapping.items():
            if snmp_type == syntax:
                return zabbix_info
                
        # Buscar coincidencia parcial
        for snmp_type, zabbix_info in type_mapping.items():
            if snmp_type in syntax:
                # Intentar extraer unidades si están en la sintaxis o descripción
                # Buscar patrones como: "Gauge32 (1/100 seconds)", "DisplayString (SIZE (0..255))"
                units_match = re.search(r'\(([^)]*(?:seconds|bytes|bits|percent)[^)]*)\)', syntax + " " + detailed_desc, re.IGNORECASE)
                if units_match:
                    unit_text = units_match.group(1)
                    unit_map = {
                        'seconds': 's', 'second': 's',
                        'bytes': 'B',
                        'bits': 'b',
                        'percent': '%'
                    }
                    for k, v in unit_map.items():
                        if k in unit_text.lower():
                            zabbix_info['units'] = v
                            break
                return zabbix_info
                
        # Tipos por defecto basados en palabras clave
        if 'INTEGER' in syntax or 'Counter' in syntax or 'Gauge' in syntax or 'Enum' in syntax:
            return {'type': 'FLOAT', 'units': ''}
        elif 'STRING' in syntax or 'DisplayString' in syntax:
            return {'type': 'CHAR', 'units': ''}
        else:
            return {'type': 'TEXT', 'units': ''}

    def is_table_symbol(self, symbol, oid, syntax, detailed_desc):
        """Determina si un símbolo es una tabla o una columna de tabla."""
        # Heurísticas comunes
        # 1. Si el OID termina en .1.x (columna de tabla)
        oid_parts = oid.split('.')
        if len(oid_parts) > 2 and oid_parts[-2] == '1':
             return True
        # 2. Si el nombre contiene "Table", "Entry"
        if 'Table' in symbol or 'Entry' in symbol:
            # La tabla en sí no es un item, sus columnas sí.
            # Pero si es una tabla, sus columnas también lo serán.
            # Esta lógica puede mejorarse.
            return True # Asumimos que si el símbolo está en una tabla, es una columna.
        # 3. Si la sintaxis menciona TABLE (menos común)
        if 'TABLE' in syntax.upper():
            return True
        # 4. Buscar en la descripción patrones de tabla
        if 'A list of' in detailed_desc or 'table contains' in detailed_desc.lower():
             return True
        return False

    def process_mib_symbols(self):
        """Procesa todos los símbolos del MIB"""
        print(f"[INFO] Procesando MIB: {self.args.module}")
        
        # Intentar extraer enums con pysmi si está disponible
        self.extract_enums_with_pysmi()
        
        symbols = self.get_mib_symbols()
        if not symbols:
            print("[ERROR] No se encontraron símbolos para procesar.")
            return

        for symbol in symbols:
            symbol_info = self.process_symbol(symbol)
            if symbol_info:
                self.processed_symbols.append(symbol_info)
                
        print(f"[INFO] Procesamiento completado. {len(self.processed_symbols)} símbolos válidos.")

    def build_template_structure(self):
        """Construye la estructura de datos para el template YAML."""
        template_name = self.args.template_name or f"{self.args.module} SNMP"
        template_uuid_seed = f"template_{template_name}"
        
        self.template_data = {
            'zabbix_export': {
                'version': '6.0',
                'templates': [
                    {
                        'uuid': generate_uuid_from_string(template_uuid_seed),
                        'template': template_name,
                        'name': template_name,
                        'description': f'Template generated from MIB {self.args.module} using mib2template_yaml_generic.py',
                        'groups': [{'name': self.args.group}],
                        'items': [],
                        'discovery_rules': [],
                        # Secciones adicionales que pueden llenarse manualmente
                        'graphs': [],
                        'triggers': [],
                        'dashboards': []
                        # 'screens': [], # Obsoleto en 6.0
                        # 'httptests': [],
                        # 'tags': [], # Las tags se pueden añadir a items individuales
                        # 'macros': []
                    }
                ]
            }
        }
        
        # Añadir value maps si se encontraron
        if self.value_maps:
             self.template_data['zabbix_export']['valuemaps'] = list(self.value_maps.values())
        
        # Organizar símbolos en items y reglas de descubrimiento
        scalars = [s for s in self.processed_symbols if not s['is_table']]
        table_columns = [s for s in self.processed_symbols if s['is_table']]
        
        print(f"[INFO] Items escalares encontrados: {len(scalars)}")
        print(f"[INFO] Columnas de tablas encontradas: {len(table_columns)}")
        
        # --- Generar Items Escalares ---
        for scalar in scalars:
            item_data = self.create_item_data(scalar)
            self.template_data['zabbix_export']['templates'][0]['items'].append(item_data)
            
        # --- Generar Reglas de Descubrimiento ---
        # Agrupar columnas por tabla. Usamos el OID padre.
        tables_dict = {}
        for col in table_columns:
            oid_parts = col['oid'].split('.')
            if len(oid_parts) > 2:
                # El OID de la tabla sería el padre del .1.x
                # Ej., para .1.3.6.1.2.1.2.2.1.1, la tabla es .1.3.6.1.2.1.2.2
                table_oid_parts = oid_parts[:-2] 
                table_oid = '.'.join(table_oid_parts)
                
                # Intentar obtener el nombre de la tabla del MIB
                # Buscar el símbolo que corresponde a table_oid
                table_symbol = None
                # Simplificación: usar el último segmento del OID como identificador
                table_display_name = f"Table_{'_'.join(table_oid_parts[-2:])}"
                
                if table_oid not in tables_dict:
                    tables_dict[table_oid] = {
                        'name': table_display_name,
                        'oid': table_oid,
                        'columns': []
                    }
                tables_dict[table_oid]['columns'].append(col)
        
        for table_oid, table_info in tables_dict.items():
            disc_rule_data = self.create_discovery_rule_data(table_info)
            if disc_rule_data: # Solo agregar si hay prototipos
                 self.template_data['zabbix_export']['templates'][0]['discovery_rules'].append(disc_rule_data)

    def create_item_data(self, symbol_info):
        """Crea la estructura de datos para un item."""
        name = symbol_info['full_name'].split('::')[1] if '::' in symbol_info['full_name'] else symbol_info['full_name']
        # Sanitizar el key/name
        key = sanitize_name(symbol_info['full_name'].replace('::', '.'))
        
        item_uuid_seed = f"item_{symbol_info['oid']}_{name}"
        
        item = {
            'uuid': generate_uuid_from_string(item_uuid_seed),
            'name': name,
            'type': 'SNMP_AGENT',
            'snmp_oid': symbol_info['oid'],
            'key': key,
            'delay': self.args.check_delay,
            'history': self.args.history,
            'description': symbol_info['description'] or "No description available from MIB"
        }
        
        if symbol_info['zabbix_type']:
            item['value_type'] = symbol_info['zabbix_type']
            
        # Solo agregar 'trends' si el tipo lo soporta (no para CHAR/TEXT/LOG)
        if symbol_info['zabbix_type'] in ['FLOAT', 'UNSIGNED']:
            item['trends'] = self.args.trends
            
        if symbol_info['units']:
            item['units'] = symbol_info['units']
            
        # Agregar valuemap si existe
        if symbol_info['enum_mappings']:
            vm_name = f"SNMP {name} (from MIB)"
            item['valuemap'] = {'name': vm_name}
            
        # Por defecto, los items se crean sin status, lo que implica DISABLED en Zabbix
        # item['status'] = 'DISABLED' 
        
        return item

    def create_discovery_rule_data(self, table_info):
        """Crea la estructura de datos para una regla de descubrimiento."""
        table_name = table_info['name']
        table_oid = table_info['oid']
        columns = table_info['columns']
        
        if not columns:
            return None
            
        # Nombre de la regla de descubrimiento
        rule_name = table_name
        # Key de la regla de descubrimiento - usar un nombre genérico o basado en la tabla
        rule_key = sanitize_name(f"discovery.{table_name.replace(' ', '_')}")
        
        rule_uuid_seed = f"discovery_{table_oid}_{table_name}"
        
        # Crear item prototypes
        item_prototypes = []
        snmp_oid_macros = [] # Para la macro de descubrimiento
        
        for col in columns:
            col_name_raw = col['full_name'].split('::')[1].split('.')[0] if '::' in col['full_name'] else col['full_name'].split('.')[0]
            col_name_sanitized = sanitize_name(col_name_raw)
            
            # Key para el prototype, usando macro de índice
            proto_key = sanitize_name(f"{col['full_name'].replace('::', '.')}[{{#SNMPINDEX}}]")
            
            proto_uuid_seed = f"prototype_{col['oid']}_{col_name_raw}"
            
            proto = {
                'uuid': generate_uuid_from_string(proto_uuid_seed),
                'name': f"{col_name_raw}.{{#SNMPINDEX}}", # Nombre legible
                'type': 'SNMP_AGENT',
                'snmp_oid': f"{col['oid']}.{{#SNMPINDEX}}",
                'key': proto_key,
                'delay': self.args.check_delay,
                'history': self.args.history,
                'description': col['description'] or f"Column {col_name_raw} from table {table_name}"
            }
            
            if col['zabbix_type']:
                proto['value_type'] = col['zabbix_type']
                
            if col['zabbix_type'] in ['FLOAT', 'UNSIGNED']:
                proto['trends'] = self.args.trends
                
            if col['units']:
                proto['units'] = col['units']
                
            # Agregar valuemap si existe
            if col['enum_mappings']:
                vm_name = f"SNMP {col_name_raw} (from MIB)"
                proto['valuemap'] = {'name': vm_name}
            
            item_prototypes.append(proto)
            
            # Agregar a la macro de descubrimiento
            # Formato simplificado: {#MACRO},OID
            # Ej., {#IFNAME},.1.3.6.1.2.1.2.2.1.2
            macro_name = sanitize_name(col_name_raw).upper()
            snmp_oid_macros.append(f"{{#{macro_name}}},{col['oid']}")
        
        if not item_prototypes:
            return None
            
        # Construir la cadena snmp_oid para la regla de descubrimiento
        # Formato: discovery[{#MACRO1},OID1,{#MACRO2},OID2,...]
        snmp_oid_str = "discovery[" + ",".join(snmp_oid_macros) + "]"
        # Limitar longitud si es necesario (Zabbix tiene límites, aunque son grandes)
        if len(snmp_oid_str) > 2000: # Límite conservador
             print(f"[WARNING] Cadena de descubrimiento muy larga para {rule_name}.")
             # Aquí podrías implementar lógica para dividir en múltiples reglas.
             # Por ahora, se trunca con un mensaje.
             snmp_oid_str = snmp_oid_str[:1995] + "...]"
             
        discovery_rule = {
            'uuid': generate_uuid_from_string(rule_uuid_seed),
            'name': rule_name,
            'delay': self.args.disc_delay,
            'key': rule_key,
            'type': 'SNMP_AGENT',
            'snmp_oid': snmp_oid_str,
            # 'status': 'DISABLED',
            'item_prototypes': item_prototypes
            # Se pueden añadir trigger_prototypes, graph_prototypes, etc. manualmente
        }
        
        return discovery_rule

    def write_yaml(self):
        """Escribe la plantilla en un archivo YAML."""
        try:
            with open(self.args.output, 'w', encoding='utf-8') as f:
                # Usar safe_dump con opciones para formato legible
                yaml.safe_dump(
                    self.template_data,
                    f,
                    default_flow_style=False,
                    indent=2,
                    allow_unicode=True,
                    sort_keys=False, # Mantiene el orden definido
                    width=10000, # Evita que rompa líneas largas (como snmp_oid discovery)
                    # ensure_ascii=False # Ya manejado por allow_unicode
                )
            print(f"[INFO] Template YAML generado con éxito: {self.args.output}")
            if self.value_maps:
                print(f"[INFO] Se generaron {len(self.value_maps)} Value Maps.")
        except Exception as e:
            print(f"[ERROR] Fallo al escribir el archivo YAML: {e}")

    def run(self):
        """Ejecuta el generador de templates"""
        self.parse_arguments()
        
        if not self.load_mib():
            sys.exit(1)
            
        self.process_mib_symbols()
        
        if not self.processed_symbols:
            print("[ERROR] No se procesaron símbolos válidos del MIB. Saliendo.")
            sys.exit(1)
            
        self.build_template_structure()
        self.write_yaml()

def main():
    """Función principal"""
    generator = MIBTemplateYAMLGenerator()
    generator.run()

if __name__ == "__main__":
    main()
