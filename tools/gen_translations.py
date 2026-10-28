#!/usr/bin/env python3
"""Write strings.json and translations/{en,uk}.json from one table.

English and Ukrainian sit side by side here, so a string cannot be added to one
language and forgotten in the other, and strings.json and en.json stay equal.
A test fails if the committed files fall behind this script.

    .venv/bin/python tools/gen_translations.py            # rewrite the three files
    .venv/bin/python tools/gen_translations.py --check    # exit 1 if any is stale
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PACKAGE = ROOT / "custom_components" / "olimpia_sherpa_modbus"

from custom_components.olimpia_sherpa_modbus.registers import WRITE_SPECS  # noqa: E402

# key: (en, uk[, {state: (en, uk)}])
SENSOR = {
    "water_in": ("Water in", "Вода вхід"),
    "water_out": ("Water out", "Вода вихід"),
    "dhw_tank": ("DHW tank", "Бак ГВП"),
    "outdoor_air": ("Outdoor air", "Зовнішнє повітря"),
    "dhw_compressor_temp": ("DHW compressor", "Компресор ГВП"),
    "dhw_condenser_temp": ("DHW condenser", "Конденсатор ГВП"),
    "dhw_evaporator_temp": ("DHW evaporator", "Випарник ГВП"),
    "solar_temp": ("Solar thermal", "Сонячний колектор"),
    "mode": ("Mode", "Режим", {
        "standby": ("Standby", "Очікування"),
        "cooling": ("Cooling", "Охолодження"),
        "heating": ("Heating", "Опалення"),
        "domestic_hot_water": ("Domestic hot water", "Гаряча вода"),
        "anti_legionella": ("Anti-legionella", "Антилегіонела"),
    }),
    "error_code": ("Error code", "Код помилки"),
    "override_code": ("Override code", "Код особливого стану"),
    "pump_step": ("Pump speed step", "Ступінь швидкості насоса"),
    "pump_duty": ("Pump duty", "ШІМ насоса"),
    "water_target": ("Water target (calculated)", "Цільова температура води (розрахункова)"),
    "water_delta": ("Water delta", "Різниця температур води"),
    "compressor_rate": ("Compressor rate", "Темп лічильника компресора"),
    "compressor_seconds": ("Compressor runtime (s)", "Напрацювання компресора (с)"),
    "pump_seconds": ("Pump runtime (s)", "Напрацювання насоса (с)"),
    "filter_seconds": ("Filter runtime (s)", "Напрацювання фільтра (с)"),
    "dhw_compressor_seconds": ("DHW compressor runtime (s)", "Напрацювання компресора ГВП (с)"),
    "dhw_pump_seconds": ("DHW pump runtime (s)", "Напрацювання насоса ГВП (с)"),
    "smart_grid_1_seconds": ("Smart Grid input 1 time", "Час входу Smart Grid 1"),
    "smart_grid_2_seconds": ("Smart Grid input 2 time", "Час входу Smart Grid 2"),
    "compressor_hours": ("Compressor runtime", "Напрацювання компресора"),
    "pump_hours": ("Pump runtime", "Напрацювання насоса"),
    "cooling_setpoint": ("Cooling setpoint", "Уставка охолодження"),
    "cooling_eco_setpoint": ("Cooling setpoint (eco)", "Уставка охолодження (еко)"),
    "heating_setpoint": ("Heating setpoint", "Уставка опалення"),
    "heating_eco_setpoint": ("Heating setpoint (eco)", "Уставка опалення (еко)"),
    "dhw_setpoint": ("DHW setpoint", "Уставка ГВП"),
    "legionella_setpoint": ("Anti-legionella setpoint", "Уставка антилегіонели"),
    "dhw_hysteresis": ("DHW hysteresis", "Гістерезис ГВП"),
    "legionella_start_minutes": ("Anti-legionella start (minutes)", "Початок антилегіонели (хв)"),
    "legionella_start": ("Anti-legionella start", "Початок антилегіонели"),
    "inputs": ("Input word", "Слово входів"),
    "status": ("Status word", "Слово стану"),
    "outputs": ("Output word", "Слово виходів"),
    "override": ("Override word", "Слово особливих станів"),
    "alarm_1": ("Alarm word 1", "Слово аварій 1"),
    "alarm_2": ("Alarm word 2", "Слово аварій 2"),
    "identify_code": ("Identify code", "Код ідентифікації"),
    "remote_controls": ("Remote control", "Дистанційне керування", {
        "display": ("Display only", "Лише дисплей"),
        "serial": ("Serial port", "Послідовний порт"),
        "contacts": ("Free contacts", "Сухі контакти"),
    }),
    "dhw_source": ("DHW request source", "Джерело запиту ГВП", {
        "disabled": ("Disabled", "Вимкнено"),
        "contact": ("DHW contact", "Контакт ГВП"),
        "sensor": ("Tank sensor T3", "Датчик бака T3"),
    }),
    "legionella_mode": ("Anti-legionella mode", "Режим антилегіонели", {
        "heat_pump_and_k5": ("Heat pump and K5 heater", "Тепловий насос і нагрівач K5"),
        "k5_only": ("K5 heater only", "Лише нагрівач K5"),
        "electric_heaters": ("Electric heaters EH1/EH2", "Електронагрівачі EH1/EH2"),
    }),
    "aux_heaters": ("Auxiliary electric heaters", "Додаткові електронагрівачі", {
        "none": ("None", "Немає"),
        "one_backup": ("One, backup", "Один, резервний"),
        "two_backup": ("Two, backup", "Два, резервні"),
        "one_low_temperature_start": ("One, low-temperature start", "Один, холодний пуск"),
        "two_low_temperature_start": ("Two, low-temperature start", "Два, холодний пуск"),
    }),
    "dhw_mode": ("DHW mode", "Режим ГВП", {
        "automatic": ("Automatic", "Автоматичний"),
        "dhw_module_only": ("DHW module only", "Лише модуль ГВП"),
        "heat_pump_only": ("Heat pump only", "Лише тепловий насос"),
    }),
    "smart_grid": ("Smart Grid / PV input", "Вхід Smart Grid / PV", {
        "disabled": ("Disabled", "Вимкнено"),
        "photovoltaic": ("Photovoltaic", "Фотоелектрика"),
    }),
    "boiler_threshold": ("External boiler threshold", "Поріг зовнішнього котла"),
    "freeze_protection": ("Freeze protection", "Захист від замерзання"),
    "legionella_interval": ("Anti-legionella interval", "Інтервал антилегіонели"),
    "legionella_duration": ("Anti-legionella duration", "Тривалість антилегіонели"),
    "water_setpoint_correction": ("Water setpoint correction", "Корекція уставки води"),
    "cooling_curve_max_water": ("Cooling curve: max water", "Крива охолодження: макс. вода"),
    "cooling_curve_max_water_outdoor": ("Cooling curve: outdoor at max water", "Крива охолодження: зовнішня при макс. воді"),
    "cooling_curve_min_water": ("Cooling curve: min water", "Крива охолодження: мін. вода"),
    "cooling_curve_min_water_outdoor": ("Cooling curve: outdoor at min water", "Крива охолодження: зовнішня при мін. воді"),
    "heating_curve_max_water": ("Heating curve: max water", "Крива опалення: макс. вода"),
    "heating_curve_max_water_outdoor": ("Heating curve: outdoor at max water", "Крива опалення: зовнішня при макс. воді"),
    "heating_curve_min_water": ("Heating curve: min water", "Крива опалення: мін. вода"),
    "heating_curve_min_water_outdoor": ("Heating curve: outdoor at min water", "Крива опалення: зовнішня при мін. воді"),
    "last_successful_read": ("Last successful read", "Останнє успішне читання"),
    "read_failures": ("Read failures", "Помилки читання"),
}
BINARY = {
    "in_flow": ("Water flow", "Потік води"),
    "in_ta": ("Thermostat demand", "Запит термостата"),
    "mode_cooling": ("Cooling", "Охолодження"),
    "mode_heating": ("Heating", "Опалення"),
    "mode_dhw": ("DHW cycle", "Цикл ГВП"),
    "mode_legionella": ("Anti-legionella cycle", "Цикл антилегіонели"),
    "mode_night": ("Night mode", "Нічний режим"),
    "mode_pending": ("Mode pending", "Режим очікує"),
    "out_pump": ("Circulation pump", "Циркуляційний насос"),
    "out_dhw_pump": ("DHW pump", "Насос ГВП"),
    "out_eh1": ("Electric heater 1", "Електронагрівач 1"),
    "out_eh2": ("Electric heater 2", "Електронагрівач 2"),
    "out_3way": ("Three-way valve", "Триходовий клапан"),
    "out_k5": ("DHW tank heater (K5)", "Нагрівач бака ГВП (K5)"),
    "out_boiler": ("External boiler call", "Запит зовнішнього котла"),
    "out_alarm": ("Alarm relay", "Реле аварії"),
    "defrost": ("Defrost", "Розморожування"),
    "power": ("Power", "Робота"),
    "error": ("Error", "Аварія"),
    "warning": ("Warning", "Попередження"),
    "compressor_running": ("Compressor running", "Компресор працює"),
    "cooling_curve_enabled": ("Cooling climatic curve", "Кліматична крива охолодження"),
    "heating_curve_enabled": ("Heating climatic curve", "Кліматична крива опалення"),
    "external_boiler_enabled": ("External boiler enabled", "Зовнішній котел дозволено"),
}

# The writable keys come from the register map; their names are the sensors'.
NUMBER_KEYS = [k for k, spec in WRITE_SPECS.items() if spec.platform == "number"]
SWITCH_KEYS = [k for k, spec in WRITE_SPECS.items() if spec.platform == "switch"]


def writable_name(key, i):
    spec = SENSOR.get(key) or BINARY.get(key)
    return spec[i]


#: The climate entity, and the names of its own attributes.
CLIMATE = {"heat_pump": ("Heat pump", "Тепловий насос", {
    "water_target": ("Water target (calculated)", "Цільова температура води (розрахункова)"),
    "water_target_source": ("Water target from", "Джерело цільової температури"),
    "water_in": ("Water in", "Вода вхід"),
    "water_out": ("Water out", "Вода вихід"),
    "outdoor_air": ("Outdoor air", "Зовнішнє повітря"),
    "dhw_in_progress": ("Hot water cycle", "Цикл ГВП"),
    "night": ("Night mode", "Нічний режим"),
    "remote_controls": ("Remote control", "Дистанційне керування"),
    "heating_curve": ("Heating curve", "Крива опалення"),
    "cooling_curve": ("Cooling curve", "Крива охолодження"),
    "operating_mode": ("Operating mode", "Режим роботи"),
    "mode_control": ("Mode control", "Керування режимом"),
})}

#: Mode control's entities (opt-in): the select, the ECO and night switches, and
#: the hot water (always there; its on/off needs mode control).
OPERATING_MODE = {"name": ("Operating mode", "Режим роботи"), "state": {
    "standby": ("Standby", "Очікування"),
    "dhw_only": ("DHW only", "Лише ГВП"),
    "heating": ("Heating", "Опалення"),
    "cooling": ("Cooling", "Охолодження"),
}}
MODE_SWITCHES = {
    "eco": ("ECO", "ECO"),
    "night": ("Night mode", "Нічний режим"),
}
HOT_WATER = ("Hot water", "Гаряча вода")


def entities(lang):
    i = 0 if lang == "en" else 1
    out = {"sensor": {}, "binary_sensor": {}}
    out["climate"] = {key: {"name": spec[i], "state_attributes": {
        attr: {"name": names[i]} for attr, names in spec[2].items()}} for key, spec in CLIMATE.items()}
    out["number"] = {k: {"name": writable_name(k, i)} for k in NUMBER_KEYS}
    out["switch"] = {k: {"name": writable_name(k, i)} for k in SWITCH_KEYS}
    out["switch"].update({k: {"name": names[i]} for k, names in MODE_SWITCHES.items()})
    out["select"] = {"operating_mode": {
        "name": OPERATING_MODE["name"][i],
        "state": {k: names[i] for k, names in OPERATING_MODE["state"].items()}}}
    out["water_heater"] = {"hot_water": {"name": HOT_WATER[i]}}
    for key, spec in SENSOR.items():
        item = {"name": spec[i]}
        if len(spec) > 2:
            item["state"] = {state: names[i] for state, names in spec[2].items()}
        out["sensor"][key] = item
    for key, spec in BINARY.items():
        out["binary_sensor"][key] = {"name": spec[i]}
    return out

T = {  # (en, uk)
 "allow_writes": ("Allow writes to verified parameters", "Дозволити запис перевірених параметрів"),
 "allow_writes_desc": ("Off by default. When on, a setpoint becomes writable only after the write check (the Verify write action) has passed for it on this unit. The unit's own controller still runs the plant.",
                       "Типово вимкнено. Коли увімкнено, уставка стає доступною для запису лише після того, як для неї на цьому агрегаті пройде перевірка запису (дія «Перевірити запис»). Установкою й надалі керує власний контролер агрегату."),
 "svc_name": ("Verify write", "Перевірити запис"),
 "svc_desc": ("Checks that one parameter can be written on this unit: writes its own value back, then one step away (held, then read again), and always restores the original. Needs 'Allow writes' on. Admin only.",
              "Перевіряє, чи можна записати параметр на цьому агрегаті: записує поточне значення, потім на один крок інше (з витримкою та повторним читанням) і завжди повертає початкове. Потрібно увімкнути «Дозволити запис». Лише для адміністратора."),
 "svc_entry": ("Sherpa", "Sherpa"),
 "svc_entry_desc": ("Which unit, if more than one is configured.", "Який агрегат, якщо їх налаштовано кілька."),
 "svc_register": ("Parameter", "Параметр"),
 "svc_register_desc": ("The parameter to check.", "Параметр для перевірки."),
 "svc_hold": ("Hold", "Витримка"),
 "rr_name": ("Read registers", "Прочитати регістри"),
 "rr_desc": ("Reads raw holding registers through the integration's own connection, for research and support. Without an address it reads every register the unit is known to answer. Only reads, never writes. Admin only.",
             "Читає сирі регістри зберігання через власне підключення інтеграції — для досліджень і підтримки. Без адреси читає всі регістри, на які агрегат відповідає. Лише читає, ніколи не записує. Лише для адміністратора."),
 "rr_address": ("Address", "Адреса"),
 "rr_address_desc": ("First register to read. Leave empty for a snapshot of every answering register.", "Перший регістр для читання. Залиште порожнім для знімка всіх регістрів, що відповідають."),
 "rr_count": ("Count", "Кількість"),
 "rr_count_desc": ("How many registers from the address (at most 125).", "Скільки регістрів від адреси (не більше 125)."),
 "mc_name": ("Write mode command", "Записати команду режиму"),
 "mc_desc": ("Research: writes the mode command (register 106), then reads it back with the unit's status, outputs and alarms. The unit acts on it only with ADDR220 = 1, and then raises E09 unless it is written at least every 255 s. Needs 'Allow writes'. Refused while Mode control is on and ADDR220 = 1: turn Mode control off first. Admin only.",
             "Дослідження: записує команду режиму (регістр 106), потім читає її назад разом зі статусом, виходами й аваріями агрегату. Агрегат виконує її лише за ADDR220 = 1, і тоді видає E09, якщо її не записувати щонайменше раз на 255 с. Потрібно увімкнути «Дозволити запис». Відхиляється, поки увімкнено «Керування режимом» і ADDR220 = 1: спершу вимкніть «Керування режимом». Лише для адміністратора."),
 "mc_value": ("Value", "Значення"),
 "mc_value_desc": ("Bits: 1 standby, 2 ECO, 4 cooling, 8 heating, 16 night. 0 is DHW only. Heating and cooling together are refused.",
                   "Біти: 1 очікування, 2 ECO, 4 охолодження, 8 опалення, 16 нічний режим. 0 — лише ГВП. Опалення й охолодження разом не приймаються."),
 "x_invalid_mode_command": ("Mode command {value} sets heating and cooling at once.", "Команда режиму {value} задає опалення й охолодження одночасно."),
 "x_mode_control_inactive": ("Mode control is not active: set ADDR220 to 1 on the panel first, with Mode control on.", "Керування режимом неактивне: спершу встановіть на панелі ADDR220 = 1 і ввімкніть «Керування режимом»."),
 "x_mode_control_active": ("Mode control is running and writes register 106 itself. Turn Mode control off in the options before using this action.", "Керування режимом працює й саме записує регістр 106. Вимкніть «Керування режимом» у параметрах, перш ніж користуватися цією дією."),
 "x_read_failed": ("No answer from the Sherpa while reading: {error}", "Немає відповіді від Sherpa під час читання: {error}"),
 "svc_hold_desc": ("Seconds to hold the test value before reading it again.", "Скільки секунд тримати тестове значення перед повторним читанням."),
 "x_writes_disabled": ("Writes are off for this Sherpa. Turn on 'Allow writes' in its options first.", "Запис для цього Sherpa вимкнено. Спершу увімкніть «Дозволити запис» у його параметрах."),
 "x_not_writable": ("{key} is not writable: its write check has not passed on this unit.", "{key} недоступний для запису: перевірка запису для нього на цьому агрегаті не пройшла."),
 "x_not_a_candidate": ("{key} is not a parameter this integration writes.", "{key} не належить до параметрів, які записує ця інтеграція."),
 "x_out_of_range": ("{value} is outside {minimum} to {maximum} in steps of {step} for {key}.", "{value} поза межами {minimum}..{maximum} з кроком {step} для {key}."),
 "x_rate_limited": ("Too many writes: {key} can be written once every {interval} s, and the unit {daily} times a day.", "Забагато записів: {key} можна записувати раз на {interval} с, а агрегат — {daily} разів на добу."),
 "x_not_applied": ("The Sherpa did not apply {key}: wrote {expected}, it reads {actual}.", "Sherpa не застосував {key}: записано {expected}, читається {actual}."),
 "x_write_failed": ("No answer from the Sherpa while writing: {error}", "Немає відповіді від Sherpa під час запису: {error}"),
 "x_write_refused": ("The Sherpa refused the write (Modbus exception {code}).", "Sherpa відхилив запис (виняток Modbus {code})."),
 "x_restore_failed": ("Could not set {key} (register {address}) back to {value}. Set it on the unit's panel.", "Не вдалося повернути {key} (регістр {address}) до {value}. Встановіть його на панелі агрегату."),
 "x_choose_entry": ("Choose which Sherpa: none or more than one is loaded.", "Оберіть, який Sherpa: завантажено жодного або кілька."),
 "i_restore_title": ("A Sherpa parameter was left changed", "Параметр Sherpa залишився зміненим"),
 "i_restore_desc": ("The write check could not put {key} (register {address}) back to {value}. Set it on the unit's SERVICE screen, then dismiss this.",
                    "Перевірка запису не змогла повернути {key} (регістр {address}) до {value}. Встановіть його на екрані SERVICE агрегату, потім закрийте це повідомлення."),
 "i_unmanaged_title": ("The Sherpa takes commands over RS-485, but nothing keeps it fed", "Sherpa приймає команди через RS-485, але ніхто його не «годує»"),
 "i_unmanaged_desc": ("The unit has ADDR220 = 1 (serial control), and Home Assistant is not writing its mode: Mode control or Allow writes is off. The unit raises E09 every 255 s and stops the pump for about 3 s each time. Set ADDR220 = 0 on the panel, or turn on Allow writes and Mode control in the options.",
                      "В агрегаті ADDR220 = 1 (керування через послідовний порт), а Home Assistant не записує його режим: вимкнено «Керування режимом» або «Дозволити запис». Агрегат видає E09 кожні 255 с і щоразу зупиняє насос приблизно на 3 с. Встановіть на панелі ADDR220 = 0 або ввімкніть у параметрах «Дозволити запис» і «Керування режимом»."),
 "i_keepalive_title": ("Home Assistant is not writing the Sherpa's mode", "Home Assistant не записує режим Sherpa"),
 "i_keepalive_desc": ("The mode has not been written for {seconds} s. The unit pulses its alarm relay (E09) and stops the pump for about 3 s every 255 s. Check the RS-485 link. If it lasts, set ADDR220 = 0 on the panel.",
                      "Режим не записувався {seconds} с. Агрегат кожні 255 с спрацьовує реле аварії (E09) і зупиняє насос приблизно на 3 с. Перевірте з'єднання RS-485. Якщо це триває, встановіть на панелі ADDR220 = 0."),
 "i_not_applied_title": ("The Sherpa does not hold the mode we write", "Sherpa не тримає режим, який ми записуємо"),
 "i_not_applied_desc": ("Register 106 reads back something other than what Home Assistant wrote, several times in a row. Another master may be writing it, or the unit refuses it. Check the bus; if it lasts, set ADDR220 = 0 on the panel.",
                        "Регістр 106 читається не таким, як його записав Home Assistant, кілька разів поспіль. Його може записувати інший ведучий, або агрегат його відхиляє. Перевірте шину; якщо це триває, встановіть на панелі ADDR220 = 0."),
 "menu_title": ("How is the Sherpa connected?", "Як підключено Sherpa?"),
 "menu_desc": ("The integration reads the unit. Writes stay off unless you turn them on in its options, and even then only parameters the write check has verified on this unit can be changed. RS-485 allows one master, so stop anything else that polls the Sherpa (an old `modbus:` configuration, another controller) before adding it.",
               "Інтеграція читає агрегат. Запис вимкнено, доки ви не увімкнете його в параметрах, і навіть тоді змінювати можна лише параметри, які пройшли перевірку запису на цьому агрегаті. RS-485 допускає лише одного ведучого, тож перед додаванням зупиніть усе інше, що опитує Sherpa (стару конфігурацію `modbus:`, інший контролер)."),
 "serial": ("USB / RS-485 adapter", "USB / RS-485 адаптер"),
 "network": ("Network gateway", "Мережевий шлюз"),
 "serial_title": ("RS-485 adapter", "Адаптер RS-485"),
 "serial_desc": ("Terminal AB on the indoor unit, 8N1. Prefer a /dev/serial/by-id path: it survives reboots and replugging.",
                 "Клеми AB внутрішнього блока, 8N1. Обирайте шлях /dev/serial/by-id: він не змінюється після перезавантаження чи перепідключення."),
 "network_title": ("Network gateway", "Мережевий шлюз"),
 "network_desc": ("A gateway wired to terminal AB on the indoor unit.", "Шлюз, підключений до клем AB внутрішнього блока."),
 "serial_port": ("Serial port", "Послідовний порт"),
 "baudrate": ("Baud rate", "Швидкість"),
 "slave": ("Modbus address", "Адреса Modbus"),
 "slave_desc": ("Parameter ADDR247 on the unit's SERVICE screen (factory default 1).", "Параметр ADDR247 на екрані SERVICE агрегату (заводське значення 1)."),
 "prefix": ("Entity ID prefix", "Префікс ID сутностей"),
 "prefix_desc": ("Every entity id starts with it, e.g. sensor.sherpa_water_in. Keep \"sherpa\" to take over the entity ids, history and statistics of an existing YAML setup.",
                 "З нього починається ID кожної сутності, наприклад sensor.sherpa_water_in. Залиште «sherpa», щоб успадкувати ID, історію та статистику наявної YAML-конфігурації."),
 "host": ("Host", "Хост"),
 "port": ("Port", "Порт"),
 "transport": ("Gateway type", "Тип шлюзу"),
 "reconf_title": ("Change the connection", "Змінити підключення"),
 "reconf_desc": ("Same unit, different link. Entity ids and history are kept.", "Той самий агрегат, інше підключення. ID сутностей та історія зберігаються."),
 "e_cannot": ("No answer. Check the port or address, the wiring on terminals AB, and that nothing else is polling the bus.", "Немає відповіді. Перевірте порт або адресу, підключення клем AB і те, що шину більше ніхто не опитує."),
 "e_not": ("Something answered, but not with a Sherpa's identity registers. Check the Modbus address.", "Пристрій відповів, але не регістрами ідентифікації Sherpa. Перевірте адресу Modbus."),
 "e_unsup": ("This unit reports identify code {code}. Only 1134 (Sherpa S2, firmware 0.57) is supported so far; run tools/probe_sherpa.py and open an issue with the capture.",
             "Агрегат повідомляє код ідентифікації {code}. Поки що підтримується лише 1134 (Sherpa S2, прошивка 0.57); запустіть tools/probe_sherpa.py і створіть issue з результатом."),
 "e_invalid_prefix": ("Use lowercase letters, digits and underscores only.", "Лише малі латинські літери, цифри та підкреслення."),
 "e_prefix_in_use": ("Another Sherpa already uses this prefix.", "Цей префікс уже використовує інший Sherpa."),
 "a_already": ("This Sherpa is already configured.", "Цей Sherpa вже налаштовано."),
 "a_reconf": ("Connection updated.", "Підключення оновлено."),
 "rtu_over_tcp": ("Transparent serial server (RTU over TCP)", "Прозорий серійний сервер (RTU over TCP)"),
 "tcp": ("Modbus TCP gateway", "Шлюз Modbus TCP"),
 "opt_title": ("Link, writes and mode control", "Зв'язок, запис і керування режимом"),
 "opt_desc": ("The RS-485 link stalls for 10-30 s now and then; that is normal. Entities keep their last values until a failure has lasted as long as set here.",
              "Зв'язок RS-485 час від часу зависає на 10-30 с; це нормально. Сутності зберігають останні значення, доки збій не триває довше, ніж задано тут."),
 "opt_mode_control": ("Mode control", "Керування режимом"),
 "opt_mode_control_desc": ("Set the unit's mode from Home Assistant (select, ECO and night switches, climate, hot water), through register 106. Needs Allow writes. Works only while the panel has handed control to RS-485 (ADDR220 = 1): the integration then writes the mode every 60 s, because the unit raises E09 after 255 s without a write. It never writes ADDR220. To hand control back, set ADDR220 = 0 on the panel.",
                          "Встановлювати режим агрегату з Home Assistant (вибір режиму, перемикачі ECO і нічного режиму, клімат, гаряча вода) через регістр 106. Потрібно «Дозволити запис». Працює лише поки панель передала керування RS-485 (ADDR220 = 1): тоді інтеграція записує режим кожні 60 с, бо без запису 255 с агрегат видає E09. ADDR220 вона ніколи не записує. Щоб повернути керування, встановіть на панелі ADDR220 = 0."),
 "e_mode_control_needs_writes": ("Mode control needs Allow writes. Turn that on too.", "«Керування режимом» потребує «Дозволити запис». Увімкніть і його."),
 "unavailable_after": ("Unavailable after", "Недоступно через"),
 "x_unsup": ("The Sherpa reports identify code {code} ({model}), a register layout this integration does not know.", "Sherpa повідомляє код ідентифікації {code} ({model}) — розкладку регістрів, яку ця інтеграція не знає."),
 "x_not": ("No Sherpa answered at Modbus address {slave}.", "За адресою Modbus {slave} не відповів жоден Sherpa."),
 "x_cannot": ("Cannot reach the Sherpa on {endpoint}.", "Не вдається зв'язатися із Sherpa через {endpoint}."),
 "i_title": ("Unsupported Sherpa model", "Непідтримувана модель Sherpa"),
 "i_desc": ("The unit reports identify code {code} ({model}). This integration has a register map only for identify code 1134 (Sherpa S2, firmware 0.57), and reading another layout with it would show wrong values. Capture this unit with tools/probe_sherpa.py and open an issue with the result.",
            "Агрегат повідомляє код ідентифікації {code} ({model}). Інтеграція має карту регістрів лише для коду 1134 (Sherpa S2, прошивка 0.57), і читання іншої розкладки показувало б хибні значення. Зніміть дані цього агрегату за допомогою tools/probe_sherpa.py і створіть issue з результатом."),
}

def doc(lang):
    i = 0 if lang == "en" else 1
    t = {k: v[i] for k, v in T.items()}
    serial_data = {"serial_port": t["serial_port"], "baudrate": t["baudrate"], "slave": t["slave"], "entity_prefix": t["prefix"]}
    serial_desc = {"slave": t["slave_desc"], "entity_prefix": t["prefix_desc"]}
    network_data = {"host": t["host"], "port": t["port"], "transport": t["transport"], "slave": t["slave"], "entity_prefix": t["prefix"]}
    reconf_data = {"serial_port": t["serial_port"], "baudrate": t["baudrate"], "host": t["host"], "port": t["port"], "transport": t["transport"], "slave": t["slave"]}
    return {
        "config": {
            "step": {
                "user": {"title": t["menu_title"], "description": t["menu_desc"],
                         "menu_options": {"serial": t["serial"], "network": t["network"]}},
                "serial": {"title": t["serial_title"], "description": t["serial_desc"], "data": serial_data, "data_description": serial_desc},
                "network": {"title": t["network_title"], "description": t["network_desc"], "data": network_data, "data_description": serial_desc},
                "reconfigure": {"title": t["reconf_title"], "description": t["reconf_desc"], "data": reconf_data, "data_description": {"slave": t["slave_desc"]}},
            },
            "error": {"cannot_connect": t["e_cannot"], "not_a_sherpa": t["e_not"], "unsupported_model": t["e_unsup"],
                      "invalid_prefix": t["e_invalid_prefix"], "prefix_in_use": t["e_prefix_in_use"]},
            "abort": {"already_configured": t["a_already"], "reconfigure_successful": t["a_reconf"]},
        },
        "options": {"step": {"init": {"title": t["opt_title"], "description": t["opt_desc"],
                                      "data": {"unavailable_after": t["unavailable_after"],
                                               "allow_writes": t["allow_writes"],
                                               "mode_control": t["opt_mode_control"]},
                                      "data_description": {"allow_writes": t["allow_writes_desc"],
                                                           "mode_control": t["opt_mode_control_desc"]}}},
                    "error": {"mode_control_needs_writes": t["e_mode_control_needs_writes"]}},
        "services": {"verify_write": {"name": t["svc_name"], "description": t["svc_desc"], "fields": {
            "config_entry_id": {"name": t["svc_entry"], "description": t["svc_entry_desc"]},
            "register": {"name": t["svc_register"], "description": t["svc_register_desc"]},
            "hold_seconds": {"name": t["svc_hold"], "description": t["svc_hold_desc"]}}},
            "read_registers": {"name": t["rr_name"], "description": t["rr_desc"], "fields": {
                "config_entry_id": {"name": t["svc_entry"], "description": t["svc_entry_desc"]},
                "address": {"name": t["rr_address"], "description": t["rr_address_desc"]},
                "count": {"name": t["rr_count"], "description": t["rr_count_desc"]}}},
            "write_mode_command": {"name": t["mc_name"], "description": t["mc_desc"], "fields": {
                "config_entry_id": {"name": t["svc_entry"], "description": t["svc_entry_desc"]},
                "value": {"name": t["mc_value"], "description": t["mc_value_desc"]}}}},
        "selector": {"framing": {"options": {"rtu_over_tcp": t["rtu_over_tcp"], "tcp": t["tcp"]}},
                     "write_register": {"options": {k: writable_name(k, i) for k in sorted(NUMBER_KEYS + SWITCH_KEYS)}}},
        "entity": entities(lang),
        "exceptions": {**{k: {"message": t[f"x_{v}"]} for k, v in (
            ("writes_disabled", "writes_disabled"), ("not_writable", "not_writable"),
            ("not_a_candidate", "not_a_candidate"), ("out_of_range", "out_of_range"),
            ("rate_limited", "rate_limited"), ("write_not_applied", "not_applied"),
            ("write_failed", "write_failed"), ("write_refused", "write_refused"),
            ("restore_failed", "restore_failed"), ("choose_entry", "choose_entry"),
            ("read_failed", "read_failed"), ("invalid_mode_command", "invalid_mode_command"),
            ("mode_control_inactive", "mode_control_inactive"),
            ("mode_control_active", "mode_control_active"))},
                       "unsupported_model": {"message": t["x_unsup"]}, "not_a_sherpa": {"message": t["x_not"]},
                       "cannot_connect": {"message": t["x_cannot"]}},
        "issues": {"unsupported_model": {"title": t["i_title"], "description": t["i_desc"]},
                   "restore_failed": {"title": t["i_restore_title"], "description": t["i_restore_desc"]},
                   "serial_control_unmanaged": {"title": t["i_unmanaged_title"], "description": t["i_unmanaged_desc"]},
                   "mode_keepalive_lost": {"title": t["i_keepalive_title"], "description": t["i_keepalive_desc"]},
                   "mode_not_applied": {"title": t["i_not_applied_title"], "description": t["i_not_applied_desc"]}},
    }

OUTPUTS = (("strings.json", "en"), ("translations/en.json", "en"), ("translations/uk.json", "uk"))


def render(lang: str) -> str:
    return json.dumps(doc(lang), indent=2, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if a file is stale")
    args = ap.parse_args(argv)
    stale = []
    for name, lang in OUTPUTS:
        path, text = PACKAGE / name, render(lang)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
            continue
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print(f"stale: {', '.join(stale)}; run tools/gen_translations.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
