<?php

namespace App\Services;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Support\Facades\Http;

/**
 * The one place web/ speaks HTTP to the orchestrator (127.0.0.1:8085, bearer-token-gated) —
 * web/ never reaches Postgres, Ollama, or a Python process directly (CLAUDE.md).
 */
class OrchestratorClient
{
    /**
     * @return array{documents: array<int, array<string, mixed>>, total: int}
     *
     * @throws ConnectionException|RequestException
     */
    public function kbDocuments(int $page = 1, int $perPage = 20): array
    {
        $response = $this->request()
            ->get('/kb/documents', ['page' => $page, 'per_page' => $perPage])
            ->throw();

        return $response->json();
    }

    /**
     * @return array<int, array<string, mixed>>
     *
     * @throws ConnectionException|RequestException
     */
    public function kbSearch(string $query, int $limit = 20): array
    {
        $response = $this->request()
            ->post('/kb/search', ['query' => $query, 'limit' => $limit])
            ->throw();

        return $response->json('results', []);
    }

    /**
     * Consumes POST /query's streamed ndjson lines ({"stage": ...}, {"error": ...},
     * {"result": ...}), calling $onStage as each stage event arrives and returning the
     * final result. `RunExciseQuery` is the only caller (ARCHITECTURE.md — the job, not
     * the web worker, blocks on this).
     *
     * @param  array<string, mixed>  $payload
     * @param  callable(array<string, mixed>): void  $onStage
     * @return array<string, mixed>
     *
     * @throws ConnectionException|RequestException|OrchestratorQueryException
     */
    public function runQuery(array $payload, callable $onStage): array
    {
        $response = Http::baseUrl(config('services.orchestrator.base_url'))
            ->withToken(config('services.orchestrator.token'))
            ->withOptions(['stream' => true])
            ->timeout(300)
            ->post('/query', $payload)
            ->throw();

        $body = $response->toPsrResponse()->getBody();
        $buffer = '';
        $result = null;

        while (! $body->eof()) {
            $buffer .= $body->read(8192);
            while (($newlineAt = strpos($buffer, "\n")) !== false) {
                $line = trim(substr($buffer, 0, $newlineAt));
                $buffer = substr($buffer, $newlineAt + 1);
                if ($line === '') {
                    continue;
                }

                // Order matters: an {"error": ...} event also carries a flat "stage"
                // string (main.py's _stream_query), unlike a {"stage": {...}} event's
                // nested Stage object — check "error" first or it's mistaken for one.
                $event = json_decode($line, true, 512, JSON_THROW_ON_ERROR);
                if (isset($event['error'])) {
                    throw new OrchestratorQueryException($event['error'], $event['stage'] ?? null);
                } elseif (isset($event['stage'])) {
                    $onStage($event['stage']);
                } elseif (isset($event['result'])) {
                    $result = $event['result'];
                }
            }
        }

        if ($result === null) {
            throw new OrchestratorQueryException('orchestrator stream ended without a result');
        }

        return $result;
    }

    private function request()
    {
        return Http::baseUrl(config('services.orchestrator.base_url'))
            ->withToken(config('services.orchestrator.token'))
            ->timeout(10);
    }
}
