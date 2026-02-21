# Leave AI UX Spec (v2)

## 1) Пользователи
- **HR/кадровик**: быстро понять, можно ли отправлять заявление, что исправить, выгрузить итог.
- **Сотрудник**: проверить своё заявление до отправки, получить готовый текст для переписывания.
- **Руководитель/ассистент**: увидеть критичные ошибки и request_id при инцидентах.

## 2) JTBD
1. Проверить заявление.
2. Понять, что именно не так.
3. Исправить данные без боли.
4. Получить готовый текст и экспорт.

## 3) Карта экранов/состояний
- **Landing / Upload**
- **Processing** (progress + cancel)
- **Results / Review** (default)
- **Fix mode** (редактирование поля в inspector)
- **Export**
- **Diagnostics** (скрыто по умолчанию, drawer)
- **History** (drawer)

## 4) Сценарии
### Happy path
1. Загрузить PDF → обработка.
2. Виден banner-вердикт.
3. Во вкладке «Ошибки» — чеклист.
4. Клик на issue → справа сразу редактор.
5. Скопировать текст заявления / экспорт.

### Negative 1: timeout/429/5xx
- Banner показывает понятный заголовок.
- request_id виден всегда.
- Есть кнопка «Повторить».

### Negative 2: нет подписи
- Issue в категории signature.
- Inspector объясняет, что исправить.

### Negative 3: даты/сроки не сходятся
- Issue в dates/counts.
- Клик ведёт к полю дат/дней, можно править локально.

## 5) Принципы
- **Conclusion first**: вердикт всегда наверху.
- **Issues-first**: сначала ошибки, потом детали.
- **Fix by click**: ошибка ведёт к полю.
- **Logs last**: диагностика в нижнем drawer.

## 6) Wireframes
### Desktop
```
[HEADER (sticky): title | History Theme Help]
[SIDEBAR sticky][MAIN tabs + banner + list ][INSPECTOR sticky]
[Upload         ][Decision banner           ][Selected issue ]
[Stepper        ][Tabs: Issues/Data/Text...][Edit controls  ]
[Counts         ][Issue Explorer            ][Apply/Next     ]
[LOG DRAWER collapsed -> open diagnostics]
```

### Mobile
```
[Header]
[Decision banner]
[Segmented tabs]
[Issues/Data/Text/Export content]
[Sticky action bar: Исправить | Скопировать текст | Экспорт]
[Inspector as bottom sheet]
```

## 7) Компоненты
- Sticky Header
- Left Sidebar: upload + stepper + counters
- Main: decision banner + tabs + content
- Right Inspector: selected issue details + editor
- Bottom log drawer
- Toast

## 8) Микрокопи
- Primary:
  - Landing: **Проверить заявление**
  - Processing: **Отменить**
  - Review (needs_rewrite): **Исправить ошибки**
  - Review (ok): **Скопировать текст**
- Secondary: **Загрузить другое**, **История**, **Диагностика**

## 9) Accessibility
- Полная клавиатурная навигация (tab/enter/esc).
- Видимый focus-visible.
- `aria-live` для прогресса/тостов/вердикта.
- Tabs: `tablist/tab/tabpanel`.
- Диагностика/история доступны, но не мешают основной задаче.
