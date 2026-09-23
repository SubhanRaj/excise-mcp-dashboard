<?php

namespace App\Services;

/**
 * The transport OrchestratorClient::chatStream()/runQuery() delegate to for a
 * genuinely-streamed ndjson POST. Pulled out from OrchestratorClient itself so tests can
 * swap in a fake generator — Laravel's Http::fake() cannot intercept CurlOrchestratorStream's
 * raw curl calls the way it does the Http facade (that gap is exactly why curl is used
 * here at all; see CurlOrchestratorStream's own docblock).
 */
interface OrchestratorStream
{
    /**
     * @param  array<string, mixed>  $payload
     * @param  callable(float $idleSeconds, float $totalSeconds): bool  $isTimedOut  polled
     *                                                                               once per idle wait; true ends the stream as a timeout
     * @return \Generator<int, array<string, mixed>>
     *
     * @throws \RuntimeException
     */
    public function stream(string $path, array $payload, callable $isTimedOut): \Generator;
}
