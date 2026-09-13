<?php

namespace App\Http\Controllers;

use App\Models\ChartArtifact;
use App\Models\Conversation;
use App\Models\Message;
use App\Models\MessageToolCall;
use App\Services\OrchestratorClient;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * A chat message streams a token every few hundred milliseconds, too fast for
 * the DB-polling relay Ask uses — this is the one place web/ does real
 * streaming I/O: it opens the orchestrator's ndjson /chat stream and pipes
 * each event to the browser as it arrives, persisting the transcript on the
 * side (web/plan/webui.md §9.1).
 */
class ChatController extends Controller
{
    private const HISTORY_TURNS = 8;

    public function send(
        Request $request,
        Conversation $conversation,
        OrchestratorClient $orchestrator
    ): StreamedResponse {
        abort_unless($conversation->user_id === Auth::id(), 403);

        $validated = $request->validate([
            'message' => ['required', 'string', 'max:4000'],
            'model' => ['nullable', 'string'],
        ]);

        $model = $validated['model'] ?? $conversation->model;
        if ($model !== null && ! array_key_exists($model, config('models.models'))) {
            abort(422, 'Unknown model.');
        }

        $userMessage = $conversation->messages()->create(['role' => 'user', 'content' => $validated['message']]);

        $history = $conversation->messages()
            ->where('id', '!=', $userMessage->id)
            ->orderByDesc('created_at')
            ->limit(self::HISTORY_TURNS * 2)
            ->get()
            ->reverse()
            ->map(fn (Message $m) => ['role' => $m->role, 'content' => $m->content])
            ->values()
            ->all();

        $conversation->update(array_filter([
            'model' => $conversation->model ?? $model,
            'title' => $conversation->title ?? Str::limit($validated['message'], 60),
        ], fn ($v) => $v !== null));

        $assistantMessage = $conversation->messages()->create(['role' => 'assistant', 'content' => '', 'model' => $model]);

        return response()->stream(function () use ($conversation, $assistantMessage, $validated, $model, $history, $orchestrator) {
            $assistantText = '';
            $pendingToolCall = null;
            $lastToolCallId = null;

            try {
                foreach ($orchestrator->chatStream([
                    'conversation_id' => $conversation->id,
                    'message' => $validated['message'],
                    'history' => $history,
                    'model' => $model,
                ]) as $event) {
                    echo json_encode($event)."\n";
                    if (ob_get_level() > 0) {
                        ob_flush();
                    }
                    flush();

                    if (isset($event['token'])) {
                        $assistantText .= $event['token'];
                    } elseif (isset($event['tool_call'])) {
                        $pendingToolCall = $event['tool_call'];
                    } elseif (isset($event['tool_result']) && $pendingToolCall !== null) {
                        $toolCall = $assistantMessage->toolCalls()->create([
                            'tool_name' => $pendingToolCall['name'],
                            'arguments' => $pendingToolCall['arguments'],
                            'result_summary' => $event['tool_result'],
                        ]);
                        $lastToolCallId = $toolCall->id;
                        $pendingToolCall = null;
                    } elseif (isset($event['chart']) && $lastToolCallId !== null) {
                        ChartArtifact::create([
                            'owner_type' => MessageToolCall::class,
                            'owner_id' => $lastToolCallId,
                            'spec' => $event['chart'],
                        ]);
                    }
                }
            } catch (\Throwable $e) {
                Log::error('ChatController::send stream failed', ['error' => $e->getMessage()]);
                echo json_encode(['error' => ['stage' => 'internal', 'message' => 'The chat connection was interrupted.']])."\n";
            } finally {
                $assistantMessage->update(['content' => $assistantText]);
            }
        }, 200, [
            'Content-Type' => 'application/x-ndjson',
            'Cache-Control' => 'no-cache',
            'X-Accel-Buffering' => 'no',
        ]);
    }
}
