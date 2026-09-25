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

        // A chart is now a deterministic step the orchestrator takes itself after a
        // successful run_sql_query, never something the chat model decides on or writes —
        // want_chart carries the composer's toggle as a real field instead of leaving the
        // orchestrator to infer intent from wording in the message text (MCP_ENGINES.md
        // §Tools).
        $wantChart = $validated['includeChart'] ?? false;

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
            'message' => $validated['message'],
            'history' => $history,
            'model' => $model,
            'want_chart' => $wantChart,
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
     * The replay is authoritative and starts from the turn's very first event,
     * so `streamTurn()` below rebuilds this message's tool calls from it wholesale
     * rather than appending — but only once it knows the replay reached at least
     * as far as what is already saved. A resume's own connection dying again
     * partway through (the same ~100s cap that made this resume necessary in the
     * first place) must never regress an already-working answer to less than it
     * had; confirmed live, a chart-render retry that ran long enough to need a
     * second resume left a real answer empty after the second attempt died with
     * nothing replayed yet.
     */
    public function resume(
        Request $request,
        Conversation $conversation,
        Message $message,
        OrchestratorClient $orchestrator
    ): StreamedResponse {
        abort_unless($conversation->user_id === Auth::id(), 403);
        abort_unless($message->conversation_id === $conversation->id && $message->role === 'assistant', 404);

        return $this->streamTurn($message, $orchestrator->chatStream([
            'conversation_id' => $conversation->id,
            'turn_id' => $message->id,
            // Ignored by the orchestrator once turn_id already names a running
            // (or just-finished) turn — only the first /chat call for a turn_id
            // actually starts it (main.py's chat()), want_chart included.
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
            // Accumulated locally and only written to the database once the loop
            // below ends — the same deferred-persist shape $assistantText already
            // used, extended to tool calls too (see persistIfNotWorseThanBefore()).
            $toolCalls = [];
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
                        $toolCalls[] = [
                            'tool_name' => $pendingToolCall['name'],
                            'arguments' => $pendingToolCall['arguments'],
                            'result_summary' => $event['tool_result'],
                            'chart' => null,
                        ];
                        $pendingToolCall = null;
                    } elseif (isset($event['chart']) && $toolCalls !== []) {
                        $toolCalls[array_key_last($toolCalls)]['chart'] = $event['chart'];
                    } elseif (isset($event['done'])) {
                        $promptTokens = $event['done']['prompt_tokens'] ?? 0;
                        $completionTokens = $event['done']['completion_tokens'] ?? 0;
                    }
                }
            } catch (\Throwable $e) {
                Log::error('ChatController stream failed', ['error' => $e->getMessage()]);
                echo json_encode(['error' => ['stage' => 'internal', 'message' => 'The chat connection was interrupted.']])."\n";
            } finally {
                $this->persistIfNotWorseThanBefore(
                    $assistantMessage, $assistantText, $toolCalls, $promptTokens, $completionTokens
                );
            }
        }, 200, [
            'Content-Type' => 'application/x-ndjson',
            'Cache-Control' => 'no-cache',
            'X-Accel-Buffering' => 'no',
        ]);
    }

    /**
     * A resume's own connection can die again before replaying as far as an
     * earlier attempt already got — confirmed live, a second resume (needed
     * because a chart render kept retrying) died with nothing replayed yet,
     * and unconditionally persisting turned a real, already-saved answer into
     * an empty one. Comparing against what is already on the row — never
     * writing something shorter or with fewer tool calls than what is already
     * there — means a resume can only advance a message's own saved state, not
     * regress it. A fresh send() always has empty content and zero tool calls
     * to compare against, so this never blocks a first attempt, including one
     * that genuinely produced nothing.
     *
     * @param  array<int, array{tool_name: string, arguments: mixed, result_summary: mixed, chart: mixed}>  $toolCalls
     */
    private function persistIfNotWorseThanBefore(
        Message $assistantMessage,
        string $assistantText,
        array $toolCalls,
        int $promptTokens,
        int $completionTokens
    ): void {
        $existingContent = $assistantMessage->content ?? '';
        $existingToolCallCount = $assistantMessage->toolCalls()->count();
        if (strlen($assistantText) < strlen($existingContent) || count($toolCalls) < $existingToolCallCount) {
            return;
        }

        foreach ($assistantMessage->toolCalls as $toolCall) {
            $toolCall->chartArtifact?->delete();
        }
        $assistantMessage->toolCalls()->delete();

        foreach ($toolCalls as $toolCall) {
            $created = $assistantMessage->toolCalls()->create([
                'tool_name' => $toolCall['tool_name'],
                'arguments' => $toolCall['arguments'],
                'result_summary' => $toolCall['result_summary'],
            ]);
            if ($toolCall['chart'] !== null) {
                ChartArtifact::create([
                    'owner_type' => MessageToolCall::class,
                    'owner_id' => $created->id,
                    'spec' => $toolCall['chart'],
                ]);
            }
        }

        $assistantMessage->update([
            'content' => $assistantText,
            'prompt_tokens' => $promptTokens,
            'completion_tokens' => $completionTokens,
        ]);
    }
}
