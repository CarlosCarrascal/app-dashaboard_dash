"""API modular de campo para Flutter y PostgreSQL.

Las rutas HTTP delegan en servicios, los servicios dependen de puertos y los adaptadores de
infraestructura implementan esos puertos con psycopg. El paquete no importa el ETL ni contiene
extracción de Access. Véase ADR-0016.
"""

__all__: list[str] = []
