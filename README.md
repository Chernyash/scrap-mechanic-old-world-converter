# Scrap Mechanic Save Migrator (v27 → v28)

Unofficial tool to convert Survival world databases from **Early Access (savegameversion 27)** to **Scrap Mechanic 1.0 / Drilling Thunder (savegameversion 28)** so old worlds can be loaded in the new client.

> **Warning:** Always keep a backup. This is reverse-engineered and unsupported by Axolot Games. Old terrain will not gain new 1.0 content (mines, quests, etc.).

---

## English

### What it does

Compares the old and new `.db` formats and rewrites the save so version **28** can open it:

| Change | Details |
|--------|---------|
| `Game.savegameversion` | `27` → `28` |
| `Game.uniqueIds` | Counter count `16` → `17`, appends `0x40000000` |
| `ScriptableObject` table | Adds `worldId` column + index |
| `ScriptableObject.data` | Inserts `FF FE` (noWorld / 65534) after the 7-byte header |
| `ChildShape.data` | Appends `0x00` (lengths 42/47 → 43/48) |
| `Unit.data` | Appends `0x00` (length 64 → 65) |

### Requirements

- Python 3.9+ (stdlib only: `sqlite3`, `argparse`, `shutil`)

### Usage

```bash
python migrate_sm_v28.py <source_v27.db> <output_v28.db>
```

Example:

```bash
python migrate_sm_v28.py Povtor3_v27_backup.db Povtor3_v28.db
```

Then copy `Povtor3_v28.db` over your world file:

```
%AppData%\Axolot Games\Scrap Mechanic\User\User_<SteamID>\Save\Survival\<WorldName>.db
```

### Backup locations (this project)

- `Povtor3_v27_backup.db` — original v27 save  
- `Povtor3_v28.db` — migrated output  

### Notes

- Do **not** use SQL `blob || X'00'` for appends — SQLite coerces `||` to text and corrupts binary data. This script updates blobs in Python.
- Source should be savegameversion **27**. Already-migrated pieces are skipped where detected.
- If the game crashes on load, restore the backup and report the error.

---

## Русский

### Что делает

Неофициальный конвертер Survival-миров из **старой версии (savegameversion 27)** в формат **Scrap Mechanic 1.0 / Drilling Thunder (savegameversion 28)**, чтобы можно было зайти в старый мир из нового клиента.

> **Важно:** Сначала сделай бэкап. Инструмент неофициальный. Старая генерация мира **не получит** новый контент 1.0 (шахты, квесты и т.д.) — только совместимость загрузки.

### Что меняется

| Изменение | Детали |
|-----------|--------|
| `Game.savegameversion` | `27` → `28` |
| `Game.uniqueIds` | Счётчиков `16` → `17`, в конец добавляется `0x40000000` |
| Таблица `ScriptableObject` | Колонка `worldId` + индекс |
| `ScriptableObject.data` | После 7-байтного заголовка вставляется `FF FE` (noWorld / 65534) |
| `ChildShape.data` | В конец байт `0x00` (длины 42/47 → 43/48) |
| `Unit.data` | В конец байт `0x00` (длина 64 → 65) |

### Требования

- Python 3.9+ (только стандартная библиотека)

### Как пользоваться

```bash
python migrate_sm_v28.py <исходный_v27.db> <результат_v28.db>
```

Пример:

```bash
python migrate_sm_v28.py Povtor3_v27_backup.db Povtor3_v28.db
```

Потом замени файл мира на результат:

```
%AppData%\Axolot Games\Scrap Mechanic\User\User_<SteamID>\Save\Survival\<ИмяМира>.db
```

### Файлы в этой папке

- `Povtor3_v27_backup.db` — оригинал v27  
- `Povtor3_v28.db` — сконвертированный сейв  
- `migrate_sm_v28.py` — скрипт миграции  

### Заметки

- Не склеивай BLOB через SQL `||` — SQLite превращает это в text и ломает данные. В скрипте допись байта делается в Python.
- Ожидается сейв версии **27**. Уже обновлённые куски по возможности пропускаются.
- Если игра падает при входе — верни бэкап и пришли текст/скрин ошибки.

---

## License / Лицензия

Provided as-is for personal use. Not affiliated with Axolot Games.  
Как есть, для личного использования. Не связано с Axolot Games.
