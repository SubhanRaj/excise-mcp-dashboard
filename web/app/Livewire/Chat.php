<?php

namespace App\Livewire;

use App\Livewire\Concerns\ConfirmsWithSweetAlert;
use App\Models\ChartArtifact;
use App\Models\Conversation;
use App\Models\MessageToolCall;
use App\Services\OrchestratorClient;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Livewire\Component;

class Chat extends Component
{
    use ConfirmsWithSweetAlert;

    /**
     * Verified against the real August 2026 Lucknow import (CLAUDE.md's dispatch-report
     * milestone), the FY2025-26 SRO shop revenue snapshot, and the live knowledge base — a
     * first-time visitor's proof that the tool loop produces a real answer, not a
     * hypothetical one. Shown only on the empty thread; not a data source of any kind, so a
     * plain const is enough.
     */
    public const EXAMPLE_QUESTIONS = [
        ['question' => 'How many country liquor and composite shops are in Lucknow in August 2026?', 'chart' => false],
        ['question' => 'Compare dispatched volume by shop category in Lucknow for August 2026.', 'chart' => true],
        ['question' => 'What does the excise policy say about MGQ?', 'chart' => false],
        ['question' => 'How much revenue was generated from beer sale across Uttar Pradesh in FY 2025-26?', 'chart' => false],
        ['question' => 'Which district generated the highest revenue in FY2025-26?', 'chart' => false],
    ];

    public ?string $conversationId = null;

    public string $message = '';

    public ?string $model = null;

    public bool $includeChart = false;

    /**
     * Set once, at mount, and never touched again — the chat thread's Alpine
     * component keys off this instead of $conversationId so that send()
     * creating a conversation mid-request doesn't change the wire:key and
     * make Livewire tear down and recreate that DOM node. That teardown was
     * destroying the very listener meant to catch the chat-message-ready
     * event it fires in the same request, so the browser's fetch() to
     * ChatController::send() never happened.
     */
    public ?string $mountedConversationId = null;

    public function mount(?Conversation $conversation = null): void
    {
        if ($conversation) {
            abort_unless($conversation->user_id === Auth::id(), 403);
            $this->conversationId = $conversation->id;
            $this->model = $conversation->model;
        }
        $this->mountedConversationId = $this->conversationId;
    }

    public function useExample(string $question, bool $chart = false): void
    {
        $this->message = $question;
        $this->includeChart = $chart;
    }

    public function send(): void
    {
        $this->validate(['message' => ['required', 'string', 'max:4000']]);

        if (! $this->conversationId) {
            $conversation = Conversation::create([
                'user_id' => Auth::id(),
                'model' => $this->model,
                'title' => Str::limit(trim($this->message), 60),
            ]);
            $this->conversationId = $conversation->id;
        }

        $this->dispatch(
            'chat-message-ready',
            conversationId: $this->conversationId,
            message: $this->message,
            model: $this->model,
            includeChart: $this->includeChart,
        );
        $this->message = '';
        // includeChart stays as the user left it — it used to reset to off here, right as
        // the message left, which looked like the toggle click itself hadn't registered.
        // It now behaves like the model picker next to it: a standing choice for the
        // composer, not a one-shot flag cleared out from under the person who set it.
    }

    public function syncAfterStream(): void
    {
        // No state to change — this method exists only to force a fresh render()
        // once the browser's fetch() to ChatController::send has finished, so the
        // just-persisted transcript replaces the client-rendered live turn.
    }

    public function deleteConversation(string $id): void
    {
        $conversation = Conversation::findOrFail($id);
        abort_unless($conversation->user_id === Auth::id(), 403);
        $conversation->delete();
        if ($this->conversationId === $id) {
            $this->redirect(route('chat'));
        }
    }

    public function forceDeleteConversation(string $id): void
    {
        $conversation = Conversation::withTrashed()->findOrFail($id);
        abort_unless($conversation->user_id === Auth::id(), 403);

        // chart_artifacts is a polymorphic owner with no DB-level FK to message_tool_calls,
        // so the cascadeOnDelete() on conversations -> messages -> message_tool_calls below
        // would otherwise leave orphaned artifact rows and files behind.
        $toolCallIds = MessageToolCall::withTrashed()
            ->whereIn('message_id', $conversation->messages()->withTrashed()->pluck('id'))
            ->pluck('id');
        ChartArtifact::withTrashed()
            ->where('owner_type', MessageToolCall::class)
            ->whereIn('owner_id', $toolCallIds)
            ->get()
            ->each(function (ChartArtifact $artifact): void {
                foreach (['png_path', 'svg_path', 'pdf_path'] as $column) {
                    if ($artifact->$column) {
                        Storage::disk('local')->delete($artifact->$column);
                    }
                }
                $artifact->forceDelete();
            });

        $conversation->forceDelete();
        if ($this->conversationId === $id) {
            $this->redirect(route('chat'));
        }
    }

    public function render()
    {
        $conversations = Conversation::where('user_id', Auth::id())->latest()->get();

        $activeConversation = $this->conversationId
            ? Conversation::with('messages.toolCalls.chartArtifact')->find($this->conversationId)
            : null;

        $models = collect(config('models.models'))->where('role', 'chat')->all();
        try {
            $pulled = collect(app(OrchestratorClient::class)->health()['models'] ?? [])
                ->where('pulled', true)
                ->pluck('key');
            if ($pulled->isNotEmpty()) {
                $models = collect($models)
                    ->filter(fn ($m) => $pulled->contains($m['ollama_tag']))
                    ->all();
            }
        } catch (ConnectionException|\Throwable $e) {
            Log::error('Chat::render orchestrator health check failed', ['error' => $e->getMessage()]);
        }

        return view('livewire.chat', [
            'conversations' => $conversations,
            'activeConversation' => $activeConversation,
            'models' => $models,
        ])->layout('components.layout', [
            'pageTitle' => $activeConversation?->title ?? 'Chat',
            'title' => $activeConversation?->title ?? 'Chat',
        ]);
    }
}
