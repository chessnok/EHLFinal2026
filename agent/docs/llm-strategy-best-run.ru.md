# Стратегия `llm` в лучших прогонах: промпты и как использовался результат

Состояние на 10.10.2026.

## Какая версия

Почти наверняка лучшие тренировочные прогоны шли с промптами `agent/src/negotiator/strategy/llm_strategy.py` из
коммита **`8670be2`**:

- это последняя закоммиченная версия файла;
- она появилась в 13:54 UTC, до прогонов (14:33–15:10 UTC).

API арены не записывает версию кода, поэтому это вывод по времени, а не по логам.

**Нестыковка.** Провайдер `claude-code:haiku`, на котором, судя по `rejections.md`, шли прогоны, закоммичен только в
14:59 UTC. Значит, у тиммейта была локальная копия, и промпт там теоретически мог отличаться.

Лучшие скоры команды по кейсам: 7 из 10 дала стратегия `llm` (P01, P03, P04, P05, P07, P10, P11), 3 — tactical
(P02, P08, P18).

## Что говорили модели

### 1. Профиль поставщика

Один вызов на поставщика, до открытия сессии, пока 60-секундный таймер ещё не идёт.

- **Роль модели:** аналитик закупок.
- **На вход — досье поставщика:**
  - кейс и брифинг;
  - мастер-данные и кредитный рейтинг;
  - скоркарты, договоры, история цен и переговоров, новости;
  - до 10 последних писем и заметок.
- **Задача:** понять, что двигает поставщика.
- **На выход — JSON:** краткая ситуация, драйверы (деньги, объём, мощности и т. д.), нехватка денег 0–1,
  жёсткость 0–1, отношения, рычаги, какие аргументы работают, чего избегать, тон.

### 2. Ход

Один вызов на каждое письмо.

- **Роль модели:** закупщик. Цель — минимальная C без нарушения обязательных условий.
- **Разделение ролей:** явно сказано, что все цены и варианты условий считает код, а модель выбирает только стратегию
  раунда и пишет текст.
- **На вход:**
  - кейс и раунд, профиль из шага 1;
  - стоящее предложение поставщика и его C, наша альтернатива;
  - наша прошлая и запланированная цена;
  - обсуждаемые поля с вариантами;
  - пронумерованные аргументы;
  - последние 6 писем треда.
- **На выход — JSON:** позиция (давить, обменять, держать, принять), доля уступки 0–1, рычаг, номера аргументов,
  просить ли разбивку себестоимости, вопрос, текст письма, причина.
- **Ограничения на текст:**
  - 40–120 слов, без цен, процентов, ID и приветствия;
  - не раскрывать срочность, бюджет и отсутствие альтернативы;
  - не утверждать фактов вне списка аргументов;
  - ссылаться на «the options below» и предлагать поставщику выбрать вариант, потому что все они для нас равноценны.

## Как код использовал ответы

| Ответ модели | Что с ним делал код |
|---|---|
| Профиль | Только подставлялся в промпт хода как контекст; сам код на профиль не реагировал |
| `stance` = hold или accept | Тред откладывался. Принятие делал код при закрытии: самый дешёвый действующий оффер, если он лучше альтернативы |
| `stance` = push или trade | Отправлялось письмо |
| `concession` | Масштабировала шаг от нашей прошлой цены к цене по графику baseline v2. Цена не падала ниже прошлой и не поднималась выше цены поставщика; если почти совпала, тред откладывался |
| `lever` | Только при trade: в начало меню добавлялся вариант со значением поставщика на этом поле и ценой с той же C |
| Номера аргументов | Код вставлял выбранные аргументы дословно, с цифрами и ID; каждый ID один раз за кейс. Если в 1-м раунде модель ничего не выбрала, их подбирал baseline |
| `ask_cost_breakdown` | Фиксированная фраза с просьбой прислать разбивку, один раз |
| `question` | Дописывался в письмо, придуманные ID вырезались |
| `message` | Тело письма. Код вырезал придуманные ID и целиком предложения с деньгами и процентами, добавлял приветствие, аргументы, список вариантов и подпись |
| `reason` | Только в телеметрию |

**Что всегда решал код, без модели:**

- **Варианты условий:** меню с равной C из baseline v2 — наша оптимальная структура, структура поставщика и вариант с
  короткой оплатой, все по одной цене для нас.
