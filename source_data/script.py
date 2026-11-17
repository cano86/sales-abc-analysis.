import pandas as pd
import os
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# 1. Настройка путей и имён файлов
# ---------------------------------------------------------
folder_path = r'./source_data'  # папка с исходниками (лежит рядом со скриптом)
files = {
    'sales': 'sales.csv',      # файл с продажами
    'returns': 'returns.csv',  # файл с возвратами
    'stock': 'stock.csv'       # файл с остатками
}

# ---------------------------------------------------------
# 2. Загрузка данных с меткой источника
# ---------------------------------------------------------


def load_with_source(file_name, source_label):
    """Загружает CSV и добавляет столбец Источник.
    Основной вариант — запятая; если файл оказался с другим разделителем
    (вся строка склеилась в один столбец) — пробуем точку с запятой."""
    path = os.path.join(folder_path, file_name)
    df = pd.read_csv(path, sep=',', encoding='utf-8-sig')

    # Страховка: если получился один столбец — значит, разделитель не запятая
    if df.shape[1] == 1:
        df = pd.read_csv(path, sep=';', encoding='utf-8-sig')

    df['Источник'] = source_label
    return df


df_sales = load_with_source(files['sales'], 'Продажи')
df_returns = load_with_source(files['returns'], 'Возвраты')
df_stock = load_with_source(files['stock'], 'Остатки')

# ---------------------------------------------------------
# 3. Объединение всех таблиц в одну
# ---------------------------------------------------------
df_all = pd.concat([df_sales, df_returns, df_stock], ignore_index=True)

# Диагностика: смотрим реальные имена столбцов (можно закомментировать потом)
print("Столбцы после объединения:", df_all.columns.tolist())

# ---------------------------------------------------------
# 4. Проверка схемы (data contract): скрипт останавливается
#    с понятным сообщением, если структура файлов изменилась
# ---------------------------------------------------------
required = ['Выручка_руб', 'Сумма_возврата_руб', 'Регион']
missing = [col for col in required if col not in df_all.columns]
if missing:
    raise SystemExit(
        f"Не хватает столбцов: {missing}. "
        f"Реальные столбцы: {df_all.columns.tolist()}"
    )

# Заполняем пропуски нулями: в файле продаж нет колонок возвратов и остатков
# (после concat там будут NaN), и наоборот
numeric_cols = ['Продажи_шт', 'Выручка_руб', 'Возвраты_шт',
                'Сумма_возврата_руб', 'Остаток_шт', 'Цена_закупочная_руб']
for col in numeric_cols:
    if col in df_all.columns:
        df_all[col] = df_all[col].fillna(0)

# ---------------------------------------------------------
# 5. Расчёт чистой выручки
# ---------------------------------------------------------


def calc_net_revenue(row):
    if row['Источник'] == 'Продажи':
        return row['Выручка_руб']
    elif row['Источник'] == 'Возвраты':
        return -row['Сумма_возврата_руб']
    else:
        return 0


df_all['Чистая_выручка'] = df_all.apply(calc_net_revenue, axis=1)


# ---------------------------------------------------------
# 7. Итоговые метрики (KPI)
# ---------------------------------------------------------
total_revenue = df_all[df_all['Источник'] == 'Продажи']['Выручка_руб'].sum()
total_returns = df_all[df_all['Источник'] ==
                       'Возвраты']['Сумма_возврата_руб'].sum()
net_revenue_total = df_all['Чистая_выручка'].sum()
avg_return_share = (total_returns / total_revenue *
                    100) if total_revenue > 0 else 0

print(f"\nВыручка: {total_revenue:,.2f} ₽")
print(f"Возвраты: {total_returns:,.2f} ₽")
print(f"Чистая выручка: {net_revenue_total:,.2f} ₽")
print(f"Средняя доля возвратов: {avg_return_share:.2f}%\n")

# ---------------------------------------------------------
# 8. Топ-5 проблемных городов по доле возвратов
# ---------------------------------------------------------
# ---------------------------------------------------------
# 6. Доля возвратов: агрегированная метрика на уровне города.
#    Построчная доля здесь не имеет смысла: продажи и возвраты
#    живут в разных строках объединённой таблицы.
# ---------------------------------------------------------
# (столбец 'Доля_возвратов_%' построчно больше не нужен)

# ---------------------------------------------------------
# 8. Метрики по городам: считаем долю ИЗ СУММ
# ---------------------------------------------------------
city_metrics = (
    df_all
    .groupby('Регион')
    .agg(
        Выручка_сум=('Выручка_руб', 'sum'),
        Возвраты_сум=('Сумма_возврата_руб', 'sum'),
    )
    .reset_index()
)

# Доля возвратов = возвраты города / выручка города * 100.
# Защита от деления на 0: если выручки нет — доля 0.
city_metrics['Доля_возвратов_%'] = 0.0
city_mask = city_metrics['Выручка_сум'] > 0
city_metrics.loc[city_mask, 'Доля_возвратов_%'] = (
    city_metrics.loc[city_mask, 'Возвраты_сум'] /
    city_metrics.loc[city_mask, 'Выручка_сум'] * 100
)

top_5_cities = (
    city_metrics
    .sort_values(by='Доля_возвратов_%', ascending=False)
    .head(5)
)


print("Топ-5 проблемных городов:")
print(top_5_cities.to_string(index=False))


# ---------------------------------------------------------
# 9. ABC-анализ по артикулам (по выручке)
# ---------------------------------------------------------
# Шаг 1: суммируем выручку по каждому артикулу
abc_data = (df_all[df_all['Источник'] == 'Продажи']
            .groupby('Артикул')
            .agg(Выручка=('Выручка_руб', 'sum'))
            .reset_index()
            )

