<?php

namespace App\Livewire\Admin;

use App\Services\OrchestratorClient;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Log;
use Livewire\Component;

/**
 * Read-only view of etl.ingestion_runs / etl.quarantine (ROADMAP.md
 * Milestone 5) — web/ never reaches Postgres directly, so this calls the
 * orchestrator's GET /etl/runs and GET /etl/quarantine the same way
 * KnowledgeBaseIndex calls GET /kb/documents.
 */
class EtlRunsIndex extends Component
{
    private const PER_PAGE = 20;

    public int $page = 1;

    public ?int $selectedRunId = null;

    public bool $unavailable = false;

    public function mount(): void
    {
        abort_unless(auth()->user()->hasPrivilege('etl.view'), 403);
    }

    public function nextPage(): void
    {
        $this->page++;
    }

    public function previousPage(): void
    {
        $this->page = max(1, $this->page - 1);
    }

    public function viewQuarantine(int $runId): void
    {
        $this->selectedRunId = $this->selectedRunId === $runId ? null : $runId;
    }

    public function render()
    {
        $runs = [];
        $total = 0;
        $quarantine = [];

        try {
            $response = app(OrchestratorClient::class)->etlRuns($this->page, self::PER_PAGE);
            $runs = $response['runs'] ?? [];
            $total = $response['total'] ?? 0;

            if ($this->selectedRunId !== null) {
                $quarantine = app(OrchestratorClient::class)
                    ->etlQuarantine(1, 50, $this->selectedRunId)['rows'] ?? [];
            }

            $this->unavailable = false;
        } catch (ConnectionException|\Throwable $e) {
            Log::error('EtlRunsIndex::render failed', ['error' => $e->getMessage()]);
            $this->unavailable = true;
        }

        return view('livewire.admin.etl-runs-index', [
            'runs' => $runs,
            'total' => $total,
            'perPage' => self::PER_PAGE,
            'quarantine' => $quarantine,
        ])->layout('components.layout', ['pageTitle' => 'ETL runs', 'title' => 'ETL runs']);
    }
}
