<?php

namespace App\Livewire;

use App\Models\Query;
use Livewire\Component;
use Livewire\WithPagination;

/**
 * Every past /query, one row per submitted question (ROADMAP.md Milestone 5).
 * Every signed-in user reaches this at /ledger — an Analyst sees only their
 * own rows, an Admin sees everyone's, the same split Ask's "Recent questions"
 * rail already applies to a single user's own queries.
 */
class QueryLedger extends Component
{
    use WithPagination;

    public string $search = '';

    public string $status = '';

    public function updatingSearch(): void
    {
        $this->resetPage();
    }

    public function updatingStatus(): void
    {
        $this->resetPage();
    }

    public function render()
    {
        $queries = Query::query()
            ->when(! auth()->user()->isAdmin(), fn ($q) => $q->where('user_id', auth()->id()))
            ->when($this->search, fn ($q) => $q->where('prompt', 'like', "%{$this->search}%"))
            ->when($this->status, fn ($q) => $q->where('status', $this->status))
            ->with('user')
            ->latest()
            ->paginate(30);

        return view('livewire.query-ledger', ['queries' => $queries])
            ->layout('components.layout', ['pageTitle' => 'Query ledger', 'title' => 'Query ledger']);
    }
}