- **Ответы `agreed` и `final_offer`:** тред сразу откладывался, модель даже не спрашивали.
- **Последний раунд или дедлайн волны:** тоже откладывание без модели.
- **Ошибка модели или нет ответа за 30 с:** ход делал baseline.

## Что из этого вышло, по разбору практики

Подробно: [`practice-analysis.ru.md`](practice-analysis.ru.md) и [`rejections.md`](rejections.md).

- **Профиль ни на что не влиял напрямую.** Сигналы вроде «хочу быструю оплату» или «требую индексную оговорку» модель
  видела, но промпт не говорил, что с ними делать. Поставщики спрашивали «Which volume can you commit to?» в
  57 репликах — ответа не было ни разу.
- **`final_offer` всегда принимался без попытки.** Так P10 закрылся в 1-м раунде.
- **Обмен на индексную оговорку брал значение поставщика.** Нужна была самая дешёвая для нас — с максимальной мёртвой
  зоной. Отказ от оговорки привёл к уходу поставщика в P18.
- **Модель могла выбрать уступку около 0 при движущемся поставщике.** Отсюда шаги по €0.02 в P11.
- **Фильтр ловил только предложения с цифрами.** Утверждения без цифр проходили, например «You mentioned your budget»
  в P11.

Эти места переделаны в новой версии стратегии.

## Приложение: промпты дословно (коммит `8670be2`)

### Профиль поставщика (`PROFILE_SYSTEM`)

```text
You are a senior procurement analyst at Hollerau Pumpenwerke, a German pump maker.
Read everything we know about one supplier and work out what will move it in a negotiation: what it is
dealing with right now, what it values, what it cannot do, and how it reacted in the past.

Return JSON:
{"summary": "<3 sentences: the supplier's situation and what it wants>",
 "drivers": ["<from: cash, volume, capacity, contract_security, list_price, relationship, quality, energy_costs,
              material_costs, wages, lead_time, other>"],
 "cash_pressure": <0..1, how much it needs money soon>,
 "firmness": <0..1, how little it usually concedes>,
 "relationship": "good" | "neutral" | "strained",
 "levers": ["<negotiable fields that should matter to it, from the list given>"],
 "arguments_that_work": "<which kinds of argument it accepts, or 'unknown'>",
 "avoid": "<what would backfire with this supplier>",
 "tone": "<how to write to it>"}
```

### Ход (`DECIDE_SYSTEM`)

```text
You are the buyer of Hollerau Pumpenwerke negotiating by e-mail with an industrial supplier.
Goal: the lowest total cost C for our need, without breaking a must-have. Code computes every price and
every term sheet; you choose the strategy for this round and write the e-mail text.

Decide:
- stance: "push" (ask for more with a concession of ours), "trade" (offer something the supplier values -
  a lever - for a better price), "hold" (stop here, keep the standing offer for the close), or "accept"
  (its standing offer is good enough; code still checks it beats our alternative).
- concession: 0..1 - how much of the scheduled price step to give this round (0 = stand firm, 1 = full step).
  Concede little when the supplier moves on its own, more when it is stuck but reasonable.
- lever: one negotiable field to trade, or "none".
- evidence: up to 3 argument numbers from the list (they are inserted verbatim with their figures and IDs);
  pick only those relevant to what the supplier just said; [] if none.
- ask_cost_breakdown: true to ask for its cost breakdown (useful once, early).
- question: one short question to the supplier, or "".
- message: the e-mail body WITHOUT greeting, signature, prices, percentages, data IDs or term sheets (code
  adds all of these). 40-120 words, polite, firm, specific to what the supplier wrote. Never reveal urgency,
  a budget, a missing alternative or our target. State no fact that is not in the arguments list: no market
  benchmarks, competitor prices, other bids, volume growth, volume tiers, forecasts or new projects - the
  supplier asks for proof and trusts us less. Do not promise volume we have not offered in the options.
  Refer to "the options below" instead of naming prices or terms; the options are equal value to us, so
  invite the supplier to pick the one that suits it.

Return JSON: {"stance": "...", "concession": 0.0, "lever": "...", "evidence": [], "ask_cost_breakdown": false,
"question": "...", "message": "...", "reason": "<one sentence: why>"}
```
