"""Fase 1, na mão:  python examples/phase1.py     (add `sim` para o simulador, sem o braço)

Edite este arquivo e rode de novo. Toda coordenada é em mm: x para a direita, y para cima, (0, 0) no canto de baixo à esquerda da folha."""
import sys

from penarm import Plotter, find_port

port = None if "sim" in sys.argv[1:] else find_port()
with Plotter(port) as p:                      # p é o braço
    w, h = p.canvas.w, p.canvas.h             # tamanho da folha: x vai de 0 a w, y de 0 a h
    print(f"folha: {w:.0f} x {h:.0f} mm")
    x, y, lado = w / 2 - 15, h / 2 - 15, 30   # canto de baixo à esquerda de um quadrado de 30 mm, no meio da folha

    print(p.draw_line(x, y, x + lado, y, dry_run=True)["ascii"])   # ensaio: mostra o desenho e não move nada
    p.draw_line(x, y, x + lado, y)                                 # o lado de baixo

    # SUA VEZ: complete o quadrado com mais 3 draw_line.
    # O braço não levanta a caneta: cada linha começa onde a anterior terminou.
