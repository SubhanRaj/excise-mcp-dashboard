<?php

namespace App\Livewire\Admin;

use App\Models\GoogleConnection;
use Livewire\Component;

class GoogleConnectionIndex extends Component
{
    public function mount(): void
    {
        abort_unless(auth()->user()->hasPrivilege('google.manage'), 403);
    }

    public function disconnect(string $connectionId): void
    {
        abort_unless(auth()->user()->hasPrivilege('google.manage'), 403);

        $connection = GoogleConnection::findOrFail($connectionId);
        abort_unless($connection->user_id === auth()->id() || auth()->user()->isAdmin(), 403);

        $connection->delete();
        flash()->success('Google account disconnected.');
    }

    public function render()
    {
        $connections = auth()->user()->isAdmin()
            ? GoogleConnection::with('user')->latest()->get()
            : GoogleConnection::with('user')->where('user_id', auth()->id())->latest()->get();

        return view('livewire.admin.google-connection-index', ['connections' => $connections])
            ->layout('components.layout', ['pageTitle' => 'Connected sources', 'title' => 'Connected sources']);
    }
}
