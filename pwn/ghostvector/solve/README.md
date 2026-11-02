# GhostVector — organizer solver

## Загрузка и запуск

В минимальном guest нет server-side `scp` и SFTP. Бинарник загружается через
SSH stdin:

```sh
ssh -p <PORT> user@<HOST> \
  'cat > /home/user/solve && chmod 700 /home/user/solve' < solve/solve
ssh -p <PORT> user@<HOST> /home/user/solve
```

Вторая команда должна напечатать точный флаг экземпляра `ctfcup{...}`.

## Что проверяет solver

1. Создаёт user mapping по адресу, который принимает `GV_GET_LAYOUT`.
2. Public ioctl возвращает замаскированные физические адреса PTE этого mapping
   и защищённой страницы флага.
3. Кастомная vector-store инструкция записывает подготовленный user-readable
   RISC-V PTE в физическую память побайтно.
4. `mprotect()` заставляет ядро обновить TLB; исходная виртуальная страница
   начинает отображать страницу флага, после чего solver печатает её.
