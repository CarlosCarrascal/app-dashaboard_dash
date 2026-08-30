import argparse

from analitica.aplicacion.servicios import demo_auditoria_en_vivo as _demo

ajustar_lote = _demo.ajustar_lote
auditar_lote_en_vivo = _demo.auditar_lote_en_vivo


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    auditar_lote_en_vivo()


if __name__ == "__main__":
    main()
