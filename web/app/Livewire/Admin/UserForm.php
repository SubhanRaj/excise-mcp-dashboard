<?php

namespace App\Livewire\Admin;

use App\Mail\AccountOnboarding;
use App\Models\Designation;
use App\Models\User;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\URL;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;
use Livewire\Component;

class UserForm extends Component
{
    public ?User $user = null;

    public string $name = '';

    public string $username = '';

    public string $email = '';

    public string $mobile = '';

    public string $role = 'Analyst';

    public string $post = '';

    public ?int $designationId = null;

    /** @var array<int, string> */
    public array $privileges = [];

    public function mount(?User $user = null): void
    {
        abort_unless(auth()->user()->hasPrivilege('users.manage'), 403);

        $this->user = $user;
        $this->name = $user->name ?? '';
        $this->username = $user->username ?? '';
        $this->email = $user->email ?? '';
        $this->mobile = $user->mobile ?? '';
        $this->role = $user->role ?? 'Analyst';
        $this->post = $user->post ?? '';
        $this->designationId = $user->designation_id ?? null;
        $this->privileges = $user->privileges ?? [];
    }

    /**
     * A designation's default_privileges is a preset copied onto the user's own privileges
     * the moment it's picked — not a live-applied grant (web/plan/webui.md §6). Only fires
     * on create, where there's no existing privilege selection to clobber.
     */
    public function updatedDesignationId(): void
    {
        if ($this->user) {
            return;
        }

        $this->privileges = Designation::find($this->designationId)?->default_privileges ?? [];
    }

    public function save(): void
    {
        abort_unless(auth()->user()->hasPrivilege('users.manage'), 403);

        $validated = $this->validate([
            'name' => ['required', 'string', 'max:255'],
            'username' => ['required', 'string', 'max:255', Rule::unique('users', 'username')->ignore($this->user)->withoutTrashed()],
            'email' => ['required', 'email', 'max:255', Rule::unique('users', 'email')->ignore($this->user)],
            'mobile' => ['nullable', 'digits:10'],
            'role' => ['required', Rule::in(User::ROLES)],
            'post' => ['nullable', 'string', 'max:100'],
            'designationId' => ['nullable', 'exists:designations,id'],
            'privileges' => ['array'],
            'privileges.*' => [Rule::in(User::PRIVILEGES)],
        ]);

        try {
            $data = [
                'name' => $validated['name'],
                'username' => $validated['username'],
                'email' => $validated['email'],
                'mobile' => $validated['mobile'] ?: null,
                'role' => $validated['role'],
                'post' => $validated['post'] ?: null,
                'designation_id' => $validated['designationId'] ?: null,
                'privileges' => $validated['privileges'],
            ];

            if ($this->user) {
                DB::transaction(fn () => $this->user->update($data));
                flash()->success("Account for {$this->name} updated.");
            } else {
                // Unusable placeholder — the real password is set by the user via the
                // onboarding link mailed below. email_verified_at stays null as the
                // single-use gate for that link.
                $user = DB::transaction(fn () => User::create([
                    ...$data,
                    'password' => Hash::make(Str::random(40)),
                    'email_verified_at' => null,
                ]));

                try {
                    $url = URL::temporarySignedRoute('onboarding.show', now()->addHours(72), ['user' => $user->id]);
                    Mail::to($user->email)->send(new AccountOnboarding($user, $url));
                    flash()->success("Account for {$this->name} created — an activation email has been sent.");
                } catch (\Throwable $mailError) {
                    Log::error('UserForm::save: onboarding mail failed', ['user_id' => $user->id, 'error' => $mailError->getMessage()]);
                    flash()->warning("Account for {$this->name} created, but the activation email failed. Use \"Resend activation\" on their row.");
                }
            }

            $this->redirectRoute('admin.users.index', navigate: true);
        } catch (\Throwable $e) {
            Log::error('UserForm::save failed', ['user_id' => $this->user?->id, 'error' => $e->getMessage()]);
            flash()->error('Failed to save the account. Please try again.');
        }
    }

    public function render()
    {
        $title = $this->user ? "Edit {$this->user->name}" : 'Add User';

        return view('livewire.admin.user-form', [
            'designations' => Designation::orderBy('sort_order')->orderBy('name')->get(),
        ])->layout('components.layout', ['pageTitle' => $title, 'title' => $title]);
    }
}
