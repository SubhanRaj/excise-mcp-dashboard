<?php

namespace App\Livewire\Admin;

use App\Mail\AccountOnboarding;
use App\Models\User;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\Password;
use Illuminate\Support\Facades\URL;
use Livewire\Component;
use Livewire\WithPagination;

class UserIndex extends Component
{
    use WithPagination;

    public string $search = '';

    public function mount(): void
    {
        abort_unless(auth()->user()->hasPrivilege('users.manage'), 403);
    }

    public function updatingSearch(): void
    {
        $this->resetPage();
    }

    public function delete(string $userId): void
    {
        abort_unless(auth()->user()->hasPrivilege('users.manage'), 403);

        if ((string) $userId === (string) auth()->id()) {
            flash()->warning('You cannot delete your own account.');

            return;
        }

        $user = User::findOrFail($userId);

        try {
            DB::transaction(fn () => $user->delete());
            flash()->success("{$user->name}'s account has been deactivated.");
        } catch (\Throwable $e) {
            Log::error('UserIndex::delete failed', ['user_id' => $user->id, 'error' => $e->getMessage()]);
            flash()->error('Failed to deactivate account. Please try again.');
        }
    }

    public function resendActivation(string $userId): void
    {
        abort_unless(auth()->user()->hasPrivilege('users.manage'), 403);

        $user = User::findOrFail($userId);

        if ($user->email_verified_at !== null) {
            flash()->warning("{$user->name}'s account is already active.");

            return;
        }

        $url = URL::temporarySignedRoute('onboarding.show', now()->addHours(72), ['user' => $user->id]);
        Mail::to($user->email)->send(new AccountOnboarding($user, $url));
        flash()->success("Activation email re-sent to {$user->email}.");
    }

    public function sendPasswordReset(string $userId): void
    {
        abort_unless(auth()->user()->hasPrivilege('users.manage'), 403);

        $user = User::findOrFail($userId);
        Password::sendResetLink(['email' => $user->email]);
        flash()->success("Password reset link sent to {$user->email}.");
    }

    public function render()
    {
        $users = User::with('designation')
            ->when($this->search, fn ($q) => $q->where(function ($q) {
                $q->where('name', 'like', "%{$this->search}%")
                    ->orWhere('username', 'like', "%{$this->search}%")
                    ->orWhere('email', 'like', "%{$this->search}%");
            }))
            ->latest()
            ->paginate(20);

        return view('livewire.admin.user-index', ['users' => $users])
            ->layout('components.layout', ['pageTitle' => 'Users', 'title' => 'Users']);
    }
}
