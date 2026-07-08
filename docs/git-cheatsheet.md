# Git: rebase, merge, cherry-pick

---

## merge

Объединяет две ветки, создавая **merge commit** (или fast-forward если возможно).

```
main:    A---B---C
                  \
feature:           D---E
```

После `git merge feature`:

```
main:    A---B---C---M   ← merge commit
                  \ /
feature:           D---E
```

### Когда использовать
- Когда важно сохранить историю "как было"
- Публичные ветки (main, develop) где rebase опасен
- Когда хочешь видеть точку слияния

### Команды

```bash
# Слить feature в main
git checkout main
git merge feature

# Fast-forward только (без merge commit)
git merge --ff-only feature

# Всегда создавать merge commit даже при fast-forward
git merge --no-ff feature

# Отменить merge если ещё не закоммичен
git merge --abort
```

---

## rebase

Переносит коммиты одной ветки **поверх** другой. История становится линейной.

```
main:    A---B---C
                  \
feature:           D---E
```

После `git rebase main` (из ветки feature):

```
main:    A---B---C
                  \
feature:           D'---E'   ← коммиты переписаны (новые хэши)
```

### Когда использовать
- Локальные feature-ветки перед merge в main
- Когда хочешь чистую линейную историю
- `git pull --rebase` вместо `git pull` — избегает лишних merge commit

### Когда НЕ использовать
- На публичных ветках (main, develop) — переписывает хэши, сломает историю у других

### Команды

```bash
# Перебазировать текущую ветку на main
git checkout feature
git rebase main

# Интерактивный rebase — редактировать, squash, переставлять коммиты
git rebase -i HEAD~3   # последние 3 коммита

# Продолжить после разрешения конфликтов
git rebase --continue

# Отменить rebase
git rebase --abort
```

### Интерактивный rebase (rebase -i)

```bash
git rebase -i HEAD~4
```

Откроется редактор:

```
pick a1b2c3 add login endpoint
pick d4e5f6 fix typo in login
pick 7g8h9i add logout endpoint
pick j0k1l2 wip: temp debug log
```

Меняешь `pick` на:
- `squash` (или `s`) — склеить с предыдущим коммитом
- `reword` (или `r`) — изменить сообщение
- `drop` (или `d`) — удалить коммит
- `edit` (или `e`) — остановиться и внести правки

---

## cherry-pick

Берёт **конкретный коммит** из любой ветки и применяет его к текущей.

```
main:      A---B---C
                    \
feature:             D---E---F
```

Хочешь только коммит E в main:

```bash
git checkout main
git cherry-pick <hash-of-E>
```

```
main:      A---B---C---E'   ← копия E с новым хэшем
```

### Когда использовать
- Нужен один конкретный фикс из feature-ветки, не весь feature
- Бэкпорт хотфикса с main на release-ветку
- Случайно закоммитил не в ту ветку

### Команды

```bash
# Применить один коммит
git cherry-pick abc1234

# Несколько коммитов
git cherry-pick abc1234 def5678

# Диапазон коммитов (от старого к новому, не включая первый)
git cherry-pick abc1234..def5678

# Применить без автоматического коммита (проверить сначала)
git cherry-pick --no-commit abc1234

# Продолжить после конфликта
git cherry-pick --continue

# Отменить
git cherry-pick --abort
```

---

## Сравнение

| | merge | rebase | cherry-pick |
|---|---|---|---|
| История | сохраняет ветвления | линейная | точечная |
| Хэши коммитов | не меняются | меняются | создаёт новый |
| Что берёт | всю ветку | всю ветку | конкретный коммит |
| Конфликты | один раз | на каждом коммите | на каждом коммите |
| Безопасно для public | да | нет | да |

---

## Типичный рабочий процесс

```bash
# 1. Работаешь в feature-ветке
git checkout -b feature/login

# 2. Делаешь коммиты...

# 3. Main обновился пока ты работал — подтягиваешь
git fetch origin
git rebase origin/main

# 4. Squash мусорных коммитов перед merge
git rebase -i origin/main

# 5. Merge в main
git checkout main
git merge --no-ff feature/login

# 6. Хотфикс нужен на старой release-ветке
git checkout release/1.0
git cherry-pick <hash-of-fix>
```
