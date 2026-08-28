$env:OPENROUTER_API_KEY = "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"

$projectRoot = Split-Path -Parent $PSScriptRoot

$codexArgs = @(
    "--cd"
    $projectRoot
    "-c"
    'model_provider="openrouter"'
    "-c"
    'model="deepseek/deepseek-v4-flash-0731"'
    "-c"
    'model_providers.openrouter.name="OpenRouter"'
    "-c"
    'model_providers.openrouter.base_url="https://openrouter.ai/api/v1"'
    "-c"
    'model_providers.openrouter.env_key="OPENROUTER_API_KEY"'
    "-c"
    'model_providers.openrouter.wire_api="responses"'
    "-c"
    'model_reasoning_effort="medium"'
)

& codex @codexArgs