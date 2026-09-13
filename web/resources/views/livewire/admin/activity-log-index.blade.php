<div>
    <div class="relative w-full sm:w-72 mb-5">
        <i class="ti ti-search absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
        <input type="text" wire:model.live.debounce.300ms="search" placeholder="Search action..." class="field-input pl-9">
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        <table class="w-full text-sm">
            <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <tr>
                    <th class="px-4 py-3">When</th>
                    <th class="px-4 py-3">User</th>
                    <th class="px-4 py-3">Action</th>
                    <th class="px-4 py-3">IP</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                @forelse($logs as $log)
                <tr>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">{{ $log->created_at->ist()->format('d M Y, h:i A') }}</td>
                    <td class="px-4 py-3 text-slate-700 dark:text-slate-200">{{ $log->user?->name ?? '—' }}</td>
                    <td class="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{{ $log->action }}</td>
                    <td class="px-4 py-3 text-slate-400">{{ $log->ip_address }}</td>
                </tr>
                @empty
                <tr><td colspan="4" class="px-4 py-8 text-center text-slate-400">No activity recorded yet.</td></tr>
                @endforelse
            </tbody>
        </table>
    </div>

    <div class="mt-4">{{ $logs->links() }}</div>
</div>
