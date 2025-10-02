<?php
/**
 * Компонент чатбота ВОККДЦ для 1С-Битрикс
 * @author ВОККДЦ
 * @version 1.0
 */

if (!defined("B_PROLOG_INCLUDED") || B_PROLOG_INCLUDED !== true) die();

// Параметры компонента
$arDefaultParams = array(
    "SERVER_URL" => "http://your-server-domain:8085", // Замените на ваш домен или IP-адрес
    "WIDGET_POSITION" => "bottom-right",
    "THEME" => "vodc",
    "SHOW_HEADER" => "Y",
    "HEADER_TEXT" => "Ассистент ВОККДЦ"
);

// Объединяем с переданными параметрами
$arParams = array_merge($arDefaultParams, $arParams);

// Подключаем шаблон
$this->IncludeComponentTemplate();