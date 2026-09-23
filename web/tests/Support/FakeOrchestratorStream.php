<?php

namespace Tests\Support;

use App\Services\OrchestratorStream;

/**
 * Replaces CurlOrchestratorStream in a test — Http::fake() cannot intercept its raw curl
 * calls, so a feature test binds this instead via $this->app->instance(OrchestratorStream::class, ...).
 * Yields the given canned events regardless of $isTimedOut, capturing the request payload
 * so a test can assert on it in place of Http::assertSent().
 */
class FakeOrchestratorStream implements OrchestratorStream
{
    /** @var array<string, mixed> */
    public array $capturedPayload = [];

    /** @param array<int, array<string, mixed>> $events */
    public function __construct(private array $events) {}

    public function stream(string $path, array $payload, callable $isTimedOut): \Generator
    {
        $this->capturedPayload = $payload;
        yield from $this->events;
    }
}
