<?php
/**
 * Описание компонента чатбота ВОККДЦ
 */

$arComponentDescription = array(
    "NAME" => "Чатбот ВОККДЦ",
    "DESCRIPTION" => "Интеллектуальный ассистент по вопросам Воронежского областного диагностического центра",
    "ICON" => "/images/icon.gif",
    "CACHE_PATH" => "Y",
    "PATH" => array(
        "ID" => "vodc",
        "NAME" => "ВОККДЦ",
        "CHILD" => array(
            "ID" => "chatbot",
            "NAME" => "Чатбот"
        )
    ),
    "PARAMETERS" => array(
        "SERVER_URL" => array(
            "NAME" => "URL сервера чатбота",
            "TYPE" => "STRING",
            "DEFAULT" => "http://localhost:5000",
            "PARENT" => "BASE"
        ),
        "WIDGET_POSITION" => array(
            "NAME" => "Позиция виджета",
            "TYPE" => "LIST",
            "VALUES" => array(
                "bottom-right" => "Внизу справа",
                "bottom-left" => "Внизу слева", 
                "top-right" => "Вверху справа",
                "top-left" => "Вверху слева"
            ),
            "DEFAULT" => "bottom-right",
            "PARENT" => "VISUAL"
        ),
        "THEME" => array(
            "NAME" => "Тема оформления",
            "TYPE" => "LIST",
            "VALUES" => array(
                "vodc" => "ВОККДЦ (синяя)",
                "dark" => "Темная"
            ),
            "DEFAULT" => "vodc",
            "PARENT" => "VISUAL"
        ),
        "SHOW_HEADER" => array(
            "NAME" => "Показывать заголовок",
            "TYPE" => "CHECKBOX",
            "DEFAULT" => "Y",
            "PARENT" => "VISUAL"
        ),
        "HEADER_TEXT" => array(
            "NAME" => "Текст заголовка",
            "TYPE" => "STRING",
            "DEFAULT" => "Ассистент ВОККДЦ",
            "PARENT" => "VISUAL"
        )
    )
);