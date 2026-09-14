# Dominios del panel

`admin/` contiene el primer corte funcional: seguridad, resumen, evaluaciones, maestros, calidad
y cargas. La ruta `admin/operaciones` es el punto de entrada visual para los dominios que siguen.

Los módulos agrícolas se incorporarán como features independientes, manteniendo la misma regla de
lazy loading y permisos:

- empresas, fundos, lotes, variedades y campañas;
- evaluaciones, forecast y cosecha;
- riego, packing y tareo;
- reportes.
