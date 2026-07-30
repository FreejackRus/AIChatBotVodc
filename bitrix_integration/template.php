<?php
if (!defined("B_PROLOG_INCLUDED") || B_PROLOG_INCLUDED !== true) {
    die();
}

$serverUrl = rtrim(
    htmlspecialcharsbx($arParams["SERVER_URL"] ?? "https://chat.vodc.ru"),
    "/"
);
$pageUrl = urlencode(
    "https://" . ($_SERVER["HTTP_HOST"] ?? "vodc.ru")
    . ($_SERVER["REQUEST_URI"] ?? "/")
);
$pageTitle = urlencode($APPLICATION->GetTitle());
$iframeSrc = $serverUrl . "/?page_url=" . $pageUrl . "&page_title=" . $pageTitle;
?>

<iframe
    id="vodc-ai-chat"
    src="<?=htmlspecialcharsbx($iframeSrc)?>"
    title="Информационный помощник ВОККДЦ"
    loading="lazy"
    style="position:fixed;inset:0;width:100%;height:100%;border:0;z-index:999999"
></iframe>

<script>
window.addEventListener('message', function (event) {
    if (event.origin !== <?=json_encode($serverUrl)?>) return;
    if (!event.data || event.data.type !== 'vodc:chat-event') return;
    if (typeof window.ym === 'function' && window.VODC_METRIKA_ID) {
        window.ym(
            window.VODC_METRIKA_ID,
            'reachGoal',
            'ai_chat_' + event.data.event
        );
    }
});
</script>
