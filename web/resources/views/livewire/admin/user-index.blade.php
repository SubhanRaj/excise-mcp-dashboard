<div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
        <div class="relative w-full sm:w-72">
            <i class="ti ti-search absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
            <input type="text" wire:model.live.debounce.300ms="search" placeholder="Search name, username, email..."
                   class="field-input pl-9">
        </div>
        <a href="{{ route('admin.users.create') }}" wire:navigate
           class="inline-flex items-center gap-2 bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors">
            <i class="ti ti-plus"></i> Add User
        </a>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        <table class="w-full text-sm">
            <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <tr>
                    <th class="px-4 py-3">Name</th>
                    <th class="px-4 py-3">Role</th>
                    <th class="px-4 py-3">Designation</th>
                    <th class="px-4 py-3">Status</th>
                    <th class="px-4 py-3 text-right">Actions</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                @forelse($users as $user)
                <tr>
                    <td class="px-4 py-3">
                        <p class="font-medium text-slate-800 dark:text-slate-100">{{ $user->name }}</p>
                        <p class="text-xs text-slate-400">{{ $user->username }} &middot; {{ $user->email }}</p>
                    </td>
                    <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ $user->role }}</td>
                    <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ $user->designation?->name ?? '—' }}</td>
                    <td class="px-4 py-3">
                        @if($user->email_verified_at)
                        <span class="badge bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">Active</span>
                        @else
                        <span class="badge bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">Pending activation</span>
                        @endif
                    </td>
                    <td class="px-4 py-3">
                        <div class="flex items-center justify-end gap-1 text-slate-400">
                            <a href="{{ route('admin.users.edit', $user) }}" wire:navigate class="p-1.5 hover:text-govviolet-600" title="Edit">
                                <i class="ti ti-pencil"></i>
                            </a>
                            @if(!$user->email_verified_at)
                            <button wire:click="resendActivation('{{ $user->id }}')" class="p-1.5 hover:text-govviolet-600" title="Resend activation">
                                <i class="ti ti-mail-forward"></i>
                            </button>
                            @else
                            <button wire:click="sendPasswordReset('{{ $user->id }}')" class="p-1.5 hover:text-govviolet-600" title="Send password reset">
                                <i class="ti ti-key"></i>
                            </button>
                            @endif
                            @if($user->id !== auth()->id())
                            <button wire:click="delete('{{ $user->id }}')" wire:confirm="Deactivate {{ $user->name }}'s account?" class="p-1.5 hover:text-red-600" title="Deactivate">
                                <i class="ti ti-trash"></i>
                            </button>
                            @endif
                        </div>
                    </td>
                </tr>
                @empty
                <tr><td colspan="5" class="px-4 py-8 text-center text-slate-400">No users found.</td></tr>
                @endforelse
            </tbody>
        </table>
    </div>

    <div class="mt-4">{{ $users->links() }}</div>
</div>