# Шаг 2: сортируем от самого прибыльного к наименее прибыльному
abc_data = abc_data.sort_values(by='Выручка', ascending=False)

# Шаг 3: считаем долю каждого артикула и накопленную долю
total = abc_data['Выручка'].sum()
abc_data['доля_%'] = abc_data['Выручка'] / total * 100
abc_data['Накопленнная_доля %'] = abc_data['доля_%'].cumsum()
# Шаг 4: назначаем группы по накопленной доле
# 0–80% = A, 80–95% = B, 95–100% = C


def assign_abc(cum_share):
    if cum_share > 80:
        return 'A'
    elif cum_share <= 95:
        return 'B'
    else:
        return 'C'


abc_data['Группа'] = abc_data['Накопленнная_доля %'].apply(assign_abc)

print('\nABC-анализ:')
print(abc_data.to_string(index=False))

# Сводка по группам: сколько артикулов и сколько денег в каждой
group_summary = (
    abc_data
    .groupby('Группа')
    .agg(Артикулов=('Артикул', 'count'),
         Суммарная_выручка=('Выручка', 'sum'))
    .reset_index()
)
group_summary['Доля_выручки_%'] = group_summary['Суммарная_выручка'] / total * 100

print("\nСводка по группам:")
print(group_summary.to_string(index=False))

# Добавляем группу ABC обратно в общую таблицу (для отчёта)
df_all = df_all.merge(
    abc_data[['Артикул', 'Группа']], on='Артикул', how='left')

# ---------------------------------------------------------
# 10. ABC-анализ по марже (по прибыли)
# ---------------------------------------------------------
# Шаг 1: считаем маржу (только для строк продаж)
# Защита от деления/ошибок: если цена или количество пустые — маржа 0
df_all['Маржа_руб'] = 0.0
mask_sales = df_all['Источник'] == 'Продажи'
df_all.loc[mask_sales, 'Маржа_руб'] = (
    df_all.loc[mask_sales, 'Выручка_руб']
    - (df_all.loc[mask_sales, 'Цена_закупочная_руб']
       * df_all.loc[mask_sales, 'Продажи_шт'])
)
# Шаг 2: сводим маржу по артикулам
abc_data_margin = (
    df_all[df_all['Источник'] == 'Продажи']
    .groupby('Артикул')
    .agg(Маржа=('Маржа_руб', 'sum'))
    .reset_index()
)
# Шаг 3: сортируем по марже от большего к меньшему
abc_data_margin = abc_data_margin.sort_values(by='Маржа', ascending=False)
# Шаг 4: доля и накопительная доля
total_margin = abc_data_margin['Маржа'].sum()
abc_data_margin['Доля_%'] = abc_data_margin['Маржа'] / total_margin * 100
abc_data_margin['Накопленная_доля_%'] = abc_data_margin['Доля_%'].cumsum()

# Шаг 5: раздаём группы A/B/C


def assign_abc(cum_share):
    if cum_share <= 80:
        return 'A'
    elif cum_share <= 95:
        return 'B'
    else:
        return 'C'


abc_data_margin['Группа_маржа'] = abc_data_margin['Накопленная_доля_%'].apply(
    assign_abc)

print("\nABC-анализ по марже:")
print(abc_data_margin.to_string(index=False))

# Сводка по группам
group_summary_margin = (
    abc_data_margin
    .groupby('Группа_маржа')
    .agg(Артикулов=('Артикул', 'count'),
         Суммарная_маржа=('Маржа', 'sum'))
    .reset_index()
)
group_summary_margin['Доля_маржи_%'] = group_summary_margin['Суммарная_маржа'] / \
    total_margin * 100
print("\nСводка по группам (маржа):")
print(group_summary_margin.to_string(index=False))

# Добавляем группу по марже обратно в основную таблицу
df_all = df_all.merge(
    abc_data_margin[['Артикул', 'Группа_маржа']],
    on='Артикул',
    how='left'
)
# ---------------------------------------------------------
# 11. Сохранение результата в Excel (2 листа)
# ---------------------------------------------------------
output_file = 'Report_Python_v1.xlsx'
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    df_all.to_excel(writer, sheet_name='Данные', index=False)
    top_5_cities.to_excel(writer, sheet_name='Топ-5 городов', index=False)

print(f"\nОтчёт сохранён в файл: {output_file}")

# ---------------------------------------------------------
# 12. Диаграмма Парето по выручке
# ---------------------------------------------------------


# если квадратики останутся — см. ниже
plt.rcParams['font.family'] = 'DejaVu Sans'

fig, ax1 = plt.subplots(figsize=(10, 5))

# Столбики: выручка по артикулам (abc_data уже отсортирован)
ax1.bar(abc_data['Артикул'], abc_data['Выручка'], color='#4C72B0')
ax1.set_ylabel('Выручка, ₽')
ax1.set_xlabel('Артикул')

# Линия: накопленная доля (правая ось в процентах)
ax2 = ax1.twinx()
ax2.plot(abc_data['Артикул'], abc_data['Накопленнная_доля %'],
         color='#C44E52', marker='o')
ax2.set_ylabel('Накопленная доля, %')
ax2.set_ylim(0, 105)

# Пунктир на 80% — граница группы A
ax2.axhline(80, color='gray', linestyle='--', linewidth=1)
ax2.annotate('Граница группы A (80%)', xy=(0.3, 80), xytext=(0.3, 84),
             fontsize=9, color='gray')

plt.title('Парето-анализ выручки по артикулам')
plt.tight_layout()
plt.savefig('Pareto_chart.png', dpi=150)
print('График сохранен: Pareto_chart.png')
