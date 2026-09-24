<?php

namespace App\Livewire;

use App\Jobs\RunExciseQuery;
use App\Livewire\Concerns\ConfirmsWithSweetAlert;
use App\Models\ChartArtifact;
use App\Models\Query;
use App\Models\QueryFeedback;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Livewire\Component;

class Ask extends Component
{
    use ConfirmsWithSweetAlert;

    /**
     * Verified against the real August 2026 Lucknow import (CLAUDE.md's dispatch-report
     * milestone) — a first-time visitor's proof that the pipeline produces a real answer,
     * not a hypothetical one. Shown only on the empty composer; not a data source of any
     * kind, so a plain const is enough.
     */
    public const EXAMPLE_QUESTIONS = [
        'How many country liquor and composite shops are in Lucknow in August 2026?',
        'What was the total dispatch amount and volume for Lucknow in August 2026?',
        'How many CL5C shops are there in Lucknow?',
    ];

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

    public function useExample(string $question): void
    {
        $this->prompt = $question;
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

    public function deleteQuery(string $id): void
    {
        $query = Query::findOrFail($id);
        abort_unless($query->user_id === Auth::id(), 403);
        $query->delete();
        if ($this->activeQueryId === $id) {
            $this->redirect(route('ask'));
        }
    }

    public function forceDeleteQuery(string $id): void
    {
        $query = Query::withTrashed()->findOrFail($id);
        abort_unless($query->user_id === Auth::id(), 403);

        // chart_artifacts is a polymorphic owner with no DB-level FK to queries, so a
        // plain forceDelete() below would otherwise leave an orphaned artifact row and
        // its rendered files behind.
        ChartArtifact::withTrashed()
            ->where('owner_type', Query::class)
            ->where('owner_id', $query->id)
            ->get()
            ->each(function (ChartArtifact $artifact): void {
                foreach (['png_path', 'svg_path', 'pdf_path'] as $column) {
                    if ($artifact->$column) {
                        Storage::disk('local')->delete($artifact->$column);
                    }
                }
                $artifact->forceDelete();
            });

        $query->forceDelete(); // cascades query_feedback via its own DB FK
        if ($this->activeQueryId === $id) {
            $this->redirect(route('ask'));
        }
    }

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

        $title = $activeQuery ? Str::limit(trim($activeQuery->prompt), 60) : 'Ask';

        return view('livewire.ask', ['activeQuery' => $activeQuery, 'recentQueries' => $recentQueries])
            ->layout('components.layout', ['pageTitle' => $title, 'title' => $title]);
    }
}
