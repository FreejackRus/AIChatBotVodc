<?php
/**
 * Компонент чатбота ВОККДЦ для 1С-Битрикс
 * Устанавливается в /local/components/vodc/chatbot/
 */

if (!defined("B_PROLOG_INCLUDED") || B_PROLOG_INCLUDED !== true) die();

use Bitrix\Main\Loader;
use Bitrix\Main\Config\Option;

class VodcChatbotComponent extends CBitrixComponent
{
    public function onPrepareComponentParams($arParams)
    {
        // Параметры по умолчанию
        $arParams['SERVER_URL'] = isset($arParams['SERVER_URL']) ? $arParams['SERVER_URL'] : 'http://localhost:5000';
        $arParams['WIDGET_POSITION'] = isset($arParams['WIDGET_POSITION']) ? $arParams['WIDGET_POSITION'] : 'bottom-right';
        $arParams['THEME'] = isset($arParams['THEME']) ? $arParams['THEME'] : 'vodc';
        $arParams['SHOW_HEADER'] = isset($arParams['SHOW_HEADER']) ? $arParams['SHOW_HEADER'] : 'Y';
        $arParams['HEADER_TEXT'] = isset($arParams['HEADER_TEXT']) ? $arParams['HEADER_TEXT'] : 'Ассистент ВОККДЦ';
        
        return $arParams;
    }
    
    public function executeComponent()
    {
        $this->includeComponentTemplate();
    }
}

// Регистрация компонента
$arComponentDescription = array(
    "NAME" => "Чатбот ВОККДЦ",
    "DESCRIPTION" => "Интеллектуальный ассистент по вопросам Воронежского областного диагностического  центра",
    "PATH" => array(
        "ID" => "vodc",
        "NAME" => "ВОККДЦ",
    ),
    "ICON" => "/images/icon.gif",
);