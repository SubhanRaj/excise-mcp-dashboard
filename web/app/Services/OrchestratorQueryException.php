<?php

namespace App\Services;

/**
 * Wraps a typed {error, request_id, stage} event from the orchestrator's ndjson
 * stream — the web app renders `stage` in the UI (CLAUDE.md §Errors).
 */
class OrchestratorQueryException extends \RuntimeException
{
    public function __construct(string $message, public readonly ?string $stage = null)
    {
        parent::__construct($message);
    }
}
