<?php

namespace App\Livewire;

use App\Jobs\RunExciseQuery;
use App\Models\Query;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Livewire\Component;

class Ask extends Component
{
    public string $prompt = '';

    public ?string $activeQueryId = null;

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

        $this->activeQueryId = $query->id;
        $this->prompt = '';
    }

    public function newQuestion(): void
    {
        $this->activeQueryId = null;
    }

    /** Called by the browser's stage-poll once the query reaches a terminal status. */
    public function refreshResult(): void {}

    public function render()
    {
        $activeQuery = $this->activeQueryId
            ? Query::with('chartArtifact')->find($this->activeQueryId)
            : null;

        return view('livewire.ask', ['activeQuery' => $activeQuery])
            ->layout('components.layout', ['pageTitle' => 'Ask', 'title' => 'Ask']);
    }
}
