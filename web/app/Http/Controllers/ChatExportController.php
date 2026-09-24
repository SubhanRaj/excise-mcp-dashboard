<?php

namespace App\Http\Controllers;

use App\Models\Conversation;
use App\Services\OrchestratorClient;
use Barryvdh\DomPDF\Facade\Pdf;
use Illuminate\Support\Facades\Auth;
use Symfony\Component\HttpFoundation\Response;

/**
 * A conversation's full transcript as a PDF — every message, tool call
 * summary, and chart, in order. Charts render through the same
 * OrchestratorClient::renderChart() ChartExportController uses for a single
 * chart, once per chart in the conversation, embedded as base64 PNG since
 * dompdf renders static HTML, not the interactive Plotly figure the chart
 * card shows on screen.
 */
class ChatExportController extends Controller
{
    public function export(Conversation $conversation, OrchestratorClient $orchestrator): Response
    {
        abort_unless($conversation->user_id === Auth::id() || Auth::user()->isAdmin(), 403);

        $conversation->load('messages.toolCalls.chartArtifact');

        $chartImages = [];
        foreach ($conversation->messages as $message) {
            foreach ($message->toolCalls as $toolCall) {
                $figure = $toolCall->chartArtifact?->plotlyFigure();
                if ($figure) {
                    $chartImages[$toolCall->id] = base64_encode($orchestrator->renderChart($figure, 'png'));
                }
            }
        }

        $pdf = Pdf::loadView('pdf.chat-transcript', [
            'conversation' => $conversation,
            'chartImages' => $chartImages,
        ]);

        return $pdf->download("chat-{$conversation->id}.pdf");
    }
}
