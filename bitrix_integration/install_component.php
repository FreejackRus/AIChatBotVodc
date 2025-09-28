<?php
/**
 * Установка компонента чатбота ВОККДЦ в 1С-Битрикс
 * 
 * 1. Скопируйте папку компонента в /local/components/vodc/chatbot/
 * 2. Включите компонент на нужных страницах через редактор Битрикс
 * 3. Настройте параметры компонента
 */

// Пример использования в PHP-шаблоне сайта
$APPLICATION->IncludeComponent(
    "vodc:chatbot", 
    ".default", 
    array(
        "SERVER_URL" => "http://localhost:5000", // URL вашего Flask-сервера
        "WIDGET_POSITION" => "bottom-right", // bottom-left, top-right, top-left
        "THEME" => "vodc", // тема оформления
        "SHOW_HEADER" => "Y", // показывать заголовок
        "HEADER_TEXT" => "Ассистент ВОККДЦ", // текст заголовка
    ),
    false
);

// Пример использования в визуальном редакторе Битрикс
// Добавьте компонент через "Добавить компонент" -> "ВОККДЦ" -> "Чатбот ВОККДЦ"

// Параметры для настройки:
$arComponentParameters = array(
    "SERVER_URL" => array(
        "PARENT" => "BASE",
        "NAME" => "URL сервера чатбота",
        "TYPE" => "STRING",
        "DEFAULT" => "http://localhost:5000",
        "DESCRIPTION" => "Адрес Flask-сервера с чатботом"
    ),
    "WIDGET_POSITION" => array(
        "PARENT" => "VISUAL",
        "NAME" => "Позиция виджета",
        "TYPE" => "LIST",
        "VALUES" => array(
            "bottom-right" => "Внизу справа",
            "bottom-left" => "Внизу слева", 
            "top-right" => "Вверху справа",
            "top-left" => "Вверху слева"
        ),
        "DEFAULT" => "bottom-right"
    ),
    "THEME" => array(
        "PARENT" => "VISUAL",
        "NAME" => "Тема оформления",
        "TYPE" => "LIST",
        "VALUES" => array(
            "vodc" => "ВОККДЦ",
            "dark" => "Темная",
            "light" => "Светлая"
        ),
        "DEFAULT" => "vodc"
    ),
    "SHOW_HEADER" => array(
        "PARENT" => "VISUAL",
        "NAME" => "Показывать заголовок",
        "TYPE" => "CHECKBOX",
        "DEFAULT" => "Y"
    ),
    "HEADER_TEXT" => array(
        "PARENT" => "VISUAL", 
        "NAME" => "Текст заголовка",
        "TYPE" => "STRING",
        "DEFAULT" => "Ассистент ВОККДЦ"
    )
);

// Добавьте в init.php для автоматической загрузки
// Bitrix\Main\Loader::registerAutoLoadClasses('vodc.chatbot', array(
//     'VodcChatbotComponent' => '/local/components/vodc/chatbot/component.php'
// ));
?>