<?php

namespace App\Http\Controllers;

use App\Models\ChartArtifact;
use App\Models\Conversation;
use App\Models\Message;
use App\Models\MessageToolCall;
use App\Services\OrchestratorClient;
use Illuminate\Http\JsonResponse;
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
            'includeChart' => ['nullable', 'boolean'],
        ]);

        $model = $validated['model'] ?? $conversation->model;
        if ($model !== null && ! array_key_exists($model, config('models.models'))) {
            abort(422, 'Unknown model.');
        }

        $userMessage = $conversation->messages()->create(['role' => 'user', 'content' => $validated['message']]);

        // The model only charts a result "when it would help" (CHAT_SYSTEM_PROMPT) — left to
        // its own judgment, a single-number answer correctly gets no chart. The composer's
        // chart toggle turns that judgment call into an explicit ask for this one turn,
        // without putting the instruction in the message the user actually typed.
        $orchestratorMessage = ($validated['includeChart'] ?? false)
            ? $validated['message'].' Please include a chart to visualize the answer.'
            : $validated['message'];

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

        return $this->streamTurn($assistantMessage, $orchestrator->chatStream([
            'conversation_id' => $conversation->id,
            'turn_id' => $assistantMessage->id,
            'message' => $orchestratorMessage,
            'history' => $history,
            'model' => $model,
        ]));
    }

    /**
     * Reconnects to a turn whose own connection died for a reason that has
     * nothing to do with the model still working — confirmed live, Cloudflare's
     * own edge enforces roughly a 100s cap on total connection duration and
     * drops the browser regardless of the 15s heartbeat pings still arriving
     * (MCP_ENGINES.md §Streamed events). The orchestrator keeps the turn
     * running server-side once started; this attaches to it by the same
     * turn_id (the assistant message's own ULID) and replays its full history
     * from the start, since the earlier attempt may have died before
     * persisting any of it.
     *
     * Any tool call rows this message already carries are wiped first — the
     * replay is authoritative and starts from the turn's very first event, so
     * keeping the old rows would just duplicate whatever had already arrived
     * before the disconnect.
     */
    public function resume(
        Request $request,
        Conversation $conversation,
        Message $message,
        OrchestratorClient $orchestrator
    ): StreamedResponse {
        abort_unless($conversation->user_id === Auth::id(), 403);
        abort_unless($message->conversation_id === $conversation->id && $message->role === 'assistant', 404);

        foreach ($message->toolCalls as $toolCall) {
            $toolCall->chartArtifact?->delete();
        }
        $message->toolCalls()->delete();

        return $this->streamTurn($message, $orchestrator->chatStream([
            'conversation_id' => $conversation->id,
            'turn_id' => $message->id,
            // Ignored by the orchestrator once turn_id already names a running
            // (or just-finished) turn — only the first /chat call for a turn_id
            // actually starts it (main.py's chat()).
            'message' => '',
            'history' => [],
            'model' => $message->model,
        ]));
    }

    /**
     * The chat Stop button's real cancellation now that a dropped connection no
     * longer cancels the turn on its own (resume() above needs that not to
     * happen) — Stop has to say so explicitly instead.
     */
    public function cancel(
        Conversation $conversation,
        Message $message,
        OrchestratorClient $orchestrator
    ): JsonResponse {
        abort_unless($conversation->user_id === Auth::id(), 403);
        abort_unless($message->conversation_id === $conversation->id && $message->role === 'assistant', 404);

        $orchestrator->cancelChatTurn($message->id);

        return response()->json(['cancelled' => true]);
    }

    private function streamTurn(Message $assistantMessage, \Generator $events): StreamedResponse
    {
        return response()->stream(function () use ($assistantMessage, $events) {
            echo json_encode(['turn_id' => $assistantMessage->id])."\n";
            if (ob_get_level() > 0) {
                ob_flush();
            }
            flush();

            $assistantText = '';
            $pendingToolCall = null;
            $lastToolCallId = null;
            $promptTokens = 0;
            $completionTokens = 0;

            try {
                foreach ($events as $event) {
                    echo json_encode($event)."\n";
                    if (ob_get_level() > 0) {
                        ob_flush();
                    }
                    flush();

                    // A "Stop" click cancels the turn explicitly now (cancel() above)
                    // rather than relying on this disconnect — a turn survives a
                    // dropped connection on purpose so it can be resumed, so breaking
                    // here just stops *this* request from relaying it further, it no
                    // longer reaches the orchestrator as a cancellation.
                    if (connection_aborted()) {
                        break;
                    }

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
                    } elseif (isset($event['done'])) {
                        $promptTokens = $event['done']['prompt_tokens'] ?? 0;
                        $completionTokens = $event['done']['completion_tokens'] ?? 0;
                    }
                }
            } catch (\Throwable $e) {
                Log::error('ChatController stream failed', ['error' => $e->getMessage()]);
                echo json_encode(['error' => ['stage' => 'internal', 'message' => 'The chat connection was interrupted.']])."\n";
            } finally {
                $assistantMessage->update([
                    'content' => $assistantText,
                    'prompt_tokens' => $promptTokens,
                    'completion_tokens' => $completionTokens,
                ]);
            }
        }, 200, [
            'Content-Type' => 'application/x-ndjson',
            'Cache-Control' => 'no-cache',
            'X-Accel-Buffering' => 'no',
        ]);
    }
}
