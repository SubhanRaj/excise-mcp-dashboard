<?php

namespace App\Jobs;

use App\Models\ChartArtifact;
use App\Models\Query as QueryModel;
use App\Services\OrchestratorClient;
use App\Services\OrchestratorQueryException;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Runs the one-shot /query pipeline for a `queries` row. The web worker never blocks on
 * this (ARCHITECTURE.md) — Livewire dispatches it and a plain route polls the row's
 * status column for the stage indicator (web/plan/webui.md §8).
 */
class RunExciseQuery implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    // Just under OrchestratorClient::runQuery()'s own 300s HTTP timeout, so a genuine
    // orchestrator timeout is reported as a failed query rather than a silently retried job.
    public int $timeout = 290;

    public int $tries = 1;

    public function __construct(public string $queryId) {}

    public function handle(OrchestratorClient $client): void
    {
        $query = QueryModel::findOrFail($this->queryId);
        $query->update(['status' => 'running']);

        try {
            $result = $client->runQuery(
                ['conversation_id' => $query->id, 'question' => $query->prompt],
                fn (array $stage) => $query->update(['current_stage' => $stage['name'] ?? null]),
            );

            DB::transaction(function () use ($query, $result) {
                $query->update([
                    'request_id' => $result['request_id'] ?? null,
                    'sql' => $result['sql'] ?? null,
                    'engine' => $result['engine'] ?? null,
                    'model' => $result['model'] ?? null,
                    'row_count' => $result['row_count'] ?? null,
                    'timings' => $result['timings_ms'] ?? null,
                    'rows_preview' => $result['rows_preview'] ?? null,
                    'summary' => $result['summary'] ?? null,
                    'status' => 'complete',
                ]);

                $plotlyJson = $result['chart']['plotly_json'] ?? null;
                if ($plotlyJson) {
                    ChartArtifact::create([
                        'owner_type' => QueryModel::class,
                        'owner_id' => $query->id,
                        'spec' => json_decode($plotlyJson, true),
                    ]);
                }
            });
        } catch (OrchestratorQueryException $e) {
            $query->update([
                'status' => 'failed',
                'current_stage' => $e->stage,
                'error_message' => $e->getMessage(),
            ]);
        } catch (\Throwable $e) {
            Log::error('RunExciseQuery failed', ['query_id' => $query->id, 'error' => $e->getMessage()]);
            $query->update(['status' => 'failed', 'error_message' => 'Something went wrong. Please try again.']);
        }
    }
}
