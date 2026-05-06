<?php
$uri = $_SERVER['REQUEST_URI'];
$doc = basename(parse_url($uri, PHP_URL_PATH));
$doc = preg_replace('/[^0-9]/', '', $doc);

if (strlen($doc) !== 8 && strlen($doc) !== 11) {
    header('Content-Type: application/json; charset=utf-8');
    echo '{"success":false,"message":"Documento no valido"}';
    exit;
}

$ctx = stream_context_create([
    'ssl' => ['verify_peer' => false, 'verify_peer_name' => false]
]);

$result = @file_get_contents(
    "https://localhost:8076/Servicios/consultaDocumento/{$doc}",
    false,
    $ctx
);

header('Content-Type: application/json; charset=utf-8');
echo $result ?: '{"success":false,"message":"Error al consultar"}';
