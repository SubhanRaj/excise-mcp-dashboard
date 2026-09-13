<?php

namespace App\Http\Controllers;

use App\Models\Query;
use App\Services\ExportService;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Auth;
use Symfony\Component\HttpFoundation\Response;

/**
 * Two structurally-plain routes for the Ask flow (web/plan/webui.md §5, §8): the
 * stage-polling relay a browser fetch() calls every ~500ms while a query runs, and the
 * result export — both byte/JSON responses, not Livewire component renders.
 */
class AskController extends Controller
{
    public function stream(Query $query): JsonResponse
    {
        $this->authorizeOwner($query);

        return response()->json([
            'status' => $query->status,
            'current_stage' => $query->current_stage,
        ]);
    }

    public function export(Query $query, string $format, ExportService $exportService): Response
    {
        $this->authorizeOwner($query);
        abort_unless(in_array($format, ExportService::FORMATS, true), 422);
        abort_unless($query->status === 'complete' && $query->rows_preview, 404);

        $rows = $query->rows_preview;
        $columns = array_keys($rows[0] ?? []);
        $values = array_map(fn (array $row) => array_values($row), $rows);

        return $exportService->download($format, "query-{$query->id}", $columns, $values);
    }

    private function authorizeOwner(Query $query): void
    {
        abort_unless($query->user_id === Auth::id() || Auth::user()->isAdmin(), 403);
    }
}
