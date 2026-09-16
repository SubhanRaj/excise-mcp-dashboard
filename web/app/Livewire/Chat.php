<?php

namespace App\Livewire;

use App\Models\Conversation;
use App\Services\OrchestratorClient;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Livewire\Component;

class Chat extends Component
{
    public ?string $conversationId = null;

    public string $message = '';

    public ?string $model = null;

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
        );
        $this->message = '';
    }

    public function syncAfterStream(): void
    {
        // No state to change — this method exists only to force a fresh render()
        // once the browser's fetch() to ChatController::send has finished, so the
        // just-persisted transcript replaces the client-rendered live turn.
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
