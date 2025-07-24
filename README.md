### `README.md` para `mib2template_yaml_generic.py`

#### 📄 Generar Plantillas Zabbix (YAML) desde Archivos MIB (Versión Genérica)

Este script genera una **plantilla base** de Zabbix en **formato YAML** (compatible con Zabbix 6.0+) a partir de **cualquier archivo MIB válido**. Es completamente **agnóstico de la marca** del dispositivo.

Es una herramienta para **automatizar la creación inicial** de plantillas SNMP, proporcionando una estructura sólida que luego **debe ser revisada y enriquecida manualmente** con triggers, gráficos y otros elementos específicos del caso de uso.

##### 🛠 Requisitos Previos

*   **Python 3.6+**
*   **Herramientas Net-SNMP** (`snmptranslate`, `snmpget`, etc.)
    ```bash
    # Debian/Ubuntu
    sudo apt update && sudo apt install snmp snmp-mibs-downloader

    # RedHat/CentOS/Rocky/Fedora
    sudo yum install net-snmp net-snmp-utils
    # o en sistemas con dnf
    sudo dnf install net-snmp net-snmp-utils
    ```
*   **Biblioteca PyYAML**: `pip install pyyaml`
*   **(Opcional) Biblioteca pysmi** (para mejor extracción de enums): `pip install pysmi`

```bash
# Instalación de dependencias de Python
pip3 install pyyaml
# Opcional, pero recomendado para mejor soporte de enums
pip3 install pysmi
```

##### 📥 Descargar y Usar

```bash
# Descargar el script
wget -O mib2template_yaml_generic.py https://raw.githubusercontent.com/tu-repo/mib2template_yaml_generic.py

# Hacerlo ejecutable (opcional)
chmod +x mib2template_yaml_generic.py
```

##### 🎯 Ejemplos de Uso

```bash
# Generar template básico para un MIB estándar
python3 mib2template_yaml_generic.py -f /usr/share/snmp/mibs/SNMPv2-MIB.txt -m SNMPv2-MIB

# Generar template con nombre y archivo de salida personalizados
python3 mib2template_yaml_generic.py \
  -f /path/to/CUSTOM-MIB.mib \
  -m CUSTOM-MIB \
  -N "Mi Template Custom" \
  -o mi_template_custom.yaml

# Generar template con configuración de intervalos
python3 mib2template_yaml_generic.py \
  -f /usr/share/snmp/mibs/HOST-RESOURCES-MIB.txt \
  -m HOST-RESOURCES-MIB \
  --check-delay 5m \
  --disc-delay 30m \
  --history 7d
```

##### 📋 Parámetros Disponibles

```bash
usage: mib2template_yaml_generic.py [-h] -f MIB_FILE -m MODULE [-o OUTPUT]
                                    [-N TEMPLATE_NAME] [-G GROUP]
                                    [--check-delay CHECK_DELAY]
                                    [--disc-delay DISC_DELAY]
                                    [--history HISTORY] [--trends TRENDS]

Genera plantilla de Zabbix (YAML) desde archivo MIB

optional arguments:
  -h, --help            show this help message and exit
  -f MIB_FILE, --mib-file MIB_FILE
                        Ruta al archivo MIB (e.g.,
                        /usr/share/snmp/mibs/SNMPv2-MIB.txt)
  -m MODULE, --module MODULE
                        Nombre del módulo MIB (e.g., SNMPv2-MIB)
  -o OUTPUT, --output OUTPUT
                        Nombre del archivo de salida YAML (default:
                        template.yaml)
  -N TEMPLATE_NAME, --template-name TEMPLATE_NAME
                        Nombre de la plantilla (default: <module> SNMP)
  -G GROUP, --group GROUP
                        Grupo de la plantilla (default: Templates)
  --check-delay CHECK_DELAY
                        Intervalo de chequeo para items (default: 1h)
  --disc-delay DISC_DELAY
                        Intervalo de descubrimiento (default: 1h)
  --history HISTORY     Retención del historial (default: 30d)
  --trends TRENDS       Retención de tendencias (default: 0)

Ejemplos:
  mib2template_yaml_generic.py -f /usr/share/snmp/mibs/SNMPv2-MIB.txt -m SNMPv2-MIB
  mib2template_yaml_generic.py -f ./CUSTOM-MIB.mib -m CUSTOM-MIB -N "Mi Template Custom" -o custom_template.yaml
```

