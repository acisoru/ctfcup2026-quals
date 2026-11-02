21st century man
================

Внутри:

  g.bin     битстрим для Lattice iCE40 UP5K, корпус SG48 (iCEBreaker и совместимые).
            Собран под тактовую 200 МГц и UART 921600 8N1. Пины:
              35  clk       (вход, 200 МГц)
               6  uart_rxd  (вход, данные к плате)
               9  uart_txd  (выход, данные от платы)
  problem   проверялка (Linux x86-64). Рисуете фигуру мышью, жмёте Check.

Запуск:

  ./problem --port /dev/ttyUSB0            # порт, к которому подключена плата
  ./problem --port /dev/ttyUSB0 --baud 921600 --timeout-ms 60000

Флаг: ctfcup{[a-f0-9]+}
