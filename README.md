# sudebnye-raskhody-arbitrazh

Приватный переносимый скилл Codex для подготовки заявления о взыскании судебных расходов и акта оказанных юридических услуг по материалам арбитражного дела.

Скилл содержит встроенные рабочие образцы, исходный запускной промпт, исходную инструкцию, реестр материалов и контроль сохранности структуры DOCX. Пользовательский файл или папка «Исходное заявление и акт оказанных услуг» всегда имеет приоритет над встроенными образцами.

## Установка на другом компьютере

Понадобятся Codex, Git и доступ к этому закрытому GitHub-репозиторию.

### Через GitHub CLI

```powershell
gh auth login
$skillRoot = Join-Path $env:USERPROFILE ".codex\skills"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
gh repo clone aleksskott2000-cyber/sudebnye-raskhody-arbitrazh (Join-Path $skillRoot "sudebnye-raskhody-arbitrazh")
python (Join-Path $skillRoot "sudebnye-raskhody-arbitrazh\scripts\self_test.py")
```

### Через Git

```powershell
$skillRoot = Join-Path $env:USERPROFILE ".codex\skills"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
git clone https://github.com/aleksskott2000-cyber/sudebnye-raskhody-arbitrazh.git (Join-Path $skillRoot "sudebnye-raskhody-arbitrazh")
python (Join-Path $skillRoot "sudebnye-raskhody-arbitrazh\scripts\self_test.py")
```

После установки перезапустите Codex или откройте новую задачу. Для обновления:

```powershell
git -C (Join-Path $env:USERPROFILE ".codex\skills\sudebnye-raskhody-arbitrazh") pull --ff-only
```

## Использование

Передайте Codex путь к папке дела и попросите использовать `$sudebnye-raskhody-arbitrazh`. Скилл анализирует все документы и сохраняет готовые заявление и акт в эту же папку.

Чтобы применить собственное оформление, положите в папку дела файлы или папку с названием «Исходное заявление и акт оказанных услуг» либо прямо назовите нужные образцы в запросе. Скилл будет редактировать их копии «на месте» и сравнит отрисованный результат с исходником перед выдачей.

## Проверка целостности

```powershell
python scripts/self_test.py
```

Поскольку встроенные DOCX могут содержать реальные реквизиты и изображение подписи, репозиторий должен оставаться закрытым.
