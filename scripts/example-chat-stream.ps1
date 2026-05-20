# Приклад SSE-запиту до /chat/stream без пекла з лапками в PowerShell.
# Запускай з будь-якої теки: .\<шлях>\scripts\example-chat-stream.ps1
$ErrorActionPreference = "Stop"

$baseUrl = if ($env:CHAT_API_URL) { $env:CHAT_API_URL.TrimEnd("/") } else { "http://127.0.0.1:8080" }
$apiKey = if ($env:X_API_KEY) { $env:X_API_KEY } else { "sk-demo-free-rag" }

$bodyObj = [ordered]@{
    message = "What is a backing service in the twelve-factor app?"
}
$json = $bodyObj | ConvertTo-Json -Compress

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$tmp = Join-Path $env:TEMP "homework-rag-chat-body.json"
[System.IO.File]::WriteAllText($tmp, $json, $utf8NoBom)

Write-Host "POST $baseUrl/chat/stream (see SSE below)`n" -ForegroundColor Cyan

& curl.exe -N `
    -H "X-API-Key: $apiKey" `
    -H "Content-Type: application/json" `
    -d "@$tmp" `
    "$baseUrl/chat/stream"
