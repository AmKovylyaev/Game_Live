# Пиксельная экосистема

Небольшая симуляция пищевой цепочки на Python и `tkinter`: трава восстанавливается, травоядные ищут еду, а хищники охотятся.

![Игра на паузе](docs/images/gameplay.png)

## Запуск

### Готовые приложения

Скачайте подходящий файл на [странице Releases](https://github.com/AmKovylyaev/Game_Live/releases). Python, `uv` и исходный код для них не нужны.

- macOS (Apple Silicon): `PixelEcosystem-macos-arm64.zip` → `PixelEcosystem.app`;
- macOS (Intel): `PixelEcosystem-macos-x64.zip` → `PixelEcosystem.app`;
- Windows x64: `PixelEcosystem-windows-x64.zip` → `PixelEcosystem.exe`;
- Linux x64: `PixelEcosystem-linux-x64.tar.gz` → `PixelEcosystem`.

Сборки пока не подписаны.

- На macOS при первом запуске откройте приложение через контекстное меню → «Открыть», если Gatekeeper его блокирует.
- На Windows SmartScreen может показать предупреждение. Нажмите «Подробнее» → «Выполнить в любом случае» только если файл скачан со страницы этого репозитория.

### Из исходников

Нужны Python 3.12+ и `uv`:

```bash
uv run python main.py
```

## Разработка

```bash
uv sync --group dev
uv run pytest
```

Ruff запускается перед коммитом и pull request:

```bash
uv run ruff check .
uv run ruff format --check .
```

Готовые приложения собирает GitHub Actions. Публикация тега вида `v*` создаёт Release с архивами для macOS, Windows и Linux.
