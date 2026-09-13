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

    private function request()
    {
        return Http::baseUrl(config('services.orchestrator.base_url'))
            ->withToken(config('services.orchestrator.token'))
            ->timeout(10);
    }
}
