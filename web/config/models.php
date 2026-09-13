<?php

// The chat model picker's registry, mirroring pdf-markdown-pipeline's config/ocr.php
// (default key + a map keyed by short slug). This must track orchestrator/app/config.py's
// OLLAMA_SQL_MODEL/OLLAMA_CHAT_MODEL defaults — the orchestrator re-validates whatever key
// is sent against its own OLLAMA_ALLOWED_MODELS before any Ollama call (web/plan/webui.md §10).
return [

    'default' => 'llama3.1',

    'models' => [
        'qwen2.5-coder' => [
            'label' => 'Qwen 2.5 Coder (SQL/plot planner)',
            'role' => 'sql',
            'ollama_tag' => 'qwen2.5-coder:7b-instruct-q4_K_M',
        ],
        'llama3.1' => [
            'label' => 'Llama 3.1 (chat)',
            'role' => 'chat',
            'ollama_tag' => 'llama3.1:8b-instruct-q4_K_M',
        ],
    ],

];
