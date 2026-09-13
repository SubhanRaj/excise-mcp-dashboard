<?php

namespace App\Livewire\Admin;

use App\Models\ActivityLog;
use Livewire\Component;
use Livewire\WithPagination;

class ActivityLogIndex extends Component
{
    use WithPagination;

    public string $search = '';

    public function mount(): void
    {
        abort_unless(auth()->user()->hasPrivilege('activity-logs.view'), 403);
    }

    public function updatingSearch(): void
    {
        $this->resetPage();
    }

    public function render()
    {
        $logs = ActivityLog::with('user')
            ->when($this->search, fn ($q) => $q->where('action', 'like', "%{$this->search}%"))
            ->latest('created_at')
            ->paginate(30);

        return view('livewire.admin.activity-log-index', ['logs' => $logs])
            ->layout('components.layout', ['pageTitle' => 'Activity log', 'title' => 'Activity log']);
    }
}
