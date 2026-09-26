# Документація — BaseLayout + ProductLayout
elektroschit.com.ua | src/layouts/
Актуально станом на: 2026-07-21

---

## ЗМІСТ

1. [BaseLayout — загальне для всіх сторінок](#baselayout)
2. [ProductLayout — шаблон продуктових сторінок](#productlayout)
3. [Зв'язок між ними](#звязок-між-ними)
4. [Довідник значень `section`](#довідник-значень-section)

---

<a name="baselayout"></a>
## 1. BaseLayout.astro

**Файл:** `src/layouts/BaseLayout.astro`
**Посилання:** https://raw.githubusercontent.com/Vah509/elektro/main/src/layouts/BaseLayout.astro

### Що це і навіщо

Єдиний layout для **всіх** сторінок сайту. Замість того щоб кожна сторінка мала свій `<!DOCTYPE html>`, `<head>`, шапку і футер — все це написано один раз тут. Кожна сторінка просто обгортається в BaseLayout і передає свої дані через об'єкт `page`.

**До BaseLayout:** 14 сторінок з повним HTML кожна — дублювання тегів, шрифтів, скриптів. Зміна в шапці = правка 14 файлів.
**Після BaseLayout:** змінюєш один файл — змінюється весь сайт.

---

### Що входить у BaseLayout автоматично

**`<head>` на кожній сторінці:**

- `<title>` — з `page.title`
- `<meta name="description">` — з `page.description`
- `<link rel="canonical">` — з `page.canonical`
- Open Graph: `og:type`, `og:title`, `og:description`, `og:url`, `og:locale` (uk_UA), `og:site_name` (Elektroschit)
- Шрифти: Geologica 700 (заголовки) + Manrope 400/500/600 (текст)
- `main.css` — базові стилі, завжди
- Сторінкові CSS — через `<slot name="head" />`
- GTM — тільки якщо `GTM_ID` в `config.ts` не порожній
- Microsoft Clarity — тільки якщо `CLARITY_ID` не порожній
- Верифікаційні мета-теги — якщо передано `page.verifyMeta`

**`<body>` на кожній сторінці:**

- GTM noscript iframe (тільки якщо GTM_ID заповнений)
- `<Header>` — отримує `activePage` з `page.section`
- Хлібні крихти — якщо `page.crumbs` не порожній
- `<slot />` — унікальний контент сторінки
- `<Footer>`
- JSON-LD: **LocalBusiness** (контакти компанії для Google) + **BreadcrumbList** (з `page.crumbs`)

---

### Пропс `page` — всі поля

| Поле | Тип | Обов'язкове | Опис |
|---|---|---|---|
| `section` | string | ✅ | activePage для Header. Дивись [довідник нижче](#довідник-значень-section) |
| `title` | string | ✅ | Текст тегу `<title>`. До 60 символів |
| `description` | string | ✅ | Мета-опис. 150–160 символів |
| `canonical` | string | ✅ | Повний URL з завершальним слешем |
| `crumbs` | Crumb[] | ✅ | Масив хлібних крихт. `[]` — крихти не рендеряться |
| `ogType` | string | ❌ | Дефолт: `'website'`. Для карток портфоліо: `'article'` |
| `verifyMeta` | VerifyMeta[] | ❌ | Верифікаційні мета-теги (Search Console, Ahrefs тощо) |

**Тип Crumb:**
```typescript
{ label: string, href?: string }
// href є у всіх крихтах крім останньої (поточна сторінка — без href)
```

---

### Приклади використання BaseLayout

**Головна сторінка (без крихт):**
```astro
---
import BaseLayout from '../layouts/BaseLayout.astro';
import { SITE_CANONICAL } from '../config';

const page = {
  section:     '',
  title:       'Виготовлення електрощитів на замовлення | elektroschit.com.ua',
  description: 'Силові щити та щити керування. Гарантія 12 міс. Київ та вся Україна.',
  canonical:   `${SITE_CANONICAL}/`,
  crumbs:      [],
};
---
<BaseLayout {page}>
  <link slot="head" rel="stylesheet" href="/css/em-home.css" />
  <!-- контент сторінки -->
</BaseLayout>
```

**Сторінка продукції (з крихтами):**
```astro
---
import BaseLayout from '../../layouts/BaseLayout.astro';
import { SITE_CANONICAL } from '../../config';

const page = {
  section:     'produktsiia',
  title:       'Виготовлення ГРЩ та ВРЩ на замовлення | elektroschit.com.ua',
  description: 'Силові щити до 630А. Гарантія 12 місяців. Київ та вся Україна.',
  canonical:   `${SITE_CANONICAL}/posluhy-ta-produktsiia/hrshch/`,
  crumbs: [
    { label: 'Головна',   href: '/' },
    { label: 'Продукція', href: '/posluhy-ta-produktsiia/' },
    { label: 'ГРЩ та ВРЩ' },  // без href = поточна сторінка
  ],
};
---
<BaseLayout {page}>
  <link slot="head" rel="stylesheet" href="/css/em-hrshch.css" />
  <!-- контент сторінки -->
</BaseLayout>
```

**Картка портфоліо (ogType article):**
```astro
const page = {
  section:     'vykonani-roboty',
  title:       seoTitle,
  description: data.description,
  canonical:   `${SITE_CANONICAL}/vykonani-roboty/${work.slug}/`,
  ogType:      'article',
  crumbs: [
    { label: 'Головна',         href: '/' },
    { label: 'Виконані роботи', href: '/vykonani-roboty/' },
    { label: data.title },
  ],
};
```

**Верифікаційний мета-тег:**
```astro
const page = {
  // ...інші поля...
  verifyMeta: [
    { name: 'ahrefs-site-verification', content: 'xxxxxxxx' },
  ],
};
```

---

### Як підключити аналітику

Все через `src/config.ts`:
```typescript
export const GTM_ID     = 'GTM-XXXXXXX';   // вставить GTM на всі сторінки
export const CLARITY_ID = 'xxxxxxxxxx';     // теплові карти Clarity
```
Поки рядок порожній (`''`) — скрипт не вставляється в HTML взагалі. Як тільки заповниш — з'являється на всіх сторінках без жодних інших правок.

---

### Залежності BaseLayout

Імпортує:
- `src/components/Header.astro`
- `src/components/Footer.astro`
- `src/config.ts` → `PHONE`, `EMAIL`, `ADDRESS_STREET`, `ADDRESS_CITY`, `MAPS_URL`, `WORK_HOURS`, `GTM_ID`, `CLARITY_ID`, `SITE_CANONICAL`

---

<a name="productlayout"></a>
## 2. ProductLayout.astro

**Файл:** `src/layouts/ProductLayout.astro`
**Посилання:** https://raw.githubusercontent.com/Vah509/elektro/main/src/layouts/ProductLayout.astro

### Що це і навіщо

Спеціалізований layout поверх BaseLayout для **8 продуктових сторінок** (всі, крім `elektromontazh`). Містить фіксовану структуру блоків зі стандартним чергуванням фонів. Сторінка передає тільки дані — ProductLayout сам збирає всю розмітку.

**Виняток:** `elektromontazh.astro` — не використовує ProductLayout через принципово іншу структуру (центрований hero, без галереї).

---

### Структура блоків і чергування фонів

```
1. Hero           → зелений  (em-hero-product)
2. Галерея        → білий    (em-section)
3. Застосування   → зелений  (em-section-alt)
[slot extra1]     → білий    (сторінка сама задає клас)
[slot extra2]     → зелений  (сторінка сама задає клас)
5. Характеристики → білий    (em-section)
6. Компоненти     → зелений  (em-section-alt)  — якщо brands передані
   [якщо brands відсутній: <hr class="em-divider"> між двома білими]
7. Як ми працюємо → білий    (em-section)
8. Переваги       → зелений  (em-section-alt)
9. FAQ            → білий    (вбудовано у FaqAccordion)
10. ContactBlock  → зелений  (вбудовано)
11. AlsoMake      → білий    (вбудовано)
```

---

### Які сторінки використовують які слоти

| Сторінка | extra1 | extra2 |
|---|---|---|
| `hrshch` | — | — |
| `dymovydalennia` | ✅ | — |
| `dvyhuny` | ✅ | — |
| `shuz` | — | — |
| `krm` | — | — |
| `zenitni-lihtari` | — | — |
| `ahro` | — | — |
| `plk` | ✅ | ✅ |

---

### Пропс `page` та всі поля ProductLayout

ProductLayout приймає `page` і передає його прямо в BaseLayout — поля ті самі, що описані у розділі BaseLayout вище.

**Решта пропсів ProductLayout:**

| Пропс | Тип | Обов'язкове | Опис |
|---|---|---|---|
| `page` | PageProps | ✅ | SEO + крихти (прокидається в BaseLayout) |
| `slug` | string | ✅ | Slug сторінки для `AlsoMake.currentSlug` |
| `hero` | HeroProps | ✅ | Дані для блоку 1 |
| `gallery` | GalleryProps | ✅ | Дані для блоку 2 |
| `objects` | ObjectsProps | ✅ | Дані для блоку 3 |
| `specs` | SpecsProps | ✅ | Дані для блоку 5 |
| `brands` | BrandsProps | ❌ | Дані для блоку 6. Якщо не передані — замість блоку буде `<hr>` |
| `steps` | StepsProps | ✅ | Дані для блоку 7 |
| `why` | WhyProps | ✅ | Дані для блоку 8 |
| `faq` | FaqProps | ✅ | Дані для блоку 9 |
| `contactTitle` | string | ✅ | Заголовок ContactBlock |

**Slots:**

| Slot | Фон | Хто використовує |
|---|---|---|
| `head` | — | Будь-яка сторінка (додаткові CSS/meta у `<head>`) |
| `extra1` | білий | dymovydalennia, dvyhuny, plk |
| `extra2` | зелений | plk |

---

### Детальні типи пропсів

```typescript
hero: {
  tag:     string;          // напис над H1: "Виготовлення · Київ та область"
  h1:      string;          // заголовок сторінки
  lead:    string;          // лід-текст під H1
  badges:  string[];        // HTML-рядки бейджів: '<strong>від 2 тижнів</strong> — виготовлення'
  collage: {                // рівно 4 фото для коллажу 2×2
    src: string;
    alt: string;
  }[];
}

gallery: {
  h2:    string;
  items: {
    src:     string;
    alt:     string;
    caption: string;
    large?:  boolean;       // true для першого великого фото (span 2 рядки)
  }[];
}

objects: {
  label: string;            // мітка секції (em-section-label)
  h2:    string;
  lead?: string;            // необов'язковий підзаголовок
  cards: {
    num:   string;          // номер картки: "01", "02" тощо
    title: string;
    text:  string;
  }[];
}

specs: {
  h2:   string;
  rows: {
    label: string;
    value: string;
  }[];
}

brands?: {                  // якщо не передати — блок замінюється на <hr>
  main: string[];           // основні бренди: ['ETI', 'Hager', ...]
  eco:  string[];           // економ: ['E-Next', 'Asko', ...]
}

steps: {
  h2:    string;
  items: {                  // нумеруються автоматично (01, 02...)
    title: string;
    text:  string;
  }[];
}

why: {
  h2:    string;
  cards: {
    title: string;
    text:  string;
  }[];
}

faq: {
  sectionTitle: string;
  items: {
    q: string;
    a: string;
  }[];
}
```

---

### Приклад використання ProductLayout

**Сторінка без extra-слотів (наприклад, shuz):**
```astro
---
import ProductLayout from '../../layouts/ProductLayout.astro';
import { SITE_CANONICAL } from '../../config';

const page = {
  section:     'produktsiia',
  title:       'Виготовлення ШУЗ на замовлення | elektroschit.com.ua',
  description: 'Щити керування засувками для трубопровідних систем. Гарантія 12 міс. Київ.',
  canonical:   `${SITE_CANONICAL}/posluhy-ta-produktsiia/shuz/`,
  crumbs: [
    { label: 'Головна',   href: '/' },
    { label: 'Продукція', href: '/posluhy-ta-produktsiia/' },
    { label: 'Щити керування засувками (ШУЗ)' },
  ],
};

const hero = {
  tag:   'Виготовлення · Київ та область',
  h1:    'Виготовлення щитів керування засувками (ШУЗ) на замовлення',
  lead:  'Лід-текст...',
  badges: [
    '<strong>від 2 тижнів</strong> — виготовлення',
    '<strong>12 міс.</strong> — гарантія',
  ],
  collage: [
    { src: '/images/shuz/shuz-...-c1.jpg', alt: '...' },
    { src: '/images/shuz/shuz-...-c2.jpg', alt: '...' },
    { src: '/images/shuz/shuz-...-c3.jpg', alt: '...' },
    { src: '/images/shuz/shuz-...-c4.jpg', alt: '...' },
  ],
};
// ... gallery, objects, specs, brands, steps, why, faq, contactTitle
---
<ProductLayout
  {page}
  slug="shuz"
  {hero}
  {gallery}
  {objects}
  {specs}
  {brands}
  {steps}
  {why}
  {faq}
  contactTitle="Готові обговорити ваше замовлення — ШУЗ"
/>
```

**Сторінка з extra1 (наприклад, dvyhuny):**
```astro
<ProductLayout {page} slug="dvyhuny" {hero} {gallery} {objects}
  {specs} {brands} {steps} {why} {faq}
  contactTitle="Готові обговорити ваше замовлення — щити керування двигунами"
>
  <section slot="extra1" class="em-section">
    <!-- Унікальний блок, білий фон, між Застосування і Характеристики -->
  </section>
</ProductLayout>
```

**Сторінка з extra1 + extra2 (тільки plk):**
```astro
<ProductLayout {page} slug="plk" {hero} {gallery} {objects}
  {specs} {steps} {why} {faq}
  contactTitle="Готові обговорити ваше замовлення — програмування ПЛК"
>
  <!-- brands не передається → буде <hr> замість блоку компонентів -->
  <section slot="extra1" class="em-section">
    <!-- Білий блок -->
  </section>
  <div slot="extra2" class="em-section-alt">
    <div class="em-section-alt-inner">
      <!-- Зелений блок -->
    </div>
  </div>
</ProductLayout>
```

---

### Залежності ProductLayout

Імпортує:
- `./BaseLayout.astro`
- `../components/FaqAccordion.astro`
- `../components/AlsoMake.astro`
- `../components/ContactBlock.astro`
- `../components/Lightbox.astro`
- `../config.ts` → `PHONE`, `PHONE_DISPLAY`

ProductLayout сам підключає `em-hrshch.css` і `em-site.js` — сторінкам не потрібно робити це окремо.

---

<a name="звязок-між-ними"></a>
## 3. Зв'язок між BaseLayout і ProductLayout

```
Сторінка (.astro)
  └─ ProductLayout         ← передає page, slug, hero, gallery...
       └─ BaseLayout       ← передає page (title, description, canonical, crumbs)
            ├─ <head>      ← CSS, шрифти, GTM, OG, JSON-LD
            ├─ Header
            ├─ Breadcrumbs
            ├─ <slot />    ← сюди вставляється весь вміст ProductLayout
            └─ Footer
```

Тобто **кожна сторінка продукту** пише тільки дані. ProductLayout будує структуру блоків. BaseLayout ставить `<head>`, `<header>`, `<footer>`, SEO і аналітику.

**Для сторінок, що не є продуктовими** (`index`, `kontakty`, `pro-nas`, `vykonani-roboty/*`) — використовується BaseLayout напряму, без ProductLayout.

---

<a name="довідник-значень-section"></a>
## 4. Довідник значень `section`

Значення `page.section` визначає, яка вкладка підсвічується в шапці.

| `section` | Підсвічується | Хто передає |
|---|---|---|
| `'produktsiia'` | Продукція | всі сторінки posluhy-ta-produktsiia/ |
| `'posluhy'` | Послуги | — (не використовується поки) |
| `'vykonani-roboty'` | Виконані роботи | vykonani-roboty/ |
| `'pro-nas'` | Про нас | pro-nas.astro |
| `'kontakty'` | Контакти | kontakty.astro |
| `''` | Нічого | index.astro (головна) |

---

*elektroschit.com.ua | layouts-docs v1.0 (BaseLayout + ProductLayout) | 2026-07-21*
