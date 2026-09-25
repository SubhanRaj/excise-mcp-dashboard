<?php

namespace Tests\Support;

use App\Services\OrchestratorStream;

/**
 * Simulates a turn whose connection dies partway through — the first stream()
 * call yields $firstEvents then throws, the way CurlOrchestratorStream does
 * when Cloudflare's own duration cap cuts the connection (MCP_ENGINES.md
 * §Streamed events) — and a second call (the resume) yields $resumeEvents
 * cleanly, standing in for the orchestrator replaying the turn's full history.
 */
class FlakyOrchestratorStream implements OrchestratorStream
{
    /** @var array<int, array<string, mixed>> */
    public array $capturedPayloads = [];

    private int $callIndex = 0;

    /**
     * @param  array<int, array<string, mixed>>  $firstEvents
     * @param  array<int, array<string, mixed>>  $resumeEvents
     */
    public function __construct(private array $firstEvents, private array $resumeEvents) {}

    public function stream(string $path, array $payload, callable $isTimedOut): \Generator
    {
        $this->capturedPayloads[] = $payload;
        if ($this->callIndex++ === 0) {
            yield from $this->firstEvents;
            throw new \RuntimeException('orchestrator /chat: stream timed out');
        }
        yield from $this->resumeEvents;
    }
}
