<?php

namespace App\Livewire;

use App\Jobs\RunExciseQuery;
use App\Models\Query;
use App\Models\QueryFeedback;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Livewire\Component;

class Ask extends Component
{
    public string $prompt = '';

    public ?string $activeQueryId = null;

    public string $feedbackNote = '';

    public function mount(?Query $query = null): void
    {
        if ($query) {
            abort_unless($query->user_id === Auth::id(), 403);
            $this->activeQueryId = $query->id;
        }
    }

    public function submit(): void
    {
        $this->validate(['prompt' => ['required', 'string', 'max:2000']]);

        $key = 'ask:'.Auth::id();
        if (RateLimiter::tooManyAttempts($key, 10)) {
            $this->addError('prompt', 'Too many questions — please wait a moment before asking another.');

            return;
        }
        RateLimiter::hit($key, 60);

        $query = DB::transaction(fn () => Query::create([
            'user_id' => Auth::id(),
            'prompt' => $this->prompt,
            'status' => 'pending',
        ]));

        RunExciseQuery::dispatch($query->id);

        // A plain redirect (not just setting activeQueryId in place) so this question's
        // URL is bookmarkable and a later visit — a browser back/forward, a reopened tab —
        // mounts fresh from the database instead of reusing whatever Alpine/Livewire state
        // was on screen when the user left, which is what left the stage spinner frozen
        // after the query had actually finished.
        $this->redirect(route('ask.show', $query));
    }

    public function newQuestion(): void
    {
        $this->redirect(route('ask'));
    }

    /** Called by the browser's stage-poll once the query reaches a terminal status. */
    public function refreshResult(): void {}

    public function giveFeedback(bool $thumbsUp): void
    {
        if (! $this->activeQueryId) {
            return;
        }

        QueryFeedback::updateOrCreate(
            ['query_id' => $this->activeQueryId, 'user_id' => Auth::id()],
            ['thumbs_up' => $thumbsUp, 'note' => $this->feedbackNote ?: null],
        );
        $this->feedbackNote = '';
    }

    public function render()
    {
        $activeQuery = $this->activeQueryId
            ? Query::with(['chartArtifact', 'feedback' => fn ($q) => $q->where('user_id', Auth::id())])->find($this->activeQueryId)
            : null;

        $recentQueries = Query::where('user_id', Auth::id())->latest()->limit(20)->get(['id', 'prompt', 'status', 'created_at']);

        return view('livewire.ask', ['activeQuery' => $activeQuery, 'recentQueries' => $recentQueries])
            ->layout('components.layout', ['pageTitle' => 'Ask', 'title' => 'Ask']);
    }
}
