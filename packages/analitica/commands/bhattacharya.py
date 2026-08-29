"""Comando de descomposición poblacional de Bhattacharya."""

from __future__ import annotations


def ejecutar_bhattacharya(args) -> int:
    from ..servicios.servicio_bhattacharya import (
        calibrar_todos_los_lotes,
        exportar_proyeccion_excel,
        generar_proyeccion_empresa,
    )

    print(f"=== MOTOR DE PROYECCION BHATTACHARYA (Campana {args.campania}) ===")
    params_por_lote, df_params = calibrar_todos_los_lotes(
        ruta_excel=args.excel,
        campania=args.campania,
    )
    print(f"[OK] Calibrados {len(params_por_lote)} lotes exitosamente.")

    if args.lote:
        lote_buscado = str(args.lote).strip().upper()
        match = next((p for k, p in params_por_lote.items() if k.upper() == lote_buscado), None)
        if match:
            print(
                f"\n--- Parametros Calibrados para Lote {match.lote} "
                f"({match.modulo}-{match.turno}) ---"
            )
            print(
                f"  Oleada 1 (P1): Pico X1={match.mu1} d, Ancho O1={match.sigma1} d, "
                f"Carga N1={match.N1} frt/pl (RMSE={match.error_p1})"
            )
            print(
                f"  Oleada 2 (P2): Pico X2={match.mu2} d, Ancho O2={match.sigma2} d, "
                f"Carga N2={match.N2} frt/pl"
            )
            print(
                f"  Oleada 3 (P3): Pico X3={match.mu3} d, Ancho O3={match.sigma3} d, "
                f"Carga N3={match.N3} frt/pl"
            )
            print(f"  Calibre:       Peso(t) = {match.peso_a} * exp({match.peso_b} * t)")
        else:
            print(
                f"[!] Lote {args.lote} no encontrado entre los "
                f"{len(params_por_lote)} lotes calibrados."
            )

    df_detalle, df_matriz = generar_proyeccion_empresa(params_por_lote)

    if args.exportar_excel:
        ruta = exportar_proyeccion_excel(df_params, df_matriz, df_detalle, args.exportar_excel)
        print(f"[OK] Reporte exportado a: {ruta}")

    return 0
