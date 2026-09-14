# Componentes compartidos

La capa compartida agrupa UI reutilizable, tablas, formularios, gráficos y utilidades. El primer
corte ya utiliza `PageHeaderComponent`, `KpiCardComponent` y el gráfico ECharts por módulo; las
tablas de Evaluaciones utilizan TanStack Table con HTML/SCSS propio y paginación en el backend.
Los gráficos específicos y sus cálculos residen en el feature de Evaluaciones; la capa compartida
conserva los componentes utilizados por los demás módulos.
