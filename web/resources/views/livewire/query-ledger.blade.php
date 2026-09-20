<div>
    <div class="flex flex-col sm:flex-row gap-3 mb-5">
        <div class="relative w-full sm:w-72">
            <i class="ti ti-search absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
            <input type="text" wire:model.live.debounce.300ms="search" placeholder="Search prompt..." class="field-input !pl-9">
        </div>
        <select wire:model.live="status" class="field-input w-full sm:w-44">
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="complete">Complete</option>
            <option value="failed">Failed</option>
        </select>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden overflow-x-auto">
        <table class="w-full text-sm">
            <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <tr>
                    <th class="px-4 py-3">When</th>
                    @if(auth()->user()->isAdmin())
                    <th class="px-4 py-3">User</th>
                    @endif
                    <th class="px-4 py-3">Prompt</th>
                    <th class="px-4 py-3">Engine</th>
                    <th class="px-4 py-3">Model</th>
                    <th class="px-4 py-3">Rows</th>
                    <th class="px-4 py-3">Status</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                @forelse($queries as $query)
                <tr wire:key="query-{{ $query->id }}" class="hover:bg-slate-50 dark:hover:bg-slate-900/40">
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">{{ $query->created_at->ist()->format('d M Y, h:i A') }}</td>
                    @if(auth()->user()->isAdmin())
                    <td class="px-4 py-3 text-slate-700 dark:text-slate-200">{{ $query->user?->name ?? '—' }}</td>
                    @endif
                    <td class="px-4 py-3 text-slate-700 dark:text-slate-200 max-w-xs truncate">
                        <a href="{{ route('ask.show', $query) }}" wire:navigate class="hover:text-govviolet-600 hover:underline">{{ $query->prompt }}</a>
                    </td>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ $query->engine ?? '—' }}</td>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400 font-mono text-xs">{{ $query->model ?? '—' }}</td>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ $query->row_count ?? '—' }}</td>
                    <td class="px-4 py-3">
                        <span class="badge {{ match($query->status) {
                            'complete' => 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
                            'failed' => 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
                            default => 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
                        } }}">{{ ucfirst($query->status) }}</span>
                    </td>
                </tr>
                @empty
                <tr><td colspan="{{ auth()->user()->isAdmin() ? 7 : 6 }}" class="px-4 py-8 text-center text-slate-400">No questions asked yet.</td></tr>
                @endforelse
            </tbody>
        </table>
    </div>

    <div class="mt-4">{{ $queries->links() }}</div>
</div>
