<?php

namespace App\Http\Controllers;

use App\Models\ChartArtifact;
use App\Services\OrchestratorClient;
use Illuminate\Http\Response;

/**
 * PNG/SVG/PDF export of a stored chart_artifacts row — the export links
 * on Ask's and Chat's chart cards. Mirrors AskController::export's
 * owner-check-then-stream shape; the row export there works off
 * rows_preview already in MariaDB, this one calls the orchestrator to
 * rasterize the stored Plotly figure (ROADMAP.md Milestone 5).
 */
class ChartExportController extends Controller
{
    private const FORMATS = ['png', 'svg', 'pdf'];

    private const MEDIA_TYPES = [
        'png' => 'image/png',
        'svg' => 'image/svg+xml',
        'pdf' => 'application/pdf',
    ];

    public function export(ChartArtifact $chartArtifact, string $format, OrchestratorClient $orchestrator): Response
    {
        abort_unless(in_array($format, self::FORMATS, true), 422);
        abort_unless($chartArtifact->ownerUserId() === auth()->id() || auth()->user()->isAdmin(), 403);

        $figure = $chartArtifact->plotlyFigure();
        abort_unless($figure, 404);

        $bytes = $orchestrator->renderChart($figure, $format);

        return response($bytes, 200, [
            'Content-Type' => self::MEDIA_TYPES[$format],
            'Content-Disposition' => "attachment; filename=\"chart-{$chartArtifact->id}.{$format}\"",
        ]);
    }
}