##### 🔍 ¿Qué hace el script?

1.  **Carga el MIB**: Utiliza `snmptranslate` para verificar que el archivo MIB es válido y puede ser cargado.
2.  **Lista los Símbolos**: Obtiene una lista de todos los objetos (símbolos) definidos en el MIB.
3.  **Procesa cada Símbolo**:
    *   Obtiene el **OID numérico**.
    *   Obtiene el **nombre completo** (ej., `SNMPv2-MIB::sysDescr.0`).
    *   Obtiene la **descripción** del objeto.
    *   Determina el **tipo de dato** SNMP y lo mapea a un tipo Zabbix (`FLOAT`, `CHAR`, `TEXT`).
    *   Intenta extraer **unidades** (ej., segundos, bytes) del tipo o descripción.
    *   Determina si el objeto es un **item escalar** o una **columna de tabla**.
    *   Intenta extraer definiciones de **enums** (mapeos de valores como `up(1)` -> `1`) para crear `valuemaps`.
4.  **Construye la Estructura del Template**:
    *   Crea una plantilla con nombre y grupo especificados.
    *   Añade todos los **items escalares** encontrados.
    *   Agrupa las **columnas de tabla** por su tabla padre y crea **reglas de descubrimiento** (`discovery_rules`) con sus `item_prototypes`.
    *   Incluye los **`valuemaps`** generados a partir de los enums.
    *   Crea secciones vacías para `graphs`, `triggers` y `dashboards` que puedes completar manualmente.
5.  **Genera el Archivo YAML**: Guarda la estructura en un archivo YAML legible y compatible con Zabbix 6.0+.

##### ⚠️ Notas Importantes

1.  **Base Inicial**: El template generado es una **base**. **No es un template final listo para usar**. Requiere revisión y personalización.
2.  **Items Deshabilitados**: Por defecto, los items se crean sin un estado `ENABLED`, lo que significa que estarán deshabilitados en Zabbix. Esto es una medida de seguridad para evitar sobrecargar el servidor.
3.  **Sin Triggers/Graphs Automáticos**: El script **no genera triggers, gráficos o dashboards** automáticamente. Esta lógica es específica del dispositivo y del entorno de monitoreo.
4.  **Detección de Tablas**: La detección de estructuras de tabla se basa en heurísticas simples (OIDs que terminan en `.1.x`, nombres con `Table`). Puede no ser perfecta para todos los MIBs.
5.  **Extracción de Enums**: La extracción de enums es limitada con `snmptranslate`. Si instalas `pysmi`, el script intentará usarlo para una mejor extracción, aunque la implementación completa de esta característica en el script es básica.
6.  **MIBs y Dependencias**: Asegúrate de que el MIB y todas sus dependencias (otros MIBs que importa) están disponibles para `snmptranslate`. Puedes usar variables de entorno como `MIBDIRS` o la opción `-M` de `snmptranslate` si es necesario.

##### 📤 Importar Template a Zabbix

1.  Accede a la interfaz web de Zabbix.
2.  Ve a **Data collection** → **Templates**.
3.  Haz clic en **Import**.
4.  Selecciona el archivo `template.yaml` generado.
5.  **Revisa cuidadosamente** los items, discovery rules y valuemap generados.
6.  **Agrega manualmente triggers, graphs, dashboards** según tus necesidades de monitoreo.
7.  Habilita los items y reglas de descubrimiento que desees usar.
8.  Guarda la plantilla.
